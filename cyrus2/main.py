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

import argparse
import asyncio
import json
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import keyboard
import numpy as np
import pyautogui
import pygame
import pygetwindow as gw
import pyperclip
import sounddevice as sd
import torch
import uiautomation as auto
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from silero_vad import load_silero_vad

from cyrus_common import (
    _CHAT_INPUT_HINT,
    _HALLUCINATIONS,
    VOICE_HINT,
    VSCODE_TITLE,
    WAKE_WORDS,
    ChatWatcher,
    PermissionWatcher,
    SessionManager,
    _chat_input_cache,
    _extract_project,
    _fast_command,
    _is_answer_request,
    _make_alias,
    _resolve_project,
    _strip_fillers,
    _vs_code_windows,
    play_chime,
    play_listen_chime,
    register_chime_handlers,
)

load_dotenv()

# ── GPU detection (runs at import time) ───────────────────────────────────────

_CUDA = torch.cuda.is_available()
_GPU_NAME = torch.cuda.get_device_name(0) if _CUDA else "none"

# ── Configuration ─────────────────────────────────────────────────────────────

WHISPER_MODEL = "medium.en"
WHISPER_DEVICE = "cuda" if _CUDA else "cpu"
WHISPER_COMPUTE_TYPE = "float16" if _CUDA else "int8"
SAMPLE_RATE = 16000
CHANNELS = 1

# Kokoro TTS — model files must be in the same directory as main.py
KOKORO_MODEL = os.path.join(os.path.dirname(__file__), "kokoro-v1.0.onnx")
KOKORO_VOICES = os.path.join(os.path.dirname(__file__), "voices-v1.0.bin")
TTS_VOICE = "af_heart"  # see voices-v1.0.bin for full list
TTS_SPEED = 1.0  # 0.5 – 2.0

# main.py speaks at most 30 words — shorter than brain's 50-word default
MAX_SPEECH_WORDS = 30  # hard cap on spoken words (~12 s at 150 wpm)

KEY_PAUSE = "f9"
KEY_STOP = "f7"
KEY_READ_CLIP = "f8"

SPEECH_THRESHOLD = 0.5  # Silero probability threshold (0-1)
FRAME_MS = 32  # Silero requires 512 samples @ 16 kHz (32 ms)
FRAME_SIZE = 512  # must match exactly
SPEECH_WINDOW_MS = 300
SILENCE_WINDOW_MS = (
    1000  # ms of silence to end utterance (Silero handles noise, so 1 s is safe)
)
MAX_RECORD_MS = 12000  # hard cap — end recording after 12 s regardless

SPEECH_RING = SPEECH_WINDOW_MS // FRAME_MS
SILENCE_RING = SILENCE_WINDOW_MS // FRAME_MS
MAX_RECORD_FRAMES = MAX_RECORD_MS // FRAME_MS
SPEECH_RATIO = 0.80  # fraction of ring that must be speech to start (was 0.75)

# ── Shared state ──────────────────────────────────────────────────────────────

_mic_muted = threading.Event()
_user_paused = threading.Event()
_stop_speech = threading.Event()
_tts_active = threading.Event()  # set while Cyrus is playing speech
_tts_pending = threading.Event()  # set when TTS is queued but not yet started
_shutdown = threading.Event()  # set on Ctrl+C to stop all loops cleanly

pyautogui.FAILSAFE = False
auto.uiautomation.SetGlobalSearchTimeout(2)

# ── Session tracking ──────────────────────────────────────────────────────────

_active_project: str = ""
_active_project_lock: threading.Lock = threading.Lock()
_vscode_win_cache: dict = {}  # project_name → pygetwindow handle

_project_locked: bool = False
_project_locked_lock: threading.Lock = threading.Lock()

_conversation_active: bool = False  # True = no wake word needed for next reply

# Whisper initial_prompt — updated as sessions are discovered so project names
# are recognised correctly (e.g. "dev", "web app").  Thread-safe: only written
# from the session-scan thread before transcription starts in earnest.
_whisper_prompt: str = "Cyrus,"

# Global TTS queue — initialized in main()
_tts_queue: asyncio.Queue = None  # asyncio.Queue[tuple[str, str]]

# Dedicated executor — initialized in main()
_whisper_executor: ThreadPoolExecutor = None  # max_workers=1, CPU-bound

# Remote brain connection — set when --remote URL is passed
_remote_url: str = ""  # e.g. "ws://192.168.1.10:8765"
_remote_ws = None  # websockets.ClientConnection, or None

# Kokoro TTS engine — initialized in main()
_kokoro = None


# ── Local chime implementations (numpy/pygame audio) ──────────────────────────


def _local_play_chime() -> None:
    """Play a brief 880 Hz notification tone (non-blocking, low volume)."""
    try:
        sample_rate = 44100
        duration = 0.18
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        wave = (np.sin(2 * np.pi * 880 * t) * 32767 * 0.25).astype(np.int16)
        stereo = np.column_stack([wave, wave])
        sound = pygame.sndarray.make_sound(stereo)
        sound.play()
    except Exception:
        pass


def _local_play_listen_chime() -> None:
    """Two-tone ascending beep (500 Hz → 800 Hz) — signals Cyrus is listening."""
    try:
        sr = 44100
        gap = np.zeros(int(sr * 0.04), dtype=np.int16)

        def tone(freq, dur, vol=0.22):
            t = np.linspace(0, dur, int(sr * dur), False)
            return (np.sin(2 * np.pi * freq * t) * 32767 * vol).astype(np.int16)

        wave = np.concatenate([tone(500, 0.09), gap, tone(800, 0.09)])
        stereo = np.column_stack([wave, wave])
        pygame.sndarray.make_sound(stereo).play()
    except Exception:
        pass


# ── Active window tracker ──────────────────────────────────────────────────────


def _start_active_tracker(session_mgr, loop):
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
                    session_mgr.on_session_switch(proj)
        except Exception:
            pass
        time.sleep(0.5)


# ── TTS queue helpers ─────────────────────────────────────────────────────────


async def drain_tts_queue() -> None:
    """Drain all pending items from the global TTS queue."""
    if _tts_queue is None:
        return
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except Exception:
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
        except Exception as e:
            print(f"[TTS worker error] {e}")


async def _speak_urgent(text: str) -> None:
    """Drain queue then speak immediately — for permission dialogs."""
    await drain_tts_queue()
    await speak(text)


# ── Factory functions — wire main.py-specific callbacks into common classes ────


def _make_enqueue_speech_fn(tts_queue, loop):
    """Create a speech-enqueue callable for ChatWatcher (main.py local TTS)."""

    def enqueue_speech(
        project_name: str, text: str, full_text: str | None = None
    ) -> None:
        # main.py uses 2-tuple TTS queue (no full_text for IPC)
        _tts_pending.set()
        asyncio.run_coroutine_threadsafe(tts_queue.put((project_name, text)), loop)

    return enqueue_speech


def _make_speak_urgent_fn(loop):
    """Create a speak-urgent callable for PermissionWatcher (main.py backend)."""

    def speak_urgent(prompt: str) -> None:
        asyncio.run_coroutine_threadsafe(_speak_urgent(prompt), loop)

    return speak_urgent


def _make_stop_speech_fn():
    """Create a stop-speech callable for PermissionWatcher (main.py backend)."""

    def stop_speech() -> None:
        _stop_speech.set()

    return stop_speech


def _make_session_manager(tts_queue, loop) -> SessionManager:
    """Create a SessionManager wired to the main.py local TTS backend."""

    def make_chat_watcher(project_name: str, subname: str) -> ChatWatcher:
        return ChatWatcher(
            project_name=project_name,
            target_subname=subname,
            enqueue_speech_fn=_make_enqueue_speech_fn(tts_queue, loop),
            chime_fn=_local_play_chime,
            max_speech_words=MAX_SPEECH_WORDS,
        )

    def make_perm_watcher(project_name: str, subname: str) -> PermissionWatcher:
        return PermissionWatcher(
            project_name=project_name,
            target_subname=subname,
            speak_urgent_fn=_make_speak_urgent_fn(loop),
            stop_speech_fn=_make_stop_speech_fn(),
        )

    def on_whisper_prompt(prompt: str) -> None:
        global _whisper_prompt
        _whisper_prompt = prompt

    def get_active_project() -> str:
        with _active_project_lock:
            return _active_project

    return SessionManager(
        make_chat_watcher_fn=make_chat_watcher,
        make_perm_watcher_fn=make_perm_watcher,
        on_whisper_prompt_fn=on_whisper_prompt,
        is_active_project_fn=get_active_project,
    )


# ── Command execution ──────────────────────────────────────────────────────────


def _execute_cyrus_command(
    ctype: str, cmd: dict, spoken: str, session_mgr, loop
) -> None:
    """Execute a Cyrus meta-command returned by the LLM."""
    global _active_project, _project_locked

    if ctype == "switch_project":
        target = _resolve_project(cmd.get("project", ""), session_mgr.aliases)
        if target:
            with _active_project_lock:
                _active_project = target
            with _project_locked_lock:
                _project_locked = True
            session_mgr.on_session_switch(target)
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
            asyncio.run_coroutine_threadsafe(_tts_queue.put((proj_name, resp)), loop)
            return  # spoken already queued above
        else:
            spoken = (
                spoken or f"No recorded response for {proj_name or 'this session'}."
            )
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
            old_alias = next(
                (a for a, p in session_mgr.aliases.items() if p == proj), proj
            )
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


# ── VAD loop ──────────────────────────────────────────────────────────────────


def vad_loop(on_utterance, loop: asyncio.AbstractEventLoop):
    """Voice activity detection loop — captures audio chunks and calls on_utterance."""
    model = load_silero_vad()
    ring: deque[tuple[bytes, bool]] = deque(maxlen=SPEECH_RING)
    recording = False
    frames: list[bytes] = []
    silence_count = 0
    speech_frames = 0  # frames where speech was detected — drives adaptive silence

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=FRAME_SIZE
    ) as stream:
        while not _shutdown.is_set():
            if _mic_muted.is_set() or _user_paused.is_set():
                stream.read(FRAME_SIZE)
                ring.clear()
                if recording:
                    frames.clear()
                    recording = False
                    silence_count = 0
                time.sleep(0.01)
                continue

            raw, _ = stream.read(FRAME_SIZE)
            frame_bytes = bytes(raw)

            try:
                chunk = (
                    np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32)
                    / 32768.0
                )
                with torch.no_grad():
                    prob = model(torch.from_numpy(chunk), SAMPLE_RATE).item()
                is_speech = prob > SPEECH_THRESHOLD
            except Exception:
                continue

            if not recording:
                ring.append((frame_bytes, is_speech))
                num_voiced = sum(1 for _, s in ring if s)
                if (
                    len(ring) == ring.maxlen
                    and num_voiced / ring.maxlen >= SPEECH_RATIO
                ):
                    recording = True
                    frames = [fb for fb, _ in ring]
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
                adaptive_ring = (
                    SILENCE_RING * 2
                    if speech_frames * FRAME_MS > 1500
                    else SILENCE_RING
                )

                timed_out = len(frames) >= MAX_RECORD_FRAMES
                if silence_count >= adaptive_ring or timed_out:
                    if timed_out:
                        print(" [max duration]", flush=True)
                    raw_audio = b"".join(frames)
                    audio = (
                        np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
                        / 32768.0
                    )
                    recording = False
                    frames = []
                    silence_count = 0
                    speech_frames = 0
                    ring.clear()
                    model.reset_states()  # clear GRU state between utterances
                    loop.call_soon_threadsafe(on_utterance, audio)


# ── Speech-to-text ────────────────────────────────────────────────────────────

# RMS energy floor — skip transcription if audio is essentially silence
_MIN_RMS = 0.004  # ~-48 dBFS; tune up if hallucinations persist


def transcribe(whisper_model: WhisperModel, audio: np.ndarray) -> str:
    """Transcribe audio using Whisper; filter hallucinations and silence."""
    rms = float(np.sqrt(np.mean(audio**2)))
    if rms < _MIN_RMS:
        return ""  # too quiet — don't feed silence to Whisper

    segments, _ = whisper_model.transcribe(
        audio, language="en", beam_size=1, best_of=1, initial_prompt=_whisper_prompt
    )
    text = " ".join(s.text for s in segments if s.no_speech_prob < 0.6).strip()

    if _HALLUCINATIONS.search(text):
        print(f"(hallucination filtered: '{text[:60]}')")
        return ""

    return text


# ── Submit to VS Code ─────────────────────────────────────────────────────────


def _find_chat_input(target_subname: str = "") -> object:
    """Find the Claude Code chat input EditControl via UIA."""
    subname = target_subname or VSCODE_TITLE
    vscode = auto.WindowControl(searchDepth=1, SubName=subname)
    if not vscode.Exists(2):
        return None

    ctrl = vscode.EditControl(searchDepth=12, Name=_CHAT_INPUT_HINT)
    if ctrl.Exists(2):
        return ctrl

    chrome = vscode.PaneControl(searchDepth=12, ClassName="Chrome_RenderWidgetHostHWND")
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


def submit_to_vscode(text: str) -> bool:
    """Submit text to the Claude Code chat input via UIA or cached control."""
    global _vscode_win_cache

    with _active_project_lock:
        proj = _active_project

    target_sub = f"{proj} - Visual Studio Code" if proj else VSCODE_TITLE

    # ── Activate VS Code window (cached) ──────────────────────────────────────
    win = _vscode_win_cache.get(proj)
    if win is not None:
        try:
            if VSCODE_TITLE not in (win.title or ""):
                raise ValueError("wrong window")
        except Exception:
            win = None
            _vscode_win_cache.pop(proj, None)

    if win is None:
        matches = [
            w
            for w in gw.getAllWindows()
            if VSCODE_TITLE in (w.title or "") and (not proj or proj in w.title)
        ]
        if not matches:
            matches = [w for w in gw.getAllWindows() if VSCODE_TITLE in (w.title or "")]
        if not matches:
            print("[!] VS Code window not found.")
            return False
        win = matches[0]
        _vscode_win_cache[proj] = win

    try:
        win.activate()
        time.sleep(0.15)  # give VS Code time to foreground and update UIA tree
    except Exception:
        pass

    # ── Use cached chat input — no Exists() check, just try it ────────────────
    cached = _chat_input_cache.get(proj)
    if cached is not None:
        try:
            cached.SetFocus()
            time.sleep(0.03)
            cached.Click()
            time.sleep(0.03)
        except Exception:
            # Stale handle — fall through to fresh search
            cached = None
            _chat_input_cache.pop(proj, None)

    if cached is None:
        cached = _find_chat_input(target_sub)
        if not cached:
            print(
                "[!] Claude chat input not found"
                " — skipping to avoid typing in wrong window."
            )
            return False
        _chat_input_cache[proj] = cached
        try:
            cached.SetFocus()
            time.sleep(0.03)
            cached.Click()
            time.sleep(0.03)
        except Exception:
            _chat_input_cache.pop(proj, None)
            print("[!] Could not click Claude chat input — skipping.")
            return False

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


# ── Text-to-speech ────────────────────────────────────────────────────────────


async def speak(text: str) -> None:
    """Speak text via Kokoro (local) or Edge TTS (fallback).

    Mic muted during playback.
    """
    _stop_speech.clear()
    _tts_active.set()
    _mic_muted.set()
    try:
        await asyncio.wait_for(_speak_save(text), timeout=25.0)
    except asyncio.TimeoutError:
        print("[Cyrus] TTS timed out — aborting playback")
        _stop_speech.set()  # signal _speak_kokoro's _play() loop to exit
    finally:
        _tts_active.clear()
        await asyncio.sleep(
            0.25
        )  # brief echo-decay guard; VAD + RMS gate cover the rest
        _mic_muted.clear()


async def _speak_save(text: str) -> None:
    """Synthesise and play text.

    Uses Kokoro if loaded, otherwise falls back to Edge TTS.
    """
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
                stream.write(samples[i : i + chunk].reshape(-1, 1))

    await asyncio.get_event_loop().run_in_executor(None, _play)


async def _speak_edge(text: str) -> None:
    """Edge TTS fallback — requires network + ffmpeg. Used when Kokoro is not loaded."""
    import subprocess
    import tempfile

    import edge_tts

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name
    try:
        await edge_tts.Communicate(
            text, "en-US-BrianNeural", rate="-5%", pitch="-5Hz"
        ).save(tmp_path)
        if not os.path.getsize(tmp_path):
            return

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "quiet",
                    "-i",
                    tmp_path,
                    "-f",
                    "s16le",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-",
                ],
                capture_output=True,
            ),
        )
        pcm = result.stdout
        if not pcm:
            return

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        def _play():
            chunk = 1024
            with sd.OutputStream(
                samplerate=24000, channels=1, dtype="float32"
            ) as stream:
                for i in range(0, len(audio), chunk):
                    if _stop_speech.is_set():
                        break
                    stream.write(audio[i : i + chunk])

        await asyncio.get_event_loop().run_in_executor(None, _play)
    finally:
        try:
            os.unlink(tmp_path)
        except (PermissionError, FileNotFoundError):
            pass


# ── Remote brain routing ───────────────────────────────────────────────────────


async def _remote_route(text: str, project: str, last_response: str) -> dict:
    """Send a transcribed utterance to the remote brain and return its routing decision.

    Falls back to local routing if the connection is unavailable.
    """
    global _remote_ws
    if _remote_ws is None:
        return None  # caller handles fallback

    try:
        msg = json.dumps(
            {
                "type": "utterance",
                "text": text,
                "project": project,
                "last_response": last_response,
            }
        )
        await _remote_ws.send(msg)
        raw = await asyncio.wait_for(_remote_ws.recv(), timeout=5.0)
        data = json.loads(raw)
        # Strip the envelope "type" key before returning as a decision dict
        data.pop("type", None)
        return data
    except Exception as e:
        print(f"[Cyrus] Remote brain unreachable ({e}) — routing locally.")
        _remote_ws = None
        return None


# ── Startup sequence ─────────────────────────────────────────────────────────


async def startup_sequence(session_mgr) -> None:
    """Play greeting and listen chime on startup."""
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
        "--remote",
        metavar="URL",
        help="WebSocket URL of a remote Cyrus brain, e.g. ws://192.168.1.10:8765",
    )
    args = parser.parse_args()

    if args.remote:
        _remote_url = args.remote
        try:
            import websockets as _ws_lib

            _remote_ws = await _ws_lib.connect(_remote_url)
            print(f"[Cyrus] Connected to remote brain at {_remote_url}")
        except Exception as e:
            print(
                f"[Cyrus] Could not connect to remote brain ({e})"
                " — using local routing."
            )
            _remote_url = ""

    if _CUDA:
        print(f"[Cyrus] GPU: {_GPU_NAME}")
    else:
        print("[Cyrus] No CUDA/ROCm GPU detected — Whisper on CPU")
    print(f"Loading Whisper {WHISPER_MODEL} on {WHISPER_DEVICE}...")
    whisper_model = WhisperModel(
        WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE
    )

    # ── Kokoro TTS ──────────────────────────────────────────────────────────────
    if os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_VOICES):
        try:
            import onnxruntime as _ort
            from kokoro_onnx import Kokoro as _KokoroClass

            _ort.set_default_logger_severity(
                3
            )  # suppress WARNING-level Conv fallback noise
            _providers = []
            if _CUDA:
                _providers.append(
                    ("CUDAExecutionProvider", {"cudnn_conv_algo_search": "DEFAULT"})
                )
            _providers.append("CPUExecutionProvider")
            _session = _ort.InferenceSession(KOKORO_MODEL, providers=_providers)
            _kokoro = _KokoroClass.from_session(_session, KOKORO_VOICES)
            _active_providers = _session.get_providers()
            _tts_device = (
                "GPU" if "CUDAExecutionProvider" in _active_providers else "CPU"
            )
            print(f"[Cyrus] Kokoro TTS loaded ({_tts_device}) — voice: {TTS_VOICE}")
        except Exception as e:
            print(f"[Cyrus] Kokoro load failed ({e}) — using Edge TTS fallback")
    else:
        print("[Cyrus] Kokoro model files not found — using Edge TTS fallback")
        print(f"         Expected: {KOKORO_MODEL}")

    pygame.mixer.init()

    loop = asyncio.get_event_loop()

    # Register local audio chime handlers
    register_chime_handlers(
        chime_fn=_local_play_chime,
        listen_chime_fn=_local_play_listen_chime,
    )

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
    session_mgr = _make_session_manager(_tts_queue, loop)
    session_mgr.start()

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
        args=(session_mgr, loop),
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
            text = ""
        if text:
            asyncio.run_coroutine_threadsafe(_tts_queue.put(("", text)), loop)
        else:
            print("[Clipboard empty]")

    keyboard.add_hotkey(KEY_PAUSE, toggle_pause)
    keyboard.add_hotkey(KEY_STOP, stop_speech)
    keyboard.add_hotkey(KEY_READ_CLIP, read_clipboard)

    print("[Cyrus] F9 pause  |  F7 stop+clear  |  F8 clipboard  |  Ctrl+C exit")

    # Interactive startup — verify, greet, detect sessions, assign names
    await startup_sequence(session_mgr)

    # Discard any audio captured during startup TTS
    # (Whisper hallucinates on speaker echo)
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
        text = await loop.run_in_executor(
            _whisper_executor, transcribe, whisper_model, audio
        )

        if not text:
            print("(nothing heard)")
            continue

        # While TTS is playing: only a wake word can interrupt.
        # Any other audio is assumed to be speaker echo — discard it.
        if _tts_active.is_set() or _tts_pending.is_set():
            fw = text.lower().strip().split()
            has_wake = any(w.rstrip(",.!?") in WAKE_WORDS for w in fw)
            if not has_wake:
                continue  # echo or background noise
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
                    text = parts[1].lstrip(", ").strip() if len(parts) > 1 else text
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
                    follow_audio = await asyncio.wait_for(
                        utterance_queue.get(), timeout=6.0
                    )
                    text = await loop.run_in_executor(
                        _whisper_executor, transcribe, whisper_model, follow_audio
                    )
                    # Strip a repeated wake word if the user said it again
                    fw = text.lower().strip().split()
                    if fw and fw[0].rstrip(",.!?") in WAKE_WORDS:
                        parts = text.split(None, 1)
                        text = parts[1].lstrip(", ").strip() if len(parts) > 1 else ""
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
                decision = await _remote_route(text, proj, last_resp)

            if decision is None:
                # Local routing (default, or remote fallback)
                if _is_answer_request(text):
                    resp = (
                        session_mgr.last_response(proj)
                        or "I don't have a recent response to share."
                    )
                    words = resp.split()
                    if len(words) > 30:
                        resp = " ".join(words[:30]) + ". See the chat for more."
                    decision = {
                        "action": "answer",
                        "spoken": resp,
                        "message": "",
                        "command": {},
                    }
                else:
                    decision = {
                        "action": "forward",
                        "message": text,
                        "spoken": "",
                        "command": {},
                    }

        action = decision.get("action", "forward")

        if action == "answer":
            spoken = decision.get("spoken", "")
            if spoken:
                print(
                    "\n[Cyrus answers] "
                    f"{spoken[:80]}{'...' if len(spoken) > 80 else ''}"
                )
                asyncio.run_coroutine_threadsafe(_tts_queue.put(("", spoken)), loop)
                _conversation_active = (
                    False  # require wake word again to prevent TTS echo loop
                )
            else:
                _conversation_active = False

        elif action == "command":
            ctype = decision.get("command", {}).get("type", "")
            spoken = decision.get("spoken", "")
            print(f"\n[Cyrus command] {ctype}")
            _execute_cyrus_command(
                ctype, decision.get("command", {}), spoken, session_mgr, loop
            )
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
                play_chime()  # instant "I got it" signal while Claude processes
            # Sent to Claude Code — conversation with Cyrus ends
            _conversation_active = False


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        print("\nCyrus signing off.")
        _shutdown.set()  # tells vad_loop to exit its while-loop cleanly
        _stop_speech.set()  # aborts any in-progress TTS playback
        _mic_muted.set()  # stops VAD from processing new frames
        try:
            pygame.mixer.stop()  # stop all playing sounds before tearing down SDL
            pygame.mixer.quit()
        except Exception:
            pass
        try:
            sd.stop()  # abort all PortAudio streams
        except Exception:
            pass
        if _whisper_executor is not None:
            _whisper_executor.shutdown(wait=False, cancel_futures=True)
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        # Force-exit: bypasses Python's C-extension destructor sequence which
        # crashes on Windows when audio threads (PortAudio/SDL) are still live.
        os._exit(0)
