"""
cyrus_brain.py — Service 2: Logic / VS Code Watcher

Manages Claude Code sessions, routes utterances, and reads responses aloud.
Owns all VS Code UIA interaction. Has no audio hardware dependency.

Usage:
    python cyrus_brain.py [--host HOST] [--port PORT]

Restart freely during development — cyrus_voice.py stays warm and reconnects.

Protocol (line-delimited JSON):
  Brain → Voice:  {"type": "speak",         "text": "...", "project": "..."}
                  {"type": "chime"}
                  {"type": "listen_chime"}
                  {"type": "stop_speech"}
                  {"type": "pause"}
                  {"type": "whisper_prompt", "text": "..."}
                  {"type": "status",         "msg":  "..."}
  Voice → Brain:  {"type": "utterance",     "text": "...", "during_tts": false}
                  {"type": "tts_start"}
                  {"type": "tts_end"}
"""

import os
import re
import json
import asyncio
import threading
import time
import argparse
import queue as _stdlib_queue
import socket

import comtypes
import pyautogui
import pyperclip
import pygetwindow as gw
import uiautomation as auto
from collections import deque

# ── Configuration ──────────────────────────────────────────────────────────────

BRAIN_HOST       = "0.0.0.0"
BRAIN_PORT       = 8766
HOOK_PORT        = 8767   # Claude Code Stop hook sends here
VSCODE_TITLE     = "Visual Studio Code"
_CHAT_INPUT_HINT = "Message input"
MAX_SPEECH_WORDS = 50

WAKE_WORDS = {"cyrus", "sire", "sirius", "serious", "cyprus",
              "virus", "sirus", "cirus", "sy", "sir", "sarush", "surus",
              "saras", "serus", "situs", "cirrus", "serous", "ceres"}

VOICE_HINT = ("\n\n[Voice mode: keep explanations to 2-3 sentences. "
              "For code changes show only the modified section, not the full file.]")

# ── Shared state ───────────────────────────────────────────────────────────────

_active_project:      str            = ""
_active_project_lock: threading.Lock = threading.Lock()
_chat_input_cache:    dict           = {}   # kept for PermissionWatcher internal use
_chat_input_coords:   dict           = {}   # proj → (cx, cy) pixel coords, cross-thread safe
_vscode_win_cache:    dict           = {}

_project_locked:      bool           = False
_project_locked_lock: threading.Lock = threading.Lock()

_conversation_active: bool = False
_whisper_prompt:      str  = "Cyrus,"
_tts_active_remote:   bool = False   # True while voice service is playing TTS

# asyncio queues — set in main()
_speak_queue:     asyncio.Queue = None   # (project, text) → sent to voice
_utterance_queue: asyncio.Queue = None   # utterances received from voice

# Dedicated submit thread queue — all VS Code UIA writes happen on one thread
_submit_request_queue: _stdlib_queue.Queue = _stdlib_queue.Queue()

# Voice writer — set when voice connects, None when disconnected
_voice_writer: asyncio.StreamWriter = None
_voice_lock = asyncio.Lock()

auto.uiautomation.SetGlobalSearchTimeout(2)
pyautogui.FAILSAFE = False

# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_project(title: str) -> str:
    t = title.replace(" - Visual Studio Code", "").lstrip("● ").strip()
    parts = [p.strip() for p in t.split(" - ") if p.strip()]
    return parts[-1] if parts else "VS Code"


def _make_alias(proj: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", proj.lower())).strip()


def _resolve_project(query: str, aliases: dict) -> str | None:
    q = query.lower().strip()
    if q in aliases:
        return aliases[q]
    for alias, proj in aliases.items():
        if q in alias or alias in q:
            return proj
    return None


def _vs_code_windows() -> list[tuple[str, str]]:
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


_FILLER_RE = re.compile(
    r"^(?:uh+|um+|er+|so|okay|ok|right|hey|please|can you|could you|would you)\s+",
    re.IGNORECASE,
)


def _strip_fillers(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _FILLER_RE.sub("", text).strip()
    return text


# ── Send to voice ──────────────────────────────────────────────────────────────

async def _send(msg: dict) -> None:
    """Send one JSON message to voice. Fire-and-forget — never raises."""
    global _voice_writer
    if _voice_writer is None:
        return
    try:
        async with _voice_lock:
            _voice_writer.write((json.dumps(msg) + "\n").encode())
            await _voice_writer.drain()
    except Exception:
        _voice_writer = None


def _send_threadsafe(msg: dict, loop: asyncio.AbstractEventLoop) -> None:
    """Thread-safe wrapper for _send, callable from background threads."""
    asyncio.run_coroutine_threadsafe(_send(msg), loop)


# ── Speak helpers (used by background threads via threadsafe wrapper) ──────────

async def _speak_worker() -> None:
    """Consume speak queue and forward to voice."""
    while True:
        project, text = await _speak_queue.get()
        await _send({"type": "speak", "text": text, "project": project})


async def _speak_urgent(text: str) -> None:
    """Interrupt current TTS and speak immediately (e.g. permission dialogs)."""
    # Drain the speak queue
    while not _speak_queue.empty():
        try:
            _speak_queue.get_nowait()
        except Exception:
            break
    await _send({"type": "stop_speech"})
    await _send({"type": "speak", "text": text, "project": ""})


def play_chime(loop: asyncio.AbstractEventLoop = None) -> None:
    """Signal brain's event loop to send a chime to voice."""
    if loop is not None:
        _send_threadsafe({"type": "chime"}, loop)


def play_listen_chime(loop: asyncio.AbstractEventLoop = None) -> None:
    if loop is not None:
        _send_threadsafe({"type": "listen_chime"}, loop)


# ── Routing helpers ────────────────────────────────────────────────────────────

_ANSWER_RE = re.compile(
    r"\b(recap|summarize?|summary)\b"
    r"|what\s+(did|was|were)\b.{0,40}\b(say|said|respond|answered?|told?|reply|replied)\b"
    r"|what\s+(you|claude|cyrus|it)\s+said\b"
    r"|\b(last\s+response|last\s+reply)\b"
    r"|\brepeat\s+(that|what\s+(you|claude|cyrus|it)\s+said)\b",
    re.IGNORECASE,
)


def _is_answer_request(text: str) -> bool:
    return bool(_ANSWER_RE.search(text))


def _fast_command(text: str) -> dict | None:
    t = text.lower().strip().rstrip(".,!?")

    if re.fullmatch(r"pause|resume|stop listening|start listening", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "pause"}}

    if re.fullmatch(r"(un ?lock|auto|follow focus|auto(matic)? routing)", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "unlock"}}

    if re.search(r"\b(which|what)\b.{0,20}\b(project|session)\b", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "which_project"}}

    if re.fullmatch(r"(last|repeat|replay|again).{0,30}(message|response|said)?", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "last_message"}}

    m = (re.match(r"(?:switch(?:ed)?(?: to)?|use|go to|open|activate)\s+(.+)", t)
         or re.match(r"make\s+(.+?)\s+(?:the\s+)?active", t)
         or re.match(r"(?:set|change)\s+(?:active\s+)?(?:project|session)\s+to\s+(.+)", t))
    if m:
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "switch_project", "project": m.group(1).strip()}}

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
                            session_mgr, loop: asyncio.AbstractEventLoop) -> None:
    global _active_project, _project_locked

    if ctype == "switch_project":
        target = _resolve_project(cmd.get("project", ""), session_mgr.aliases)
        if target:
            with _active_project_lock:
                _active_project = target
            with _project_locked_lock:
                _project_locked = True
            session_mgr.on_session_switch(target, loop)
            spoken = spoken or f"Switched to {target}. Routing locked."
            print(f"[Brain] {spoken}")
        else:
            spoken = f"No session matching '{cmd.get('project', '')}' found."
            print(f"[Brain] {spoken}")

    elif ctype == "unlock":
        with _project_locked_lock:
            _project_locked = False
        spoken = spoken or "Following window focus."
        print("[Brain] Routing unlocked.")

    elif ctype == "which_project":
        with _active_project_lock:
            proj_name = _active_project
        with _project_locked_lock:
            locked = _project_locked
        status = "locked" if locked else "following focus"
        spoken = spoken or f"Active project: {proj_name or 'none'}, {status}."
        print(f"[Brain] {spoken}")

    elif ctype == "last_message":
        with _active_project_lock:
            proj_name = _active_project
        resp = session_mgr.last_response(proj_name)
        if resp:
            asyncio.run_coroutine_threadsafe(
                _speak_queue.put((proj_name, resp)), loop
            )
            return
        else:
            spoken = spoken or f"No recorded response for {proj_name or 'this session'}."
            print(f"[Brain] {spoken}")

    elif ctype == "rename_session":
        new_name = cmd.get("new", "").strip()
        old_hint = cmd.get("old", "").strip()
        with _active_project_lock:
            active = _active_project
        proj = _resolve_project(old_hint, session_mgr.aliases) if old_hint else active
        if proj and new_name:
            old_alias = next((a for a, p in session_mgr.aliases.items() if p == proj), proj)
            session_mgr.rename_alias(old_alias, new_name, proj)
            spoken = spoken or f"Renamed to '{new_name}'."
            print(f"[Brain] {proj} → alias '{new_name}'")
        else:
            spoken = spoken or "Could not find that session to rename."
        print(f"[Brain] {spoken}")

    elif ctype == "pause":
        # Delegate to voice service
        asyncio.run_coroutine_threadsafe(_send({"type": "pause"}), loop)
        return

    if spoken:
        asyncio.run_coroutine_threadsafe(_speak_queue.put(("", spoken)), loop)


# ── Chat Watcher ───────────────────────────────────────────────────────────────

class ChatWatcher:
    """
    Polls a Claude Code chat webview via UIA.
    When a new response stabilises, sends it to voice for TTS.
    """
    POLL_SECS   = 0.5
    STABLE_SECS = 1.2

    _STOP = {"Edit automatically", "Show command menu (/)",
             "ctrl esc to focus or unfocus Claude", "Message input"}
    _SKIP = {"Thinking", "Message actions", "Copy code to clipboard",
             "Stop", "Regenerate", "tasks", "New session", "Ask before edits"}

    def __init__(self, project_name: str = "", target_subname: str = ""):
        self._chat_doc               = None
        self._last_text              = ""
        self._last_change            = 0.0
        self._last_spoken            = ""
        self._new_submission_pending = False
        self._pending_queue: list[str]  = []
        self._response_history: deque   = deque(maxlen=10)
        self.project_name            = project_name
        self._target_sub             = target_subname or VSCODE_TITLE

    @property
    def last_spoken(self) -> str:
        return self._last_spoken

    def flush_pending(self, loop: asyncio.AbstractEventLoop) -> int:
        items = self._pending_queue[:]
        self._pending_queue.clear()
        for text in items:
            asyncio.run_coroutine_threadsafe(_speak_queue.put((self.project_name, text)), loop)
        return len(items)

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
                pass
            try:
                child = ctrl.GetFirstChildControl()
                while child:
                    collect(child, d + 1)
                    child = child.GetNextSiblingControl()
            except Exception:
                pass

        collect(chrome)
        unnamed = [(d, c) for d, c in docs if not (c.Name or "").strip()]
        if unnamed:
            return unnamed[-1][1]
        return docs[-1][1] if docs else None

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
            pass
        try:
            child = ctrl.GetFirstChildControl()
            while child:
                self._walk(child, depth + 1, max_depth, out)
                child = child.GetNextSiblingControl()
        except Exception:
            pass
        return out

    def _extract_response(self, results):
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
                break
            if text in self._SKIP or len(text) < 4:
                continue
            if ctype not in ("TextControl", "ListItemControl"):
                continue
            if text not in seen and not any(text in s for s in seen if len(s) > len(text)):
                seen.add(text)
                parts.append(text)

        return " ".join(parts)

    def start(self, loop: asyncio.AbstractEventLoop, is_active_fn=None):
        if is_active_fn is None:
            is_active_fn = lambda: True

        def poll():
            comtypes.CoInitializeEx()
            while self._chat_doc is None:
                self._chat_doc = self._find_webview()
                if self._chat_doc is None:
                    time.sleep(2)
            label = f"[{self.project_name}] " if self.project_name else ""
            print(f"[Brain] {label}Connected to Claude Code chat panel.")

            # Populate chat input coords early — direct EditControl search
            if self.project_name not in _chat_input_coords:
                try:
                    vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
                    win_found = vscode.Exists(1)
                    if win_found:
                        ctrl = vscode.EditControl(searchDepth=20, Name=_CHAT_INPUT_HINT)
                        if ctrl.Exists(2):
                            r = ctrl.BoundingRectangle
                            if r.width() > 0:
                                _chat_input_coords[self.project_name] = (
                                    (r.left + r.right) // 2,
                                    (r.top + r.bottom) // 2,
                                )
                                print(f"[Brain] {label}Chat input coords cached: "
                                      f"{_chat_input_coords.get(self.project_name)}")
                except Exception as e:
                    print(f"[Brain] {label}Coords cache error: {e}")

            seed = ""
            for _ in range(6):
                try:
                    seed = self._extract_response(self._walk(self._chat_doc))
                    if seed:
                        break
                except Exception:
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

                    # Detect new user submission via Message actions count
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
                        if self._new_submission_pending:
                            self._new_submission_pending = False
                            self._last_spoken = ""
                    elif response and response != self._last_spoken:
                        if now - self._last_change >= self.STABLE_SECS:
                            self._last_spoken = response
                            # Hook already spoke this response — suppress ChatWatcher
                            if now < getattr(self, "_hook_spoken_until", 0):
                                continue
                            if not seed:
                                seed = response
                                continue
                            spoken  = clean_for_speech(response)
                            self._response_history.append(spoken)
                            preview = spoken[:80] + ("..." if len(spoken) > 80 else "")
                            print(f"\nCyrus [{self.project_name or 'Claude'}]: {preview}")

                            if is_active_fn():
                                asyncio.run_coroutine_threadsafe(
                                    _speak_queue.put((self.project_name, spoken)), loop
                                )
                            else:
                                self._pending_queue.append(spoken)
                                _send_threadsafe({"type": "chime"}, loop)
                                print(f"[queued: {self.project_name}] "
                                      f"{len(self._pending_queue)} message(s) waiting")

                except Exception:
                    self._chat_doc = None
                    while self._chat_doc is None:
                        self._chat_doc = self._find_webview()
                        if self._chat_doc is None:
                            time.sleep(2)

        threading.Thread(target=poll, daemon=True).start()


# ── Permission Watcher ─────────────────────────────────────────────────────────

class PermissionWatcher:
    """
    Polls Claude Code's chat webview for permission dialogs and input prompts.
    """
    POLL_SECS   = 0.3
    ALLOW_WORDS = {"yes", "allow", "sure", "ok", "okay", "proceed", "yep", "yeah", "go"}
    DENY_WORDS  = {"no", "deny", "cancel", "stop", "nope", "reject"}

    _SKIP_PROMPT_NAMES  = {_CHAT_INPUT_HINT, ""}
    _SKIP_PROMPT_LABELS = {"search", "find", "replace", "filter", "go to line"}

    def __init__(self, project_name: str = "", target_subname: str = ""):
        self._chat_doc          = None
        self._vscode_win        = None   # cached VS Code WindowControl
        self._pending           = False
        self._allow_btn         = None
        self._announced         = ""
        self._prompt_pending    = False
        self._prompt_input_ctrl = None
        self._prompt_announced  = ""
        self.project_name       = project_name
        self._target_sub        = target_subname or VSCODE_TITLE

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
        self._vscode_win = vscode
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
                pass
            try:
                child = ctrl.GetFirstChildControl()
                while child:
                    collect(child, d + 1)
                    child = child.GetNextSiblingControl()
            except Exception:
                pass

        collect(chrome)
        unnamed = [(d, c) for d, c in docs if not (c.Name or "").strip()]
        if unnamed:
            return unnamed[-1][1]
        return docs[-1][1] if docs else None

    def _scan_window_for_permission(self):
        """
        Scan the VS Code workbench Chrome pane for the permission dialog.
        Uses the monaco-aria-container live region as a reliable signal —
        it shows 'requesting permission' when a permission dialog is active.
        Returns (tool_name, found: bool).
        """
        try:
            vscode = self._vscode_win
            if vscode is None or not vscode.Exists(0):
                vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
                if not vscode.Exists(1):
                    return "", False
                self._vscode_win = vscode

            # Find the Chrome pane (entire VS Code workbench is one Chrome widget)
            chrome = vscode.PaneControl(searchDepth=20,
                                        ClassName="Chrome_RenderWidgetHostHWND")
            if not chrome.Exists(1):
                return "", False

            aria_text  = ""
            found_perm = False

            def walk(ctrl, d=0):
                nonlocal aria_text, found_perm
                if d > 8:
                    return
                try:
                    name = (ctrl.Name or "").strip()
                    cls  = ctrl.ClassName or ""
                    # ARIA live region — VS Code announces permission dialogs here
                    if cls == "monaco-alert" and "requesting permission" in name.lower():
                        aria_text  = name
                        found_perm = True
                    # Also catch if "Allow this" appears directly at shallow depth
                    if "Allow this" in name:
                        found_perm = True
                        if not aria_text:
                            aria_text = name
                except Exception:
                    pass
                try:
                    child = ctrl.GetFirstChildControl()
                    while child:
                        walk(child, d + 1)
                        child = child.GetNextSiblingControl()
                except Exception:
                    pass

            walk(chrome)
            return aria_text, found_perm
        except Exception:
            return "", False

    def _scan(self):
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
                pass
            try:
                child = ctrl.GetFirstChildControl()
                while child:
                    walk(child, d + 1)
                    child = child.GetNextSiblingControl()
            except Exception:
                pass

        walk(self._chat_doc)

        # Cache chat input pixel coords (plain ints — no COM cross-thread issues)
        if self.project_name not in _chat_input_coords:
            for _, ctype, name, ctrl in items:
                if ctype == "EditControl" and name == _CHAT_INPUT_HINT:
                    _chat_input_cache[self.project_name] = ctrl
                    try:
                        r = ctrl.BoundingRectangle
                        if r.width() > 0 and r.height() > 0:
                            _chat_input_coords[self.project_name] = (
                                (r.left + r.right) // 2,
                                (r.top + r.bottom) // 2,
                            )
                    except Exception:
                        pass
                    break

        # ── Permission detection: chat webview first, then VS Code window scan ─
        perm_btn, perm_cmd = None, ""

        # 1. Webview scan — "Yes, allow" button in chat panel
        allow_idx = next(
            (i for i, (_, ct, n, _) in enumerate(items)
             if ct in ("TextControl", "StaticTextControl") and "Allow this" in n),
            -1,
        )
        if allow_idx != -1:
            cmd = ""
            for _, ct2, n2, _ in items[allow_idx + 1: allow_idx + 10]:
                if ct2 == "TextControl" and len(n2) > 2:
                    cmd = n2
                    break
            for _, ctype, name, ctrl in items[allow_idx:allow_idx + 20]:
                if ctype == "ButtonControl" and re.search(r"\byes\b|\ballow\b", name, re.IGNORECASE):
                    perm_btn, perm_cmd = ctrl, cmd
                    break

        # 2. VS Code native Quick Pick scan (no button ctrl — use keyboard to approve)
        if not perm_btn:
            cmd, found = self._scan_window_for_permission()
            if found:
                # Sentinel: perm_btn="keyboard" signals keyboard-based approval
                perm_btn  = "keyboard"
                perm_cmd  = cmd

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

    def arm_from_hook(self, tool: str, cmd: str, loop: asyncio.AbstractEventLoop) -> None:
        """Pre-arm from PreToolUse hook — announces before VS Code shows the dialog."""
        if self._pending:
            return  # already waiting for a response
        self._allow_btn     = "keyboard"
        self._pending       = True
        self._pending_since = time.time()
        self._announced     = f"hook:{cmd}"
        prefix = f"In {self.project_name}: " if self.project_name else ""
        prompt = f"{prefix}Allow command. Say yes or no."
        print(f"\n[Permission/hook] {prefix}{tool}: {cmd}")
        _send_threadsafe({"type": "stop_speech"}, loop)
        asyncio.run_coroutine_threadsafe(_speak_urgent(prompt), loop)

    def handle_response(self, text: str) -> bool:
        if not self._pending or not self._allow_btn:
            return False
        words = set(text.lower().strip().split())
        if words & self.ALLOW_WORDS:
            print(f"[Brain] → Allowing command ({self.project_name or 'session'})")
            if self._allow_btn == "keyboard":
                # Native VS Code Quick Pick: press "1" to select "1 Yes"
                vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
                if vscode.Exists(1):
                    try:
                        vscode.SetFocus()
                    except Exception:
                        pass
                pyautogui.press("1")
            else:
                clicked = False
                try:
                    self._allow_btn.Click()
                    clicked = True
                except Exception:
                    pass
                if not clicked:
                    pyautogui.press("enter")
            self._pending   = False
            self._allow_btn = None
            return True
        if words & self.DENY_WORDS:
            print(f"[Brain] → Cancelling command ({self.project_name or 'session'})")
            vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
            if vscode.Exists(1):
                try:
                    vscode.SetFocus()
                except Exception:
                    pass
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
            print(f"[Brain] → Dismissed prompt ({self.project_name or 'session'})")
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
                print(f"[Brain] → Prompt answered: {text!r}")
            except Exception as e:
                print(f"[Brain] Prompt input error: {e}")
        self._prompt_pending    = False
        self._prompt_input_ctrl = None
        return True

    def start(self, loop: asyncio.AbstractEventLoop):
        def poll():
            comtypes.CoInitializeEx()
            while self._chat_doc is None:
                self._chat_doc = self._find_webview()
                if self._chat_doc is None:
                    time.sleep(2)

            _poll_tick = 0
            while True:
                time.sleep(self.POLL_SECS)
                _poll_tick += 1
                try:
                    btn, cmd, p_ctrl, p_label = self._scan()

                    # Every 5 polls (~1.5s): also scan all Chrome panes for
                    # the VS Code native Quick Pick permission dialog
                    if not btn and _poll_tick % 5 == 0:
                        qp_cmd, qp_found = self._scan_window_for_permission()
                        if qp_found:
                            btn, cmd = "keyboard", qp_cmd

                    if btn:
                        if not self._pending:
                            # Fresh UIA detection — announce
                            self._allow_btn     = btn
                            self._pending       = True
                            self._pending_since = time.time()
                            self._announced     = cmd
                            prefix = f"In {self.project_name}: " if self.project_name else ""
                            prompt = f"{prefix}Allow command. Say yes or no."
                            print(f"\n[Permission] {prefix}Claude wants to run: {cmd}")
                            _send_threadsafe({"type": "stop_speech"}, loop)
                            asyncio.run_coroutine_threadsafe(_speak_urgent(prompt), loop)
                        elif btn != "keyboard" and self._allow_btn == "keyboard":
                            # Hook armed with keyboard fallback — upgrade to real UIA button
                            self._allow_btn = btn
                    elif not btn:
                        self._announced = ""
                        # Keep pending for 20 s after announcement so transient
                        # UIA misses don't clear it before the user responds.
                        if self._pending and time.time() > getattr(self, "_pending_since", 0) + 20:
                            self._pending   = False
                            self._allow_btn = None

                    if p_ctrl and p_label != self._prompt_announced:
                        self._prompt_input_ctrl = p_ctrl
                        self._prompt_pending    = True
                        self._prompt_announced  = p_label
                        prefix = f"In {self.project_name}: " if self.project_name else ""
                        prompt = f"{prefix}{p_label}"
                        print(f"\n[Input Prompt] {prompt}")
                        asyncio.run_coroutine_threadsafe(_speak_urgent(prompt), loop)
                    elif not p_ctrl:
                        self._prompt_announced = ""
                        if self._prompt_pending:
                            self._prompt_pending    = False
                            self._prompt_input_ctrl = None

                except Exception:
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

    def on_session_switch(self, proj: str, loop: asyncio.AbstractEventLoop):
        cw = self._chat_watchers.get(proj)
        if cw:
            n = cw.flush_pending(loop)
            if n:
                print(f"[Brain] Flushed {n} queued response(s) from {proj}")

    def last_response(self, proj: str) -> str:
        cw = self._chat_watchers.get(proj)
        return cw.last_spoken if cw else ""

    def rename_alias(self, old_alias: str, new_alias: str, proj: str) -> None:
        self._aliases.pop(old_alias, None)
        self._aliases[new_alias.lower().strip()] = proj

    def _add_session(self, proj: str, subname: str, loop: asyncio.AbstractEventLoop):
        global _whisper_prompt
        alias = _make_alias(proj)
        self._aliases[alias] = proj
        print(f"[Brain] Session detected: {proj}  (say \"switch to {alias}\")")
        names = " ".join(p for p in self._chat_watchers) + f" {proj}"
        _whisper_prompt = f"Cyrus, switch to {names.strip()}."
        # Push updated prompt to voice
        _send_threadsafe({"type": "whisper_prompt", "text": _whisper_prompt}, loop)

        def is_active():
            with _active_project_lock:
                return _active_project == proj

        cw = ChatWatcher(project_name=proj, target_subname=subname)
        cw.start(loop, is_active_fn=is_active)
        self._chat_watchers[proj] = cw

        pw = PermissionWatcher(project_name=proj, target_subname=subname)
        pw.start(loop)
        self._perm_watchers[proj] = pw

    def start(self, loop: asyncio.AbstractEventLoop):
        def scan():
            while True:
                try:
                    for proj, subname in _vs_code_windows():
                        if proj not in self._chat_watchers:
                            self._add_session(proj, subname, loop)
                except Exception:
                    pass
                time.sleep(5)

        try:
            for proj, subname in _vs_code_windows():
                self._add_session(proj, subname, loop)
        except Exception:
            pass

        if self.multi_session:
            names = " | ".join(f'"{a}"' for a in self._aliases)
            print(f'[Brain] {len(self._chat_watchers)} sessions: {names}')

        threading.Thread(target=scan, daemon=True).start()


# ── Active window tracker ──────────────────────────────────────────────────────

def _start_active_tracker(session_mgr: SessionManager,
                           loop: asyncio.AbstractEventLoop):
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
                    print(f"[Brain] Active project: {proj}")
                    session_mgr.on_session_switch(proj, loop)
        except Exception:
            pass
        time.sleep(0.5)


# ── VS Code submit ─────────────────────────────────────────────────────────────

def _find_chat_input(target_subname: str = "") -> object:
    subname = target_subname or VSCODE_TITLE
    vscode  = auto.WindowControl(searchDepth=1, SubName=subname)
    if not vscode.Exists(2):
        vscode = auto.WindowControl(searchDepth=1, SubName=VSCODE_TITLE)
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
            pass
        try:
            child = ctrl.GetFirstChildControl()
            while child:
                _walk(child, d + 1)
                child = child.GetNextSiblingControl()
        except Exception:
            pass

    _walk(chrome)
    if not found:
        return None
    for _, c in found:
        if (c.Name or "") in (_CHAT_INPUT_HINT, "Message input"):
            return c
    return min(found, key=lambda x: x[0])[1]


def _open_companion_connection(safe: str) -> socket.socket:
    """Open a socket to the Cyrus Companion extension for the given workspace.
    Windows: TCP localhost, port read from %LOCALAPPDATA%\\cyrus\\companion-{safe}.port
    Unix/Mac: AF_UNIX socket at /tmp/cyrus-companion-{safe}.sock
    """
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        port_file = os.path.join(base, 'cyrus', f'companion-{safe}.port')
        port = int(open(port_file).read().strip())
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(('127.0.0.1', port))
        return s
    else:
        import tempfile
        sock_path = os.path.join(tempfile.gettempdir(), f'cyrus-companion-{safe}.sock')
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(sock_path)
        return s


def _submit_via_extension(text: str) -> bool:
    """
    Submit via the Cyrus Companion VS Code extension.
    Windows: TCP localhost + discovery file (no AF_UNIX needed).
    Unix/Mac: AF_UNIX domain socket.
    Returns True on {"ok": true}, False on any failure (falls back to UIA).
    """
    with _active_project_lock:
        proj = _active_project

    safe = re.sub(r'[^\w\-]', '_', proj or "default")[:40]

    try:
        with _open_companion_connection(safe) as s:
            s.sendall((json.dumps({"text": text}) + "\n").encode("utf-8"))
            raw = b""
            while b"\n" not in raw:
                chunk = s.recv(4096)
                if not chunk:
                    break
                raw += chunk
            result = json.loads(raw.decode("utf-8").strip())
            if result.get("ok"):
                return True
            print(f"[Brain] Extension error: {result.get('error')}")
            return False
    except FileNotFoundError:
        # Discovery file or socket not found — extension not running
        return False
    except (ConnectionRefusedError, OSError) as e:
        print(f"[Brain] Companion extension unavailable: {e}")
        return False
    except Exception as e:
        print(f"[Brain] Companion extension error: {e}")
        return False


def _submit_to_vscode_impl(text: str) -> bool:
    """Runs on the dedicated submit thread. Uses pixel coords — no COM cross-thread issues."""
    global _vscode_win_cache

    # ── 0. Try companion extension (no pixel coords, cross-platform) ──────────
    if _submit_via_extension(text):
        return True
    print("[Brain] Companion extension unavailable — falling back to UIA")

    with _active_project_lock:
        proj = _active_project

    # ── 1. Resolve coords BEFORE activating window (activation can disrupt UIA) ─
    # Wait briefly for ChatWatcher to populate coords on startup
    deadline = time.time() + 6.0
    while proj not in _chat_input_coords and time.time() < deadline:
        time.sleep(0.3)
    coords = _chat_input_coords.get(proj)

    # Fallback: active project key may not match cached session — use any available coords
    if not coords and _chat_input_coords:
        fallback_proj, coords = next(iter(_chat_input_coords.items()))
        print(f"[submit] active={proj!r} not in coords cache — using fallback from {fallback_proj!r}")

    if not coords:
        # Last-resort UIA search — no window activation yet
        target_sub = f"{proj} - Visual Studio Code" if proj else VSCODE_TITLE
        ctrl = _find_chat_input(target_sub)
        if ctrl:
            try:
                r = ctrl.BoundingRectangle
                if r.width() > 0:
                    coords = ((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                    _chat_input_coords[proj] = coords
            except Exception:
                pass
        if not coords:
            print("[!] Claude chat input not found.")
            return False

    # ── 2. Find and activate VS Code window ───────────────────────────────────
    win = _vscode_win_cache.get(proj)
    if win is not None:
        try:
            if VSCODE_TITLE not in (win.title or ""):
                raise ValueError("wrong window")
        except Exception:
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
        time.sleep(0.25)
    except Exception:
        pass

    # ── 3. Click chat input by pixel coords ───────────────────────────────────
    pyautogui.click(*coords)
    time.sleep(0.1)

    # ── 4. Paste text and submit ───────────────────────────────────────────────
    saved = ""
    try:
        saved = pyperclip.paste()
    except Exception:
        pass

    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.05)
    pyautogui.press("enter")
    time.sleep(0.05)

    try:
        pyperclip.copy(saved)
    except Exception:
        pass

    return True


def submit_to_vscode(text: str) -> bool:
    """Thread-safe submit — dispatches to dedicated submit thread."""
    result_holder = [False]
    ev = threading.Event()
    _submit_request_queue.put((text, ev, result_holder))
    ev.wait(timeout=10.0)
    return result_holder[0]


def _submit_worker() -> None:
    """Dedicated thread: COM initialized once, handles all VS Code submits."""
    comtypes.CoInitializeEx()
    while True:
        text, ev, result_holder = _submit_request_queue.get()
        try:
            result_holder[0] = _submit_to_vscode_impl(text)
        except Exception as e:
            print(f"[Brain] Submit error: {e}")
            result_holder[0] = False
        ev.set()


# ── Voice reader — process incoming messages from voice service ────────────────

async def voice_reader(reader: asyncio.StreamReader,
                        session_mgr: SessionManager,
                        loop: asyncio.AbstractEventLoop) -> None:
    global _conversation_active, _tts_active_remote

    while True:
        try:
            line = await reader.readline()
            if not line:
                break
            msg   = json.loads(line.decode().strip())
            mtype = msg.get("type", "")

            if mtype == "tts_start":
                _tts_active_remote = True

            elif mtype == "tts_end":
                _tts_active_remote = False

            elif mtype == "utterance":
                text       = msg.get("text", "").strip()
                during_tts = msg.get("during_tts", False)
                if not text:
                    continue
                await _utterance_queue.put((text, during_tts))

        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"[Brain] Voice reader error: {e}")
            break


# ── Utterance routing loop ─────────────────────────────────────────────────────

async def routing_loop(session_mgr: SessionManager,
                        loop: asyncio.AbstractEventLoop) -> None:
    global _conversation_active, _active_project

    while True:
        text, during_tts = await _utterance_queue.get()

        # Echo guard: only wake-word interrupts get through during TTS
        if during_tts or _tts_active_remote:
            fw       = text.lower().strip().split()
            has_wake = any(w.rstrip(",.!?") in WAKE_WORDS for w in fw)
            if not has_wake:
                continue
            # Interrupt TTS and proceed
            await _send({"type": "stop_speech"})
            await asyncio.sleep(0.15)

        # Permission dialog — binary response, bypass routing
        handled = False
        for pw in session_mgr.perm_watchers:
            if pw.is_pending:
                if pw.handle_response(text):
                    handled = True
                    break
        if handled:
            continue

        # Input prompt — strip wake word if present
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

        # Wake word check
        words = text.lower().strip().split()
        first = words[0].rstrip(",.!?") if words else ""

        if _conversation_active:
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
                print("(wake word — listening for command...)", end=" ", flush=True)
                await _send({"type": "listen_chime"})
                try:
                    follow_text, _ = await asyncio.wait_for(
                        _utterance_queue.get(), timeout=6.0
                    )
                    fw = follow_text.lower().strip().split()
                    if fw and fw[0].rstrip(",.!?") in WAKE_WORDS:
                        parts      = follow_text.split(None, 1)
                        follow_text = parts[1].lstrip(", ").strip() if len(parts) > 1 else ""
                    text = follow_text
                    if not text:
                        print("(no command heard)")
                        continue
                    print(f"'{text}'")
                except asyncio.TimeoutError:
                    print("(no command heard)")
                    continue

        # ── Route ─────────────────────────────────────────────────────────────
        decision = _fast_command(text)

        if decision is None:
            with _active_project_lock:
                proj = _active_project
            if _is_answer_request(text):
                resp = session_mgr.last_response(proj) or "I don't have a recent response to share."
                resp_words = resp.split()
                if len(resp_words) > 30:
                    resp = " ".join(resp_words[:30]) + ". See the chat for more."
                decision = {"action": "answer", "spoken": resp, "message": "", "command": {}}
            else:
                decision = {"action": "forward", "message": text, "spoken": "", "command": {}}

        action = decision.get("action", "forward")

        if action == "answer":
            spoken = decision.get("spoken", "")
            if spoken:
                print(f"\n[Brain answers] {spoken[:80]}{'...' if len(spoken) > 80 else ''}")
                await _speak_queue.put(("", spoken))
            _conversation_active = False

        elif action == "command":
            ctype = decision.get("command", {}).get("type", "")
            spoken = decision.get("spoken", "")
            print(f"\n[Brain command] {ctype}")
            _execute_cyrus_command(ctype, decision.get("command", {}),
                                   spoken, session_mgr, loop)
            _conversation_active = spoken.rstrip().endswith("?")

        else:  # "forward"
            raw_msg = _strip_fillers(decision.get("message") or text)
            message = raw_msg + VOICE_HINT
            with _active_project_lock:
                proj = _active_project
            print(f"\nYou [{proj or 'VS Code'}]: {message}")
            try:
                submitted = await asyncio.wait_for(
                    loop.run_in_executor(None, submit_to_vscode, message),
                    timeout=12.0,
                )
            except asyncio.TimeoutError:
                print("→ Submit timed out.\n")
                submitted = False
            if not submitted:
                print("→ Could not find VS Code window.\n")
            else:
                await _send({"type": "chime"})
            _conversation_active = False


# ── Hook handler ──────────────────────────────────────────────────────────────

def _resolve_project_from_cwd(cwd: str, session_mgr: "SessionManager") -> str:
    """Match the trailing folder of cwd against known project names."""
    if not cwd:
        with _active_project_lock:
            return _active_project
    folder = os.path.basename(cwd.rstrip("/\\")).lower()
    for proj in session_mgr._chat_watchers:
        if folder in proj.lower() or proj.lower() in folder:
            return proj
    with _active_project_lock:
        return _active_project


async def handle_hook_connection(reader: asyncio.StreamReader,
                                  writer: asyncio.StreamWriter,
                                  session_mgr: "SessionManager") -> None:
    """
    Accepts a single connection from cyrus_hook.py, reads one JSON message,
    and dispatches on event type: stop / pre_tool / post_tool / notification.
    """
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=3.0)
        if not raw:
            return
        msg   = json.loads(raw.decode().strip())
        event = msg.get("event", "stop")
        cwd   = msg.get("cwd", "")
        proj  = _resolve_project_from_cwd(cwd, session_mgr)
        loop  = asyncio.get_event_loop()

        if event == "stop":
            text = (msg.get("text") or "").strip()
            if not text:
                return
            spoken = clean_for_speech(text)
            cw = session_mgr._chat_watchers.get(proj)
            if cw:
                cw._response_history.append(spoken)
                cw._hook_spoken_until = time.time() + 30.0
            preview = spoken[:80] + ("..." if len(spoken) > 80 else "")
            print(f"\nCyrus [{proj or 'Claude'}] (hook): {preview}")
            await _speak_queue.put((proj, spoken))

        elif event == "pre_tool":
            tool = msg.get("tool", "")
            cmd  = msg.get("command", "")
            print(f"[pre_tool] Received: tool={tool}, proj={proj!r}, cmd={cmd[:60]}")
            pw   = (session_mgr._perm_watchers.get(proj) or
                    next(iter(session_mgr._perm_watchers.values()), None))
            if pw:
                pw.arm_from_hook(tool, cmd, loop)
            else:
                print(f"[pre_tool] No PermissionWatcher found for proj={proj!r}, "
                      f"known={list(session_mgr._perm_watchers.keys())}")

        elif event == "post_tool":
            tool   = msg.get("tool", "")
            prefix = f"In {proj}: " if proj else ""
            if tool == "Bash":
                exit_code = msg.get("exit_code", 0)
                if exit_code != 0:
                    spoken = f"{prefix}Command failed with exit code {exit_code}."
                    print(f"\n[PostTool] {spoken}")
                    await _speak_urgent(spoken)
            elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                file_path = msg.get("file_path", "")
                basename  = os.path.basename(file_path) if file_path else "a file"
                verb      = "wrote" if tool == "Write" else "edited"
                spoken    = f"{prefix}Claude {verb} {basename}."
                print(f"\n[PostTool] {spoken}")
                await _speak_queue.put(("", spoken))

        elif event == "notification":
            message = (msg.get("message") or "").strip()
            if message:
                prefix = f"In {proj}: " if proj else ""
                spoken = f"{prefix}{message}"
                print(f"\n[Notification] {spoken}")
                await _speak_urgent(spoken)

    except asyncio.TimeoutError:
        pass
    except Exception as e:
        print(f"[Brain] Hook handler error: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ── TCP server ─────────────────────────────────────────────────────────────────

async def handle_voice_connection(reader: asyncio.StreamReader,
                                   writer: asyncio.StreamWriter,
                                   session_mgr: SessionManager,
                                   loop: asyncio.AbstractEventLoop) -> None:
    global _voice_writer
    addr = writer.get_extra_info("peername")
    print(f"[Brain] Voice service connected from {addr}")
    _voice_writer = writer

    # Announce sessions to voice so it can prime Whisper prompt
    if _whisper_prompt:
        await _send({"type": "whisper_prompt", "text": _whisper_prompt})

    # Startup greeting
    windows = _vs_code_windows()
    if not windows:
        greeting = "Cyrus is online. No VS Code sessions detected."
    elif len(windows) == 1:
        greeting = f"Cyrus is online. Session: {_make_alias(windows[0][0])}."
    else:
        names    = ", ".join(_make_alias(p) for p, _ in windows)
        greeting = f"Cyrus is online. {len(windows)} sessions: {names}."

    await _send({"type": "speak", "text": greeting, "project": ""})
    await _send({"type": "listen_chime"})
    print("[Brain] Listening for wake word...")

    try:
        await voice_reader(reader, session_mgr, loop)
    finally:
        _voice_writer = None
        print(f"[Brain] Voice service disconnected.")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    global _speak_queue, _utterance_queue, _active_project

    parser = argparse.ArgumentParser(description="Cyrus Brain — logic/watcher service")
    parser.add_argument("--host", default=BRAIN_HOST, help="Listen host")
    parser.add_argument("--port", type=int, default=BRAIN_PORT, help="Listen port")
    args = parser.parse_args()

    _speak_queue     = asyncio.Queue()
    _utterance_queue = asyncio.Queue()
    loop             = asyncio.get_event_loop()

    # Session manager starts immediately — scans VS Code windows
    session_mgr = SessionManager()
    session_mgr.start(loop)

    # Set initial active project
    first = _vs_code_windows()
    if first:
        with _active_project_lock:
            _active_project = first[0][0]

    # Window focus tracker
    threading.Thread(
        target=_start_active_tracker,
        args=(session_mgr, loop),
        daemon=True,
    ).start()

    # Dedicated VS Code submit thread — COM initialized once, stable apartment
    threading.Thread(target=_submit_worker, daemon=True).start()

    # Speak worker — forwards queued speak requests to voice
    asyncio.create_task(_speak_worker())

    # Routing loop — processes utterances
    asyncio.create_task(routing_loop(session_mgr, loop))

    # Voice TCP server (port 8766)
    voice_server = await asyncio.start_server(
        lambda r, w: handle_voice_connection(r, w, session_mgr, loop),
        args.host, args.port,
    )
    addr = voice_server.sockets[0].getsockname()
    print(f"[Brain] Listening for voice service on {addr[0]}:{addr[1]}")

    # Hook TCP server (port 8767) — Claude Code Stop hook connects here
    hook_server = await asyncio.start_server(
        lambda r, w: handle_hook_connection(r, w, session_mgr),
        args.host, HOOK_PORT,
    )
    hook_addr = hook_server.sockets[0].getsockname()
    print(f"[Brain] Listening for Claude hooks on {hook_addr[0]}:{hook_addr[1]}")
    print("[Brain] Waiting for voice to connect...")

    async with voice_server, hook_server:
        await asyncio.gather(
            voice_server.serve_forever(),
            hook_server.serve_forever(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        print("\nCyrus Brain signing off.")
