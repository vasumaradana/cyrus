"""
Cyrus - Voice Layer for Claude Code (VS Code)
Powered by Whisper + Silero VAD + Edge TTS + Windows UI Automation

Flow:
  1. Speak naturally — Cyrus transcribes and routes your words.
  2. Regex fast-path handles Cyrus commands; everything else forwards to Claude Code.
  3. Claude responds — Cyrus reads the response aloud automatically.

Multi-session:
  Responses from non-active VS Code sessions are held in a per-session queue.
  A brief chime plays when a response arrives for a session you're not in.
  When you switch sessions (by focusing the window or saying 'Cyrus, switch to
  [name]'), queued responses play automatically in order.

Voice commands (after wake word):
  "switch to [name]"   — lock routing to that project
  "auto" / "unlock"    — follow window focus again
  "which project"      — hear which session is active
  "last message"       — replay the last response in the active session
  "pause"              — toggle listening on/off

Hotkeys:
  F9 — pause / resume listening
  F7 — stop speaking + clear queued speech
  F8 — read clipboard aloud
  Ctrl+C (in terminal) — exit
"""

import os
import re
import json
import argparse
import asyncio
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import sounddevice as sd
import keyboard
import pygame
import torch
from silero_vad import load_silero_vad
import pyautogui
import pyperclip
import pygetwindow as gw
import uiautomation as auto
from collections import deque
from faster_whisper import WhisperModel
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ── GPU detection (runs at import time) ───────────────────────────────────────

_CUDA     = torch.cuda.is_available()
_GPU_NAME = torch.cuda.get_device_name(0) if _CUDA else "none"

# ── Configuration ─────────────────────────────────────────────────────────────

WHISPER_MODEL        = "medium.en"
WHISPER_DEVICE       = "cuda" if _CUDA else "cpu"
WHISPER_COMPUTE_TYPE = "float16" if _CUDA else "int8"
SAMPLE_RATE        = 16000
CHANNELS           = 1

# Kokoro TTS — model files must be in the same directory as main.py
KOKORO_MODEL       = os.path.join(os.path.dirname(__file__), "kokoro-v1.0.onnx")
KOKORO_VOICES      = os.path.join(os.path.dirname(__file__), "voices-v1.0.bin")
TTS_VOICE          = "af_heart"    # see voices-v1.0.bin for full list
TTS_SPEED          = 1.0           # 0.5 – 2.0

VSCODE_TITLE       = "Visual Studio Code"
# Whisper often mis-transcribes "Cyrus" — accept common phonetic variants
WAKE_WORDS         = {"cyrus", "sire", "sirius", "serious", "cyprus",
                      "virus", "sirus", "cirus", "sy", "sir", "sarush", "surus",
                      "saras", "serus", "situs", "cirrus", "serous", "ceres"}

KEY_PAUSE          = "f9"
KEY_STOP           = "f7"
KEY_READ_CLIP      = "f8"

SPEECH_THRESHOLD   = 0.5      # Silero probability threshold (0-1)
FRAME_MS           = 32       # Silero requires 512 samples @ 16 kHz (32 ms)
FRAME_SIZE         = 512      # must match exactly
SPEECH_WINDOW_MS   = 300
SILENCE_WINDOW_MS  = 1000     # ms of silence to end utterance (Silero handles noise, so 1 s is safe)
MAX_RECORD_MS      = 12000    # hard cap — end recording after 12 s regardless
MAX_SPEECH_WORDS      = 30   # hard cap on spoken words (~12s at 150 wpm)
# Appended to every forwarded message so Claude keeps responses voice-friendly
VOICE_HINT = ("\n\n[Voice mode: keep explanations to 2-3 sentences. "
              "For code changes show only the modified section, not the full file.]")

SPEECH_RING        = SPEECH_WINDOW_MS  // FRAME_MS
SILENCE_RING       = SILENCE_WINDOW_MS // FRAME_MS
MAX_RECORD_FRAMES  = MAX_RECORD_MS     // FRAME_MS
SPEECH_RATIO       = 0.80     # fraction of ring that must be speech to start (was 0.75)

_CHAT_INPUT_HINT   = "Message input"  # UIA Name of Claude Code's chat EditControl


# ── Shared state ──────────────────────────────────────────────────────────────

_mic_muted            = threading.Event()
_user_paused          = threading.Event()
_stop_speech          = threading.Event()
_tts_active           = threading.Event()  # set while Cyrus is playing speech
_tts_pending          = threading.Event()  # set when TTS is queued but not yet started
_shutdown             = threading.Event()  # set on Ctrl+C to stop all loops cleanly

pyautogui.FAILSAFE = False
auto.uiautomation.SetGlobalSearchTimeout(2)

# ── Session tracking ──────────────────────────────────────────────────────────

_active_project:      str            = ""
_active_project_lock: threading.Lock = threading.Lock()
_chat_input_cache:    dict           = {}   # project_name → UIA EditControl
_vscode_win_cache:    dict           = {}   # project_name → pygetwindow handle

_project_locked:      bool           = False
_project_locked_lock: threading.Lock = threading.Lock()

_conversation_active: bool           = False  # True = no wake word needed for next reply

# Whisper initial_prompt — updated as sessions are discovered so project names
# are recognised correctly (e.g. "dev", "web app").  Thread-safe: only written
# from the session-scan thread before transcription starts in earnest.
_whisper_prompt: str = "Cyrus,"

# Global TTS queue — initialized in main()
_tts_queue: asyncio.Queue = None   # asyncio.Queue[tuple[str, str]]

# Dedicated executor — initialized in main()
_whisper_executor: ThreadPoolExecutor = None   # max_workers=1, CPU-bound

# Remote brain connection — set when --remote URL is passed
_remote_url: str  = ""          # e.g. "ws://192.168.1.10:8765"
_remote_ws        = None        # websockets.ClientConnection, or None

# Kokoro TTS engine — initialized in main()
_kokoro           = None



def _extract_project(title: str) -> str:
    """'main.py - cyrus - Visual Studio Code'  →  'cyrus'"""
    t = title.replace(" - Visual Studio Code", "").lstrip("● ").strip()
    parts = [p.strip() for p in t.split(" - ") if p.strip()]
    return parts[-1] if parts else "VS Code"


def _make_alias(proj: str) -> str:
    """'my-web-app' → 'my web app',  'backend_service' → 'backend service'"""
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", proj.lower())).strip()


def _resolve_project(query: str, aliases: dict) -> str | None:
    """Return the project_name whose alias best matches query, or None."""
    q = query.lower().strip()
    if q in aliases:
        return aliases[q]
    for alias, proj in aliases.items():
        if q in alias or alias in q:
            return proj
    return None


def _vs_code_windows() -> list[tuple[str, str]]:
    """Return [(project_name, subname), ...] for every open VS Code window."""
    seen:   set[str]              = set()
    result: list[tuple[str, str]] = []
    for w in gw.getAllWindows():
        if VSCODE_TITLE not in (w.title or ""):
            continue
        proj = _extract_project(w.title)
        if proj not in seen:
            seen.add(proj)
            result.append((proj, f"{proj} - Visual Studio Code"))
    return result


def _start_active_tracker(session_mgr, tts_queue, loop):
    """Background thread — tracks which VS Code window was last focused."""
    global _active_project
    while True:
        try:
            w = gw.getActiveWindow()
            if w and VSCODE_TITLE in (w.title or ""):
                proj = _extract_project(w.title)
                with _project_locked_lock:
                    locked = _project_locked
                with _active_project_lock:
                    changed = _active_project != proj
                if changed and not locked:
                    with _active_project_lock:
                        _active_project = proj
                    print(f"[Cyrus] Active project: {proj}")
                    session_mgr.on_session_switch(proj, tts_queue, loop)
        except Exception:
            log.debug("Active window tracker poll failed", exc_info=True)
        time.sleep(0.5)


# ── Chime ─────────────────────────────────────────────────────────────────────

def play_chime():
    """Play a brief 880 Hz notification tone (non-blocking, low volume)."""
    try:
        sample_rate = 44100
        duration    = 0.18
        t    = np.linspace(0, duration, int(sample_rate * duration), False)
        wave = (np.sin(2 * np.pi * 880 * t) * 32767 * 0.25).astype(np.int16)
        stereo = np.column_stack([wave, wave])
        sound = pygame.sndarray.make_sound(stereo)
        sound.play()
    except Exception:
        log.debug("Chime playback failed", exc_info=True)


def play_listen_chime():
    """
    Two-tone ascending beep (500 Hz → 800 Hz) — signals Cyrus is listening.
    Distinct from play_chime() so the user always knows when to speak.
    """
    try:
        sr  = 44100
        gap = np.zeros(int(sr * 0.04), dtype=np.int16)

        def tone(freq, dur, vol=0.22):
            t = np.linspace(0, dur, int(sr * dur), False)
            return (np.sin(2 * np.pi * freq * t) * 32767 * vol).astype(np.int16)

        wave   = np.concatenate([tone(500, 0.09), gap, tone(800, 0.09)])
        stereo = np.column_stack([wave, wave])
        pygame.sndarray.make_sound(stereo).play()
    except Exception:
        log.debug("Listen chime playback failed", exc_info=True)


# ── TTS queue helpers ─────────────────────────────────────────────────────────

async def drain_tts_queue() -> None:
    if _tts_queue is None:
        return
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except Exception:
            log.debug("TTS queue drain interrupted", exc_info=True)
            break


async def tts_worker(session_mgr) -> None:
    """Single async consumer — speaks one item at a time."""
    while True:
        project_name, text = await _tts_queue.get()
        _tts_pending.clear()
        try:
            if session_mgr.multi_session and project_name:
                text = f"{project_name}. {text}"
            print(f"[TTS worker] speak: {text[:50]!r}")
            await speak(text)
            print("[TTS worker] done")
        except Exception:
            log.warning("TTS speak failed", exc_info=True)


async def _speak_urgent(text: str) -> None:
    """Drain queue then speak immediately — for permission dialogs."""
    await drain_tts_queue()
    await speak(text)



_ANSWER_RE = re.compile(
    # Explicit recap / summarise requests
    r"\b(recap|summarize?|summary)\b"
    # "what did/was/were ... say/said/respond/answer" — past tense about a response
    r"|what\s+(did|was|were)\b.{0,40}\b(say|said|respond|answered?|told?|reply|replied)\b"
    # "what you/Claude/Cyrus said"
    r"|what\s+(you|claude|cyrus|it)\s+said\b"
    # "last response" / "last reply" as a phrase
    r"|\b(last\s+response|last\s+reply)\b"
    # "repeat that" or "repeat what you said"
    r"|\brepeat\s+(that|what\s+(you|claude|cyrus|it)\s+said)\b",
    re.IGNORECASE,
)

def _is_answer_request(text: str) -> bool:
    """True if the utterance is asking Cyrus to replay/summarise Claude's last response."""
    return bool(_ANSWER_RE.search(text))


async def _remote_route(text: str, project: str, last_response: str) -> dict:
    """
    Send a transcribed utterance to the remote brain and return its routing decision.
    Falls back to local routing if the connection is unavailable.
    """
    global _remote_ws
    if _remote_ws is None:
        return None   # caller handles fallback

    try:
        msg = json.dumps({
            "type":          "utterance",
            "text":          text,
            "project":       project,
            "last_response": last_response,
        })
        await _remote_ws.send(msg)
        raw = await asyncio.wait_for(_remote_ws.recv(), timeout=5.0)
        data = json.loads(raw)
        # Strip the envelope "type" key before returning as a decision dict
        data.pop("type", None)
        return data
    except Exception:
        log.error("Remote brain unreachable", exc_info=True)
        _remote_ws = None
        return None


def _fast_command(text: str) -> dict | None:
    """
    Regex fast-path for obvious Cyrus meta-commands.
    Returns a decision dict or None if
    the utterance should be sent to the LLM.
    """
    t = text.lower().strip().rstrip(".,!?")

    # pause / resume
    if re.fullmatch(r"pause|resume|stop listening|start listening", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "pause"}}

    # unlock / auto
    if re.fullmatch(r"(un ?lock|auto|follow focus|auto(matic)? routing)", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "unlock"}}

    # which project / what project
    if re.search(r"\b(which|what)\b.{0,20}\b(project|session)\b", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "which_project"}}

    # last message / replay
    if re.fullmatch(r"(last|repeat|replay|again).{0,30}(message|response|said)?", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "last_message"}}

    # switch to <name>  — many natural phrasings
    m = (re.match(r"(?:switch(?:ed)?(?: to)?|use|go to|open|activate)\s+(.+)", t)
         or re.match(r"make\s+(.+?)\s+(?:the\s+)?active", t)
         or re.match(r"(?:set|change)\s+(?:active\s+)?(?:project|session)\s+to\s+(.+)", t))
    if m:
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "switch_project", "project": m.group(1).strip()}}

    # rename <old> to <new>  /  rename this to <new>  /  call this <new>
    m = (re.match(r"(?:rename|relabel)\s+(?:this\s+)?(?:session\s+|window\s+)?to\s+(.+)", t)
         or re.match(r"call\s+this\s+(?:session\s+|window\s+)?(.+)", t))
    if m:
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "rename_session", "new": m.group(1).strip()}}

    m = re.match(r"(?:rename|relabel)\s+(.+?)\s+to\s+(.+)", t)
    if m:
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "rename_session",
                            "old": m.group(1).strip(), "new": m.group(2).strip()}}

    return None


def _execute_cyrus_command(ctype: str, cmd: dict, spoken: str,
                            session_mgr, loop) -> None:
    """Execute a Cyrus meta-command returned by the LLM."""
    global _active_project, _project_locked

    if ctype == "switch_project":
        target = _resolve_project(cmd.get("project", ""), session_mgr.aliases)
        if target:
            with _active_project_lock:
                _active_project = target
            with _project_locked_lock:
                _project_locked = True
            session_mgr.on_session_switch(target, _tts_queue, loop)
            spoken = spoken or f"Switched to {target}. Routing locked."
            print(f"[Cyrus] {spoken}")
        else:
            spoken = f"No session matching '{cmd.get('project', '')}' found."
            print(f"[Cyrus] {spoken}")

    elif ctype == "unlock":
        with _project_locked_lock:
            _project_locked = False
        spoken = spoken or "Following window focus."
        print("[Cyrus] Routing unlocked.")

    elif ctype == "which_project":
        with _active_project_lock:
            proj_name = _active_project
        with _project_locked_lock:
            locked = _project_locked
        status = "locked" if locked else "following focus"
        spoken = spoken or f"Active project: {proj_name or 'none'}, {status}."
        print(f"[Cyrus] {spoken}")

    elif ctype == "last_message":
        with _active_project_lock:
            proj_name = _active_project
        resp = session_mgr.last_response(proj_name)
        if resp:
            asyncio.run_coroutine_threadsafe(
                _tts_queue.put((proj_name, resp)), loop
            )
            return  # spoken already queued above
        else:
            spoken = spoken or f"No recorded response for {proj_name or 'this session'}."
            print(f"[Cyrus] {spoken}")

    elif ctype == "rename_session":
        new_name = cmd.get("new", "").strip()
        old_hint = cmd.get("old", "").strip()
        with _active_project_lock:
            active = _active_project
        # Resolve which project to rename: explicit old name or active project
        if old_hint:
            proj = _resolve_project(old_hint, session_mgr.aliases)
        else:
            proj = active
        if proj and new_name:
            # Find current alias for this project
            old_alias = next((a for a, p in session_mgr.aliases.items() if p == proj), proj)
            session_mgr.rename_alias(old_alias, new_name, proj)
            spoken = spoken or f"Renamed to '{new_name}'."
            print(f"[Cyrus] {proj} → alias '{new_name}'")
        else:
            spoken = spoken or "Could not find that session to rename."
        print(f"[Cyrus] {spoken}")

    elif ctype == "pause":
        if _user_paused.is_set():
            _user_paused.clear()
            spoken = spoken or "Resumed."
        else:
            _user_paused.set()
            spoken = spoken or "Paused."
        print(f"[Cyrus] {spoken}")

    if spoken:
        asyncio.run_coroutine_threadsafe(_tts_queue.put(("", spoken)), loop)


# ── Chat Watcher ──────────────────────────────────────────────────────────────

class ChatWatcher:
    """
    Polls a specific Claude Code chat webview via UIA.
    When a new response stabilises, either enqueues it for TTS (active session)
    or holds it in _pending_queue and chimes (non-active session).
    """
    POLL_SECS   = 0.5
    STABLE_SECS = 1.2

    _STOP = {"Edit automatically", "Show command menu (/)",
             "ctrl esc to focus or unfocus Claude", "Message input"}
    _SKIP = {"Thinking", "Message actions", "Copy code to clipboard",
             "Stop", "Regenerate", "tasks", "New session", "Ask before edits"}

    def __init__(self, project_name: str = "", target_subname: str = ""):
        self._chat_doc        = None
        self._last_text              = ""
        self._last_change            = 0.0
        self._last_spoken            = ""
        self._new_submission_pending = False  # True after user submits; cleared on _last_text change
        self._pending_queue:  list[str]  = []
        self._response_history: deque   = deque(maxlen=10)
        self.project_name     = project_name
        self._target_sub      = target_subname or VSCODE_TITLE

    @property
    def last_spoken(self) -> str:
        return self._last_spoken

    def flush_pending(self, tts_queue, loop) -> int:
        items = self._pending_queue[:]
        self._pending_queue.clear()
        for text in items:
            try:
                asyncio.run_coroutine_threadsafe(
                    tts_queue.put((self.project_name, text)), loop
                )
            except Exception:
                log.debug("Failed to queue TTS item", exc_info=True)
        return len(items)

    # ── Find the webview ──────────────────────────────────────────────────────

    def _find_webview(self):
        vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
        if not vscode.Exists(3):
            return None
        chrome = vscode.PaneControl(searchDepth=12,
                                    ClassName="Chrome_RenderWidgetHostHWND")
        if not chrome.Exists(2):
            return None

        docs: list[tuple[int, auto.Control]] = []

        def collect(ctrl, d=0):
            if d > 15:
                return
            try:
                if ctrl.ControlTypeName == "DocumentControl":
                    docs.append((d, ctrl))
            except Exception:
                log.debug("UIA DocumentControl check failed", exc_info=True)
            try:
                child = ctrl.GetFirstChildControl()
                while child:
                    collect(child, d + 1)
                    child = child.GetNextSiblingControl()
            except Exception:
                log.debug("UIA sibling walk failed", exc_info=True)

        collect(chrome)
        unnamed = [(d, c) for d, c in docs if not (c.Name or "").strip()]
        if unnamed:
            return unnamed[-1][1]
        return docs[-1][1] if docs else None

    # ── Walk accessibility tree ───────────────────────────────────────────────

    def _walk(self, ctrl, depth=0, max_depth=12, out=None):
        if out is None:
            out = []
        if depth > max_depth:
            return out
        try:
            name  = (ctrl.Name or "").strip()
            ctype = ctrl.ControlTypeName or ""
            if len(name) >= 4:
                out.append((depth, ctype, name))
        except Exception:
            log.debug("UIA control name/type read failed", exc_info=True)
        try:
            child = ctrl.GetFirstChildControl()
            while child:
                self._walk(child, depth + 1, max_depth, out)
                child = child.GetNextSiblingControl()
        except Exception:
            log.debug("UIA sibling walk failed", exc_info=True)
        return out

    # ── Extract latest Claude response ────────────────────────────────────────

    def _extract_response(self, results):
        """
        Extract the latest Claude response.

        Anchor strategy:
          - "Message input" EditControl is a reliable end-of-chat marker.
          - The last "Thinking" ButtonControl before it marks the start of
            Claude's final response block (Thinking appears before each reply).
          - Fallback: last "Message actions" before "Message input" if no Thinking.
        """
        # Find "Message input" EditControl position (end of chat content)
        msg_input_pos = next(
            (i for i, (_, ct, tx) in enumerate(results)
             if ct == "EditControl" and tx == _CHAT_INPUT_HINT),
            -1
        )
        if msg_input_pos == -1:
            return ""

        # Primary: last "Thinking" button before Message input
        start = -1
        for i, (_, ctype, text) in enumerate(results[:msg_input_pos]):
            if ctype == "ButtonControl" and "Thinking" in text:
                start = i

        # Secondary: last "Message actions" before Message input
        if start == -1:
            for i, (_, ctype, text) in enumerate(results[:msg_input_pos]):
                if ctype == "ButtonControl" and text == "Message actions":
                    start = i

        if start == -1:
            return ""

        parts: list[str] = []
        seen:  set[str]  = set()

        for _, ctype, text in results[start + 1: msg_input_pos]:
            if text in self._STOP:
                break
            if ctype == "ButtonControl" and text == "Message actions":
                break  # end of Claude's response block; user's next message follows
            if text in self._SKIP or len(text) < 4:
                continue
            if ctype not in ("TextControl", "ListItemControl"):
                continue
            if text not in seen and not any(text in s for s in seen if len(s) > len(text)):
                seen.add(text)
                parts.append(text)

        return " ".join(parts)

    # ── Polling loop ──────────────────────────────────────────────────────────

    def start(self, tts_queue, loop: asyncio.AbstractEventLoop,
              is_active_fn=None):
        if is_active_fn is None:
            def is_active_fn() -> bool:
                return True

        def poll():
            while self._chat_doc is None:
                self._chat_doc = self._find_webview()
                if self._chat_doc is None:
                    time.sleep(2)
            label = f"[{self.project_name}] " if self.project_name else ""
            print(f"[Cyrus] {label}Connected to Claude Code chat panel.")

            # Seed: retry until we get non-empty content (avoids phantom read on startup)
            for _ in range(6):
                try:
                    seed = self._extract_response(self._walk(self._chat_doc))
                    if seed:
                        break
                except Exception:
                    log.debug("Initial seed extraction failed", exc_info=True)
                    seed = ""
                time.sleep(1.0)
            self._last_spoken = seed
            self._last_text   = seed
            self._last_change = time.time()

            while True:
                time.sleep(self.POLL_SECS)
                try:
                    results  = self._walk(self._chat_doc)
                    response = self._extract_response(results)
                    now      = time.time()

                    # Detect new user submission: count "Message actions" buttons
                    msg_actions_count = sum(
                        1 for _, ct, tx in results
                        if ct == "ButtonControl" and tx == "Message actions"
                    )
                    if msg_actions_count != getattr(self, "_last_msg_actions_count", -1):
                        prev = getattr(self, "_last_msg_actions_count", -1)
                        self._last_msg_actions_count = msg_actions_count
                        if prev != -1 and msg_actions_count > prev:
                            self._new_submission_pending = True

                    if response != self._last_text:
                        self._last_text   = response
                        self._last_change = now
                        if response:
                            print(f"[DBG {self.project_name}] chg: {response[:60]!r}")
                        # _last_text changed → Claude started a new response.
                        # If we have a pending submission, clear _last_spoken now
                        # so the settled response fires TTS even if text is identical.
                        if self._new_submission_pending:
                            self._new_submission_pending = False
                            self._last_spoken = ""
                    elif response and response != self._last_spoken:
                        # Time-based stability: fire once response unchanged for STABLE_SECS
                        if now - self._last_change >= self.STABLE_SECS:
                            self._last_spoken = response
                            # Silently absorb if seed failed — never speak stale content
                            if not seed:
                                seed = response  # baseline set; next change will speak
                                print(f"[DBG {self.project_name}] silent absorb")
                                continue
                            spoken = clean_for_speech(response)
                            self._response_history.append(spoken)

                            preview = spoken[:80] + ("..." if len(spoken) > 80 else "")
                            print(f"\nCyrus [{self.project_name or 'Claude'}]: {preview}")

                            if is_active_fn():
                                print(f"[DBG {self.project_name}] → TTS queued")
                                _tts_pending.set()
                                asyncio.run_coroutine_threadsafe(
                                    tts_queue.put((self.project_name, spoken)), loop
                                )
                            else:
                                print(f"[DBG {self.project_name}] → pending (active={_active_project!r})")
                                self._pending_queue.append(spoken)
                                play_chime()
                                print(f"[queued: {self.project_name}] "
                                      f"{len(self._pending_queue)} message(s) waiting")

                except Exception:
                    log.warning("Chat doc walk failed, reconnecting", exc_info=True)
                    self._chat_doc = None
                    while self._chat_doc is None:
                        self._chat_doc = self._find_webview()
                        if self._chat_doc is None:
                            time.sleep(2)

        threading.Thread(target=poll, daemon=True).start()


# ── Permission Watcher ────────────────────────────────────────────────────────

class PermissionWatcher:
    """
    Polls Claude Code's chat webview once per interval and checks for both:
      1. Permission dialogs ("Yes, allow" buttons for bash commands)
      2. Open-ended input prompts (EditControls with a label)
    Single walk per poll — no extra thread needed for prompt detection.
    """
    POLL_SECS   = 0.3
    ALLOW_WORDS = {"yes", "allow", "sure", "ok", "okay", "proceed", "yep", "yeah", "go"}
    DENY_WORDS  = {"no", "deny", "cancel", "stop", "nope", "reject"}

    _SKIP_PROMPT_NAMES  = {_CHAT_INPUT_HINT, ""}
    _SKIP_PROMPT_LABELS = {"search", "find", "replace", "filter", "go to line"}

    def __init__(self, project_name: str = "", target_subname: str = ""):
        self._chat_doc  = None
        # permission state
        self._pending   = False
        self._allow_btn = None
        self._announced = ""
        # input-prompt state
        self._prompt_pending    = False
        self._prompt_input_ctrl = None
        self._prompt_announced  = ""
        self.project_name = project_name
        self._target_sub  = target_subname or VSCODE_TITLE

    @property
    def is_pending(self):
        return self._pending

    @property
    def prompt_pending(self):
        return self._prompt_pending

    def _find_webview(self):
        vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
        if not vscode.Exists(3):
            return None
        chrome = vscode.PaneControl(searchDepth=12,
                                    ClassName="Chrome_RenderWidgetHostHWND")
        if not chrome.Exists(2):
            return None
        docs: list[tuple[int, auto.Control]] = []

        def collect(ctrl, d=0):
            if d > 15:
                return
            try:
                if ctrl.ControlTypeName == "DocumentControl":
                    docs.append((d, ctrl))
            except Exception:
                log.debug("UIA DocumentControl check failed", exc_info=True)
            try:
                child = ctrl.GetFirstChildControl()
                while child:
                    collect(child, d + 1)
                    child = child.GetNextSiblingControl()
            except Exception:
                log.debug("UIA sibling walk failed", exc_info=True)

        collect(chrome)
        unnamed = [(d, c) for d, c in docs if not (c.Name or "").strip()]
        if unnamed:
            return unnamed[-1][1]
        return docs[-1][1] if docs else None

    def _scan(self):
        """Walk the chat doc once; return (perm_btn, cmd, prompt_ctrl, prompt_label)."""
        if not self._chat_doc:
            return None, "", None, ""

        items: list[tuple[int, str, str, object]] = []

        def walk(ctrl, d=0):
            if d > 12:
                return
            try:
                name  = (ctrl.Name or "").strip()
                ctype = ctrl.ControlTypeName or ""
                if name:
                    items.append((d, ctype, name, ctrl))
            except Exception:
                log.debug("UIA control name/type read failed", exc_info=True)
            try:
                child = ctrl.GetFirstChildControl()
                while child:
                    walk(child, d + 1)
                    child = child.GetNextSiblingControl()
            except Exception:
                log.debug("UIA sibling walk failed", exc_info=True)

        walk(self._chat_doc)

        # ── Cache the chat input EditControl as a free side-effect ────────────
        # This keeps _chat_input_cache warm so submit_to_vscode never calls
        # _find_chat_input (which competes with our walks and times out).
        if self.project_name not in _chat_input_cache:
            for _, ctype, name, ctrl in items:
                if ctype == "EditControl" and name == _CHAT_INPUT_HINT:
                    _chat_input_cache[self.project_name] = ctrl
                    break

        # ── Permission button ──────────────────────────────────────────────────
        perm_btn, perm_cmd = None, ""
        for i, (_, ctype, name, ctrl) in enumerate(items):
            if ctype == "ButtonControl" and "Yes, allow" in name:
                cmd = ""
                hit_prompt = False
                for j in range(max(0, i - 10), i):
                    _, ct2, n2, _ = items[j]
                    if "Allow this" in n2:
                        hit_prompt = True
                        continue
                    if hit_prompt and ct2 == "TextControl" and len(n2) > 2:
                        cmd = n2
                        break
                perm_btn, perm_cmd = ctrl, cmd
                break

        # ── Input prompt EditControl ───────────────────────────────────────────
        prompt_ctrl, prompt_label = None, ""
        for i, (_, ctype, name, ctrl) in enumerate(items):
            if ctype != "EditControl":
                continue
            if name in self._SKIP_PROMPT_NAMES:
                continue
            label = ""
            for j in range(max(0, i - 10), i):
                _, ct2, n2, _ = items[j]
                if ct2 not in ("TextControl", "StaticTextControl"):
                    continue
                n2s = n2.strip().lower()
                if not n2s or n2s in self._SKIP_PROMPT_LABELS or len(n2) < 4:
                    continue
                label = n2.strip()
                break
            if label:
                prompt_ctrl, prompt_label = ctrl, label
                break

        return perm_btn, perm_cmd, prompt_ctrl, prompt_label

    def handle_response(self, text: str) -> bool:
        if not self._pending or not self._allow_btn:
            return False

        words = set(text.lower().strip().split())

        if words & self.ALLOW_WORDS:
            print(f"[Cyrus] → Allowing command ({self.project_name or 'session'})")
            try:
                self._allow_btn.Click()
            except Exception:
                log.warning("Permission allow-button click failed", exc_info=True)
            self._pending   = False
            self._allow_btn = None
            return True

        if words & self.DENY_WORDS:
            print(f"[Cyrus] → Cancelling command ({self.project_name or 'session'})")
            vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
            if vscode.Exists(1):
                try:
                    vscode.SetFocus()
                except Exception:
                    log.debug("VS Code focus failed after deny", exc_info=True)
            pyautogui.press("escape")
            self._pending   = False
            self._allow_btn = None
            return True

        return False

    def handle_prompt_response(self, text: str) -> bool:
        if not self._prompt_pending or not self._prompt_input_ctrl:
            return False

        cancel = {"cancel", "escape", "never mind", "nevermind", "stop", "dismiss", "close"}
        if text.lower().strip() in cancel:
            pyautogui.press("escape")
            print(f"[Cyrus] → Dismissed prompt ({self.project_name or 'session'})")
        else:
            try:
                self._prompt_input_ctrl.SetFocus()
                time.sleep(0.05)
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.02)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.05)
                pyautogui.press("enter")
                print(f"[Cyrus] → Prompt answered: {text!r} ({self.project_name or 'session'})")
            except Exception:
                log.warning("Prompt input failed", exc_info=True)

        self._prompt_pending    = False
        self._prompt_input_ctrl = None
        return True

    def start(self, loop: asyncio.AbstractEventLoop):
        def poll():
            while self._chat_doc is None:
                self._chat_doc = self._find_webview()
                if self._chat_doc is None:
                    time.sleep(2)

            while True:
                time.sleep(self.POLL_SECS)
                try:
                    btn, cmd, p_ctrl, p_label = self._scan()

                    # ── Permission button ──────────────────────────────────────
                    if btn and cmd != self._announced:
                        self._allow_btn  = btn
                        self._pending    = True
                        self._announced  = cmd
                        prefix = f"In {self.project_name}: " if self.project_name else ""
                        prompt = (f"{prefix}Claude wants to run: {cmd}. "
                                  f"Say yes to allow or no to cancel.")
                        print(f"\n[Permission] {prompt}")
                        _stop_speech.set()
                        asyncio.run_coroutine_threadsafe(
                            _speak_urgent(prompt), loop
                        )
                    elif not btn:
                        self._announced = ""
                        if self._pending:
                            self._pending   = False
                            self._allow_btn = None

                    # ── Input prompt ───────────────────────────────────────────
                    if p_ctrl and p_label != self._prompt_announced:
                        self._prompt_input_ctrl = p_ctrl
                        self._prompt_pending    = True
                        self._prompt_announced  = p_label
                        prefix = f"In {self.project_name}: " if self.project_name else ""
                        prompt = f"{prefix}{p_label}"
                        print(f"\n[Input Prompt] {prompt}")
                        _stop_speech.set()
                        asyncio.run_coroutine_threadsafe(
                            _speak_urgent(prompt), loop
                        )
                    elif not p_ctrl:
                        self._prompt_announced = ""
                        if self._prompt_pending:
                            self._prompt_pending    = False
                            self._prompt_input_ctrl = None

                except Exception:
                    log.warning("Permission scan failed, reconnecting", exc_info=True)
                    self._chat_doc = None
                    while self._chat_doc is None:
                        self._chat_doc = self._find_webview()
                        if self._chat_doc is None:
                            time.sleep(2)

        threading.Thread(target=poll, daemon=True).start()


# ── Session Manager ────────────────────────────────────────────────────────────

class SessionManager:
    def __init__(self):
        self._chat_watchers: dict[str, ChatWatcher]       = {}
        self._perm_watchers: dict[str, PermissionWatcher] = {}
        self._aliases:       dict[str, str]               = {}

    @property
    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    @property
    def multi_session(self) -> bool:
        return len(self._chat_watchers) > 1

    @property
    def perm_watchers(self) -> list[PermissionWatcher]:
        return list(self._perm_watchers.values())

    def on_session_switch(self, proj: str, tts_queue, loop):
        cw = self._chat_watchers.get(proj)
        if cw:
            n = cw.flush_pending(tts_queue, loop)
            if n:
                print(f"[Cyrus] Flushed {n} queued response(s) from {proj}")

    def last_response(self, proj: str) -> str:
        cw = self._chat_watchers.get(proj)
        return cw.last_spoken if cw else ""

    def recent_responses(self, proj: str, n: int = 3) -> list[str]:
        cw = self._chat_watchers.get(proj)
        return list(cw._response_history)[-n:] if cw else []

    def rename_alias(self, old_alias: str, new_alias: str, proj: str) -> None:
        """Replace an auto-generated alias with a user-chosen name."""
        self._aliases.pop(old_alias, None)
        self._aliases[new_alias.lower().strip()] = proj

    def _add_session(self, proj: str, subname: str, tts_queue, loop):
        global _whisper_prompt
        alias = _make_alias(proj)
        self._aliases[alias] = proj
        print(f"[Cyrus] Session detected: {proj}  (say \"switch to {alias}\")")
        # Seed Whisper with project names so short words like "dev" are recognised
        names = " ".join(p for p in self._chat_watchers) + f" {proj}"
        _whisper_prompt = f"Cyrus, switch to {names.strip()}."

        def is_active():
            with _active_project_lock:
                return _active_project == proj

        cw = ChatWatcher(project_name=proj, target_subname=subname)
        cw.start(tts_queue, loop, is_active_fn=is_active)
        self._chat_watchers[proj] = cw

        pw = PermissionWatcher(project_name=proj, target_subname=subname)
        pw.start(loop)
        self._perm_watchers[proj] = pw

    def start(self, loop: asyncio.AbstractEventLoop, tts_queue):
        def scan():
            while True:
                try:
                    for proj, subname in _vs_code_windows():
                        if proj not in self._chat_watchers:
                            self._add_session(proj, subname, tts_queue, loop)
                except Exception:
                    log.debug("Recurring session scan failed", exc_info=True)
                time.sleep(5)

        try:
            for proj, subname in _vs_code_windows():
                self._add_session(proj, subname, tts_queue, loop)
        except Exception:
            log.error("Initial session scan failed", exc_info=True)

        if self.multi_session:
            names = " | ".join(f'"{a}"' for a in self._aliases)
            print(f'[Cyrus] {len(self._chat_watchers)} sessions: {names}')
            print('[Cyrus] Say "Cyrus, switch to [name]" to lock routing.')

        threading.Thread(target=scan, daemon=True).start()


# ── VAD loop ──────────────────────────────────────────────────────────────────

def vad_loop(on_utterance, loop: asyncio.AbstractEventLoop):
    model = load_silero_vad()
    ring: deque[tuple[bytes, bool]] = deque(maxlen=SPEECH_RING)
    recording     = False
    frames: list[bytes] = []
    silence_count = 0
    speech_frames = 0   # frames where speech was detected — drives adaptive silence

    with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                           dtype="int16", blocksize=FRAME_SIZE) as stream:
        while not _shutdown.is_set():
            if _mic_muted.is_set() or _user_paused.is_set():
                stream.read(FRAME_SIZE)
                ring.clear()
                if recording:
                    frames.clear()
                    recording     = False
                    silence_count = 0
                time.sleep(0.01)
                continue

            raw, _ = stream.read(FRAME_SIZE)
            frame_bytes = bytes(raw)

            try:
                chunk = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                with torch.no_grad():
                    prob = model(torch.from_numpy(chunk), SAMPLE_RATE).item()
                is_speech = prob > SPEECH_THRESHOLD
            except Exception:
                log.debug("VAD frame processing failed", exc_info=True)
                continue

            if not recording:
                ring.append((frame_bytes, is_speech))
                num_voiced = sum(1 for _, s in ring if s)
                if (len(ring) == ring.maxlen
                        and num_voiced / ring.maxlen >= SPEECH_RATIO):
                    recording     = True
                    frames        = [fb for fb, _ in ring]
                    silence_count = 0
                    speech_frames = 0
                    ring.clear()
                    print("Listening...", flush=True)
            else:
                frames.append(frame_bytes)
                if is_speech:
                    silence_count = 0
                    speech_frames += 1
                else:
                    silence_count += 1

                # Adaptive silence: short pauses end quick commands fast;
                # longer utterances (>1.5 s of speech) get 2.5 s to think mid-sentence.
                adaptive_ring = (SILENCE_RING * 2
                                 if speech_frames * FRAME_MS > 1500
                                 else SILENCE_RING)

                timed_out = len(frames) >= MAX_RECORD_FRAMES
                if silence_count >= adaptive_ring or timed_out:
                    if timed_out:
                        print(" [max duration]", flush=True)
                    raw_audio = b"".join(frames)
                    audio = (np.frombuffer(raw_audio, dtype=np.int16)
                               .astype(np.float32) / 32768.0)
                    recording     = False
                    frames        = []
                    silence_count = 0
                    speech_frames = 0
                    ring.clear()
                    model.reset_states()   # clear GRU state between utterances
                    loop.call_soon_threadsafe(on_utterance, audio)


# ── Speech-to-text ────────────────────────────────────────────────────────────

# Phrases Whisper hallucinates on silence/noise (YouTube training data artefacts)
_HALLUCINATIONS = re.compile(
    r"thank(s| you) for watching"
    r"|see you (in the next|next time|again)"
    r"|don'?t forget to (like|subscribe)"
    r"|like and subscribe"
    r"|please subscribe"
    r"|subtitles by"
    r"|transcribed by",
    re.IGNORECASE,
)

# RMS energy floor — skip transcription if audio is essentially silence
_MIN_RMS = 0.004   # ~-48 dBFS; tune up if hallucinations persist

# Leading filler words to strip before forwarding to Claude Code
_FILLER_RE = re.compile(
    r"^(?:uh+|um+|er+|so|okay|ok|right|hey|please|can you|could you|would you)\s+",
    re.IGNORECASE,
)


def _strip_fillers(text: str) -> str:
    """Strip leading filler words — handles stacked fillers like 'uh um fix it'."""
    prev = None
    while prev != text:
        prev = text
        text = _FILLER_RE.sub("", text).strip()
    return text


def transcribe(whisper_model: WhisperModel, audio: np.ndarray) -> str:
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < _MIN_RMS:
        return ""   # too quiet — don't feed silence to Whisper

    segments, _ = whisper_model.transcribe(audio, language="en",
                                           beam_size=1, best_of=1,
                                           initial_prompt=_whisper_prompt)
    text = " ".join(s.text for s in segments if s.no_speech_prob < 0.6).strip()

    if _HALLUCINATIONS.search(text):
        print(f"(hallucination filtered: '{text[:60]}')")
        return ""

    return text


# ── Submit to VS Code ─────────────────────────────────────────────────────────


def _find_chat_input(target_subname: str = "") -> object:
    subname = target_subname or VSCODE_TITLE
    vscode  = auto.WindowControl(searchDepth=1, SubName=subname)
    if not vscode.Exists(2):
        return None

    ctrl = vscode.EditControl(searchDepth=12, Name=_CHAT_INPUT_HINT)
    if ctrl.Exists(2):
        return ctrl

    chrome = vscode.PaneControl(searchDepth=12,
                                ClassName="Chrome_RenderWidgetHostHWND")
    if not chrome.Exists(2):
        return None

    found: list[tuple[int, object]] = []

    def _walk(ctrl, d=0):
        if d > 15:
            return
        try:
            if ctrl.ControlTypeName == "EditControl":
                found.append((d, ctrl))
        except Exception:
            log.debug("UIA EditControl check failed", exc_info=True)
        try:
            child = ctrl.GetFirstChildControl()
            while child:
                _walk(child, d + 1)
                child = child.GetNextSiblingControl()
        except Exception:
            log.debug("UIA sibling walk failed", exc_info=True)

    _walk(chrome)

    if not found:
        return None
    for _, c in found:
        if (c.Name or "") in (_CHAT_INPUT_HINT, "Message input"):
            return c
    return min(found, key=lambda x: x[0])[1]


def submit_to_vscode(text: str) -> bool:
    global _chat_input_cache, _vscode_win_cache

    with _active_project_lock:
        proj = _active_project

    target_sub = f"{proj} - Visual Studio Code" if proj else VSCODE_TITLE

    # ── Activate VS Code window (cached) ──────────────────────────────────────
    # Validate by title, not isActive — window is almost never "active" while
    # the user is speaking to Cyrus, so isActive would defeat the cache entirely.
    win = _vscode_win_cache.get(proj)
    if win is not None:
        try:
            if VSCODE_TITLE not in (win.title or ""):
                raise ValueError("wrong window")
        except Exception:
            log.debug("Cached window handle stale", exc_info=True)
            win = None
            _vscode_win_cache.pop(proj, None)

    if win is None:
        matches = [w for w in gw.getAllWindows()
                   if VSCODE_TITLE in (w.title or "")
                   and (not proj or proj in w.title)]
        if not matches:
            matches = [w for w in gw.getAllWindows() if VSCODE_TITLE in (w.title or "")]
        if not matches:
            print("[!] VS Code window not found.")
            return False
        win = matches[0]
        _vscode_win_cache[proj] = win

    try:
        win.activate()
        time.sleep(0.15)   # give VS Code time to foreground and update UIA tree
    except Exception:
        log.warning("VS Code window activation failed", exc_info=True)

    # ── Use cached chat input — no Exists() check, just try it ────────────────
    cached = _chat_input_cache.get(proj)
    if cached is not None:
        try:
            cached.SetFocus()
            time.sleep(0.03)
            cached.Click()
            time.sleep(0.03)
        except Exception:
            log.debug("Cached chat input click failed", exc_info=True)
            # Stale handle — fall through to fresh search
            cached = None
            _chat_input_cache.pop(proj, None)

    if cached is None:
        cached = _find_chat_input(target_sub)
        if not cached:
            print("[!] Claude chat input not found — skipping to avoid typing in wrong window.")
            return False
        _chat_input_cache[proj] = cached
        try:
            cached.SetFocus()
            time.sleep(0.03)
            cached.Click()
            time.sleep(0.03)
        except Exception:
            log.error("Chat input click failed", exc_info=True)
            _chat_input_cache.pop(proj, None)
            return False

    saved = ""
    try:
        saved = pyperclip.paste()
    except Exception:
        log.debug("Clipboard save failed", exc_info=True)

    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.05)
    pyautogui.press("enter")

    time.sleep(0.05)
    try:
        pyperclip.copy(saved)
    except Exception:
        log.debug("Clipboard restore failed", exc_info=True)

    return True


# ── Response cleanup for speech ───────────────────────────────────────────────

def clean_for_speech(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "See the chat for the code.", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\n[-*_]{3,}\n", " ", text)
    text = re.sub(r"\n\s*[-*•]\s+", ". ", text)
    text = re.sub(r"\n\s*\d+\.\s+", ". ", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    words = text.split()
    if len(words) > MAX_SPEECH_WORDS:
        text = " ".join(words[:MAX_SPEECH_WORDS]) + ". See the chat for the full response."
    return text.strip()


# ── Text-to-speech ────────────────────────────────────────────────────────────

async def speak(text: str) -> None:
    """Speak text via Kokoro (local) or Edge TTS (fallback). Mic muted during playback."""
    _stop_speech.clear()
    _tts_active.set()
    _mic_muted.set()
    try:
        await asyncio.wait_for(_speak_save(text), timeout=25.0)
    except asyncio.TimeoutError:
        print("[Cyrus] TTS timed out — aborting playback")
        _stop_speech.set()   # signal _speak_kokoro's _play() loop to exit
    finally:
        _tts_active.clear()
        await asyncio.sleep(0.25)   # brief echo-decay guard; VAD + RMS gate cover the rest
        _mic_muted.clear()


async def _speak_save(text: str) -> None:
    """Synthesise and play text. Uses Kokoro if loaded, otherwise falls back to Edge TTS."""
    if _kokoro is not None:
        await _speak_kokoro(text)
    else:
        await _speak_edge(text)


async def _speak_kokoro(text: str) -> None:
    """Kokoro local TTS — ~80–150 ms on GPU, no network, no temp file."""
    print(f"[TTS] generating {len(text)} chars...")
    samples, sr = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: _kokoro.create(text, voice=TTS_VOICE, speed=TTS_SPEED, lang="en-us"),
    )
    print(f"[TTS] {len(samples)} samples at {sr}Hz — playing")

    def _play():
        chunk = 1024
        with sd.OutputStream(samplerate=sr, channels=1, dtype="float32") as stream:
            for i in range(0, len(samples), chunk):
                if _stop_speech.is_set():
                    break
                stream.write(samples[i:i + chunk].reshape(-1, 1))

    await asyncio.get_event_loop().run_in_executor(None, _play)


async def _speak_edge(text: str) -> None:
    """Edge TTS fallback — requires network + ffmpeg. Used when Kokoro is not loaded."""
    import subprocess
    import tempfile
    import edge_tts
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name
    try:
        await edge_tts.Communicate(text, "en-US-BrianNeural",
                                   rate="-5%", pitch="-5Hz").save(tmp_path)
        if not os.path.getsize(tmp_path):
            return

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["ffmpeg", "-loglevel", "quiet",
                 "-i", tmp_path,
                 "-f", "s16le", "-ar", "24000", "-ac", "1", "-"],
                capture_output=True,
            ),
        )
        pcm = result.stdout
        if not pcm:
            return

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        def _play():
            chunk = 1024
            with sd.OutputStream(samplerate=24000, channels=1, dtype="float32") as stream:
                for i in range(0, len(audio), chunk):
                    if _stop_speech.is_set():
                        break
                    stream.write(audio[i:i + chunk])

        await asyncio.get_event_loop().run_in_executor(None, _play)
    finally:
        try:
            os.unlink(tmp_path)
        except (PermissionError, FileNotFoundError):
            pass


# ── Startup sequence ─────────────────────────────────────────────────────────

async def startup_sequence(session_mgr) -> None:
    windows = _vs_code_windows()

    if not windows:
        await speak("Cyrus is online. No VS Code sessions detected.")
    elif len(windows) == 1:
        await speak(f"Cyrus is online. Session: {_make_alias(windows[0][0])}.")
    else:
        names = ", ".join(_make_alias(p) for p, _ in windows)
        await speak(f"Cyrus is online. {len(windows)} sessions: {names}.")

    play_listen_chime()
    print("[Cyrus] Listening for wake word...")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    global _tts_queue
    global _active_project, _project_locked, _conversation_active
    global _whisper_executor, _remote_url, _remote_ws, _kokoro

    parser = argparse.ArgumentParser(description="Cyrus — voice layer for Claude Code")
    parser.add_argument(
        "--remote", metavar="URL",
        help="WebSocket URL of a remote Cyrus brain, e.g. ws://192.168.1.10:8765",
    )
    args = parser.parse_args()

    if args.remote:
        _remote_url = args.remote
        try:
            import websockets as _ws_lib
            _remote_ws = await _ws_lib.connect(_remote_url)
            print(f"[Cyrus] Connected to remote brain at {_remote_url}")
        except Exception:
            log.warning("Remote brain connection failed, using local routing", exc_info=True)
            _remote_url = ""

    if _CUDA:
        print(f"[Cyrus] GPU: {_GPU_NAME}")
    else:
        print("[Cyrus] No CUDA/ROCm GPU detected — Whisper on CPU")
    print(f"Loading Whisper {WHISPER_MODEL} on {WHISPER_DEVICE}...")
    whisper_model = WhisperModel(WHISPER_MODEL,
                                 device=WHISPER_DEVICE,
                                 compute_type=WHISPER_COMPUTE_TYPE)

    # ── Kokoro TTS ──────────────────────────────────────────────────────────────
    if os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_VOICES):
        try:
            from kokoro_onnx import Kokoro as _KokoroClass
            import onnxruntime as _ort
            _ort.set_default_logger_severity(3)   # suppress WARNING-level Conv fallback noise
            _providers = []
            if _CUDA:
                _providers.append(("CUDAExecutionProvider",
                                   {"cudnn_conv_algo_search": "DEFAULT"}))
            _providers.append("CPUExecutionProvider")
            _session = _ort.InferenceSession(KOKORO_MODEL, providers=_providers)
            _kokoro = _KokoroClass.from_session(_session, KOKORO_VOICES)
            _active_providers = _session.get_providers()
            _tts_device = "GPU" if "CUDAExecutionProvider" in _active_providers else "CPU"
            print(f"[Cyrus] Kokoro TTS loaded ({_tts_device}) — voice: {TTS_VOICE}")
        except Exception:
            log.warning("Kokoro TTS load failed, using Edge TTS fallback", exc_info=True)
    else:
        print("[Cyrus] Kokoro model files not found — using Edge TTS fallback")
        print(f"         Expected: {KOKORO_MODEL}")


    pygame.mixer.init()

    loop = asyncio.get_event_loop()

    # Dedicated thread pool — CPU-bound (Whisper)
    _whisper_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")

    # Global serial TTS queue
    _tts_queue = asyncio.Queue()

    # VAD → utterance queue
    utterance_queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
    threading.Thread(
        target=vad_loop,
        args=(utterance_queue.put_nowait, loop),
        daemon=True,
    ).start()

    # Session manager
    session_mgr = SessionManager()
    session_mgr.start(loop, _tts_queue)

    # Set initial active project to the first detected VS Code window
    first_windows = _vs_code_windows()
    if first_windows:
        with _active_project_lock:
            _active_project = first_windows[0][0]

    # Serial TTS worker
    asyncio.create_task(tts_worker(session_mgr))

    # Window-focus tracker
    threading.Thread(
        target=_start_active_tracker,
        args=(session_mgr, _tts_queue, loop),
        daemon=True,
    ).start()

    # Hotkeys
    def toggle_pause():
        if _user_paused.is_set():
            _user_paused.clear()
            print("[Cyrus resumed]")
        else:
            _user_paused.set()
            print(f"[Cyrus paused — press {KEY_PAUSE.upper()} to resume]")

    def stop_speech():
        _stop_speech.set()
        asyncio.run_coroutine_threadsafe(drain_tts_queue(), loop)

    def read_clipboard():
        try:
            text = pyperclip.paste().strip()
        except Exception:
            log.debug("Clipboard read failed", exc_info=True)
            text = ""
        if text:
            asyncio.run_coroutine_threadsafe(_tts_queue.put(("", text)), loop)
        else:
            print("[Clipboard empty]")

    keyboard.add_hotkey(KEY_PAUSE,     toggle_pause)
    keyboard.add_hotkey(KEY_STOP,      stop_speech)
    keyboard.add_hotkey(KEY_READ_CLIP, read_clipboard)

    print("[Cyrus] F9 pause  |  F7 stop+clear  |  F8 clipboard  |  Ctrl+C exit")

    # Interactive startup — verify, greet, detect sessions, assign names
    await startup_sequence(session_mgr)

    # Discard any audio captured during startup TTS (Whisper hallucinates on speaker echo)
    while not utterance_queue.empty():
        try:
            utterance_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    while True:
        audio = await utterance_queue.get()

        # Drain any stale utterances that built up while we were processing —
        # keep only the most recent one so we never fall behind.
        while not utterance_queue.empty():
            try:
                audio = utterance_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        print("Transcribing...", end=" ", flush=True)
        text = await loop.run_in_executor(_whisper_executor, transcribe, whisper_model, audio)

        if not text:
            print("(nothing heard)")
            continue

        # While TTS is playing: only a wake word can interrupt.
        # Any other audio is assumed to be speaker echo — discard it.
        if _tts_active.is_set() or _tts_pending.is_set():
            fw = text.lower().strip().split()
            has_wake = any(w.rstrip(",.!?") in WAKE_WORDS for w in fw)
            if not has_wake:
                continue   # echo or background noise
            _stop_speech.set()  # interrupt current playback
            _tts_pending.clear()
            await asyncio.sleep(0.15)  # let _speak_save stop cleanly

        # Permission dialog — binary response, no LLM needed
        handled = False
        for pw in session_mgr.perm_watchers:
            if pw.is_pending:
                if pw.handle_response(text):
                    handled = True
                    break
        if handled:
            continue

        # Input-box prompt — strip wake word if present, route text directly
        for pw in session_mgr.perm_watchers:
            if pw.prompt_pending:
                ws = text.lower().strip().split()
                if ws and ws[0].rstrip(",.!?") in WAKE_WORDS:
                    parts = text.split(None, 1)
                    text  = parts[1].lstrip(", ").strip() if len(parts) > 1 else text
                if pw.handle_prompt_response(text):
                    handled = True
                    break
        if handled:
            continue

        # Wake word check — skipped when Cyrus is mid-conversation
        words = text.lower().strip().split()
        first = words[0].rstrip(",.!?") if words else ""

        if _conversation_active:
            # In conversation — no wake word required.
            # If the user said it anyway, strip it so it doesn't confuse the LLM.
            if first in WAKE_WORDS:
                rest = text.split(None, 1)
                text = rest[1].lstrip(", ").strip() if len(rest) > 1 else ""
            if not text:
                continue
            print(f"[conversation] heard: '{text}'")
        else:
            if first not in WAKE_WORDS:
                print(f"(ignored — say 'Cyrus, ...' | heard: '{first}')")
                continue
            rest = text.split(None, 1)
            text = rest[1].lstrip(", ").strip() if len(rest) > 1 else ""
            if not text:
                # Wake word with no command — user likely paused between wake word
                # and the actual command (common when emphasising the wake word).
                # Wait up to 3 s for the next VAD chunk and treat it as the command.
                print("(wake word — listening for command...)", end=" ", flush=True)
                play_listen_chime()
                try:
                    follow_audio = await asyncio.wait_for(utterance_queue.get(), timeout=6.0)
                    text = await loop.run_in_executor(
                        _whisper_executor, transcribe, whisper_model, follow_audio
                    )
                    # Strip a repeated wake word if the user said it again
                    fw = text.lower().strip().split()
                    if fw and fw[0].rstrip(",.!?") in WAKE_WORDS:
                        parts = text.split(None, 1)
                        text  = parts[1].lstrip(", ").strip() if len(parts) > 1 else ""
                    if not text:
                        print("(no command heard)")
                        continue
                    print(f"'{text}'")
                except asyncio.TimeoutError:
                    print("(no command heard)")
                    continue

        # ── Route utterance ───────────────────────────────────────────────────
        # Fast local pre-filter (commands never need the remote brain)
        decision = _fast_command(text)

        if decision is None:
            with _active_project_lock:
                proj = _active_project

            if _remote_url:
                # Remote mode: send text + context to the brain, fall back locally
                last_resp = session_mgr.last_response(proj)
                decision  = await _remote_route(text, proj, last_resp)

            if decision is None:
                # Local routing (default, or remote fallback)
                if _is_answer_request(text):
                    resp = session_mgr.last_response(proj) or "I don't have a recent response to share."
                    words = resp.split()
                    if len(words) > 30:
                        resp = " ".join(words[:30]) + ". See the chat for more."
                    decision = {"action": "answer", "spoken": resp, "message": "", "command": {}}
                else:
                    decision = {"action": "forward", "message": text, "spoken": "", "command": {}}

        action = decision.get("action", "forward")

        if action == "answer":
            spoken = decision.get("spoken", "")
            if spoken:
                print(f"\n[Cyrus answers] {spoken[:80]}{'...' if len(spoken) > 80 else ''}")
                asyncio.run_coroutine_threadsafe(_tts_queue.put(("", spoken)), loop)
                _conversation_active = False  # require wake word again to prevent TTS echo loop
            else:
                _conversation_active = False

        elif action == "command":
            ctype = decision.get("command", {}).get("type", "")
            spoken = decision.get("spoken", "")
            print(f"\n[Cyrus command] {ctype}")
            _execute_cyrus_command(ctype, decision.get("command", {}),
                                   spoken, session_mgr, loop)
            # Stay in conversation only if Cyrus asked a follow-up question
            _conversation_active = spoken.rstrip().endswith("?")

        else:  # "forward"
            # Remote brain already appended VOICE_HINT; local mode has not
            raw_msg = _strip_fillers(decision.get("message") or text)
            message = raw_msg if _remote_url else raw_msg + VOICE_HINT
            with _active_project_lock:
                proj = _active_project
            print(f"\nYou [{proj or 'VS Code'}]: {message}")
            try:
                submitted = await asyncio.wait_for(
                    loop.run_in_executor(None, submit_to_vscode, message),
                    timeout=8.0,
                )
            except asyncio.TimeoutError:
                print("→ Submit timed out — VS Code UIA unresponsive.\n")
                submitted = False
            if not submitted:
                print("→ Could not find VS Code window.\n")
            else:
                play_chime()   # instant "I got it" signal while Claude processes
            # Sent to Claude Code — conversation with Cyrus ends
            _conversation_active = False


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        print("\nCyrus signing off.")
        _shutdown.set()       # tells vad_loop to exit its while-loop cleanly
        _stop_speech.set()    # aborts any in-progress TTS playback
        _mic_muted.set()      # stops VAD from processing new frames
        try:
            pygame.mixer.stop()   # stop all playing sounds before tearing down SDL
            pygame.mixer.quit()
        except Exception:
            log.debug("Pygame mixer cleanup failed", exc_info=True)
        try:
            sd.stop()             # abort all PortAudio streams
        except Exception:
            log.debug("Sounddevice cleanup failed", exc_info=True)
        if _whisper_executor is not None:
            _whisper_executor.shutdown(wait=False, cancel_futures=True)
        try:
            keyboard.unhook_all()
        except Exception:
            log.debug("Keyboard unhook failed", exc_info=True)
        # Force-exit: bypasses Python's C-extension destructor sequence which
        # crashes on Windows when audio threads (PortAudio/SDL) are still live.
        os._exit(0)
