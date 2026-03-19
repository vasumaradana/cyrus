"""
cyrus_brain.py — Service 2: Logic / VS Code Watcher (PRIMARY ENTRY POINT)

This is the recommended entry point for Cyrus. main.py is deprecated; use this
directly. Pair with cyrus_voice.py for the full split-mode experience.

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

import argparse
import asyncio
import atexit
import contextlib
import json
import logging
import os
import queue as _stdlib_queue
import re
import signal
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path

# Import cyrus_config first so HEADLESS is available before Windows-specific
# imports are conditionally loaded.  Importing this module has no side effects
# (no hardware or GUI access) so it is always safe to import unconditionally.
from aiohttp import web as _aiohttp_web

from cyrus_config import (
    AUTH_TOKEN,
    BRAIN_PORT,
    COMPANION_PORT,
    HEADLESS,
    HEALTH_PORT,
    HOOK_PORT,
    MOBILE_PORT,
    validate_auth_token,
)

# Guard Windows-only GUI libraries behind the HEADLESS flag.
# In HEADLESS mode (CYRUS_HEADLESS=1) these packages are never imported, which
# allows the brain to start on Linux / Docker where they are not installed.
# The companion extension (port 8770) replaces all UIA-based functionality.
if not HEADLESS:
    import comtypes
    import pyautogui
    import pygetwindow as gw
    import pyperclip

import websockets

if not HEADLESS:
    try:
        import uiautomation as auto
    except Exception:
        # comtypes cache is likely corrupted — clear it and retry
        try:
            import importlib
            import os as _os
            import shutil

            import comtypes.gen

            _gen_dir = _os.path.dirname(comtypes.gen.__file__)
            shutil.rmtree(_gen_dir, ignore_errors=True)
            _os.makedirs(_gen_dir, exist_ok=True)
            # Re-create __init__.py so comtypes.gen is still a package
            with open(_os.path.join(_gen_dir, "__init__.py"), "w") as _f:
                _f.write("# auto-generated\n")
            logging.getLogger("cyrus.brain").warning(
                "Cleared corrupted comtypes cache, retrying..."
            )
            importlib.invalidate_caches()
            import uiautomation as auto
        except Exception as _e2:
            logging.getLogger("cyrus.brain").error(
                "FATAL: UIAutomation still unavailable after cache clear (%s). "
                "Try: pip install --force-reinstall comtypes uiautomation",
                _e2,
                exc_info=True,
            )
            raise

import cyrus_common as _cyrus_common_module
from cyrus_common import (
    _CHAT_INPUT_HINT,
    VOICE_HINT,
    VSCODE_TITLE,
    WAKE_WORDS,
    ChatWatcher,
    PermissionWatcher,
    SessionManager,
    _assert_vscode_focus,
    _chat_input_coords,
    _chat_input_coords_lock,
    _extract_project,
    _fast_command,
    _is_answer_request,
    _make_alias,
    _resolve_project,
    _sanitize_for_speech,
    _strip_fillers,
    _vs_code_windows,
    clean_for_speech,
    register_chime_handlers,
)
from cyrus_log import setup_logging

# ── Module logger ──────────────────────────────────────────────────────────────
log = logging.getLogger("cyrus.brain")

# ── Configuration ──────────────────────────────────────────────────────────────
# Port constants are imported from cyrus_config so they can be overridden via
# CYRUS_BRAIN_PORT, CYRUS_HOOK_PORT, and CYRUS_MOBILE_PORT environment variables.

BRAIN_HOST = "0.0.0.0"
# BRAIN_PORT, HOOK_PORT, MOBILE_PORT imported from cyrus_config above

# ── Shared state ───────────────────────────────────────────────────────────────

_active_project: str = ""
_active_project_lock: threading.Lock = threading.Lock()

# ── Companion extension sessions ───────────────────────────────────────────────


@dataclass
class SessionInfo:
    """Tracks a connected companion extension session.

    Holds the asyncio StreamWriter for the active TCP connection so the
    brain can send messages back to the companion. The created_at timestamp
    allows stale sessions to be identified.
    """

    workspace: str
    safe: str
    port: int
    connection: asyncio.StreamWriter
    created_at: float = 0.0

    def __post_init__(self) -> None:
        """Set created_at to current time if not explicitly provided."""
        if self.created_at == 0.0:
            self.created_at = time.time()


# Registration sessions: workspace name → SessionInfo for active companion connections
_registered_sessions: dict[str, "SessionInfo"] = {}
# Protects all reads/writes to _registered_sessions from concurrent async handlers.
_sessions_lock: threading.Lock = threading.Lock()

_vscode_win_cache: dict = {}
# Protects all reads/writes to _vscode_win_cache from the submit thread and
# any other thread that caches VS Code window handles.
_vscode_win_cache_lock: threading.Lock = threading.Lock()

_project_locked: bool = False
_project_locked_lock: threading.Lock = threading.Lock()

_whisper_prompt: str = "Cyrus,"
# Protects _whisper_prompt written by SessionManager background thread and
# read by the async voice connection handler.
_whisper_prompt_lock: threading.Lock = threading.Lock()

# threading.Event: .is_set() → active, .set() → activate, .clear() → deactivate.
# Using Event instead of bool makes cross-thread visibility explicit and allows
# future use of .wait() for blocking on conversation state.
_conversation_active: threading.Event = threading.Event()

_tts_active_remote: bool = False  # True while voice service is playing TTS

# asyncio queues — set in main()
_speak_queue: asyncio.Queue = None  # (project, text) → sent to voice
_utterance_queue: asyncio.Queue = None  # utterances received from voice

# Mobile WebSocket clients
_mobile_clients: set = set()  # active websocket connections
# Protects _mobile_clients: add/discard happen in async handlers, while
# difference_update occurs in _send(). Use copy-under-lock when iterating.
_mobile_clients_lock: threading.Lock = threading.Lock()

# Dedicated submit thread queue — all VS Code UIA writes happen on one thread
_submit_request_queue: _stdlib_queue.Queue = _stdlib_queue.Queue()

# Voice writer — set when voice connects, None when disconnected
_voice_writer: asyncio.StreamWriter = None
_voice_lock = asyncio.Lock()

# Configure UIA and input automation — only available in non-HEADLESS mode.
if not HEADLESS:
    auto.uiautomation.SetGlobalSearchTimeout(2)
    pyautogui.FAILSAFE = False

# ── Send to voice ──────────────────────────────────────────────────────────────


async def _send(msg: dict) -> None:
    """Send one JSON message to voice + mobile clients. Fire-and-forget."""
    # Sanitize text fields so TTS engines don't read raw UTF-8 bytes
    for key in ("text", "full_text"):
        if key in msg and isinstance(msg[key], str):
            msg[key] = _sanitize_for_speech(msg[key])
    global _voice_writer
    # Send to TCP voice client
    if _voice_writer is not None:
        try:
            async with _voice_lock:
                _voice_writer.write((json.dumps(msg) + "\n").encode())
                await _voice_writer.drain()
        except Exception:
            _voice_writer = None
    # Broadcast to mobile WebSocket clients — copy under lock, send without lock.
    # This prevents race conditions with handle_mobile_ws which adds/discards
    # clients from a separate async context.
    if msg.get("type") in ("speak", "prompt", "thinking", "tool", "status"):
        with _mobile_clients_lock:
            clients_snapshot = set(_mobile_clients)
        if clients_snapshot:
            mobile_msg = dict(msg)
            if "full_text" in mobile_msg:
                mobile_msg["text"] = mobile_msg.pop("full_text")
            payload = json.dumps(mobile_msg)
            dead = set()
            for ws in clients_snapshot:
                try:
                    await ws.send(payload)
                except Exception:
                    dead.add(ws)
            if dead:
                with _mobile_clients_lock:
                    _mobile_clients.difference_update(dead)


def _send_threadsafe(msg: dict, loop: asyncio.AbstractEventLoop) -> None:
    """Thread-safe wrapper for _send, callable from background threads."""
    asyncio.run_coroutine_threadsafe(_send(msg), loop)


# ── Speak helpers (used by background threads via threadsafe wrapper) ──────────


async def _speak_worker() -> None:
    """Consume speak queue and forward to voice."""
    while True:
        item = await _speak_queue.get()
        project, text = item[0], item[1]
        full_text = item[2] if len(item) > 2 else None
        msg = {"type": "speak", "text": text, "project": project}
        if full_text:
            msg["full_text"] = full_text
        await _send(msg)


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


# ── Factory functions — wire brain-specific callbacks into common classes ──────


def _make_enqueue_speech_fn(loop: asyncio.AbstractEventLoop):
    """Create a speech-enqueue callable for ChatWatcher (brain backend)."""

    def enqueue_speech(
        project_name: str, text: str, full_text: str | None = None
    ) -> None:
        if full_text is not None:
            item = (project_name, text, full_text)
        else:
            item = (project_name, text)
        asyncio.run_coroutine_threadsafe(_speak_queue.put(item), loop)

    return enqueue_speech


def _make_chime_fn(loop: asyncio.AbstractEventLoop):
    """Create a chime callable for ChatWatcher (brain = websocket IPC)."""

    def chime() -> None:
        _send_threadsafe({"type": "chime"}, loop)

    return chime


def _make_speak_urgent_fn(loop: asyncio.AbstractEventLoop):
    """Create a speak-urgent callable for PermissionWatcher (brain backend)."""

    def speak_urgent(prompt: str) -> None:
        asyncio.run_coroutine_threadsafe(_speak_urgent(prompt), loop)

    return speak_urgent


def _make_stop_speech_fn(loop: asyncio.AbstractEventLoop):
    """Create a stop-speech callable for PermissionWatcher (brain backend)."""

    def stop_speech() -> None:
        _send_threadsafe({"type": "stop_speech"}, loop)

    return stop_speech


def _make_session_manager(loop: asyncio.AbstractEventLoop) -> SessionManager:
    """Create a SessionManager wired to the brain's websocket IPC backend."""

    def make_chat_watcher(project_name: str, subname: str) -> ChatWatcher:
        return ChatWatcher(
            project_name=project_name,
            target_subname=subname,
            enqueue_speech_fn=_make_enqueue_speech_fn(loop),
            chime_fn=_make_chime_fn(loop),
        )

    def make_perm_watcher(project_name: str, subname: str) -> PermissionWatcher:
        return PermissionWatcher(
            project_name=project_name,
            target_subname=subname,
            speak_urgent_fn=_make_speak_urgent_fn(loop),
            stop_speech_fn=_make_stop_speech_fn(loop),
        )

    def on_whisper_prompt(prompt: str) -> None:
        global _whisper_prompt
        with _whisper_prompt_lock:
            _whisper_prompt = prompt
        _send_threadsafe({"type": "whisper_prompt", "text": prompt}, loop)

    def get_active_project() -> str:
        with _active_project_lock:
            return _active_project

    return SessionManager(
        make_chat_watcher_fn=make_chat_watcher,
        make_perm_watcher_fn=make_perm_watcher,
        on_whisper_prompt_fn=on_whisper_prompt,
        is_active_project_fn=get_active_project,
    )


# ── Routing helpers ────────────────────────────────────────────────────────────


@dataclass
class CommandResult:
    """Return value from command handlers — describes what the dispatcher should do.

    Handlers return this instead of mutating globals directly. The dispatcher
    applies state changes under locks, queues TTS, and prints log messages.
    """

    spoken: str | None = None  # Text to speak via TTS (None = nothing to say)
    speak_project: str = ""  # Project name for TTS routing (empty = default)
    new_active_project: str | None = None  # Set _active_project if not None
    new_project_locked: bool | None = None  # Set _project_locked if not None
    skip_tts: bool = False  # True skips TTS queueing entirely
    log_message: str = ""  # Text to print to console (empty = skip)


def _handle_switch_project(
    cmd: dict,
    spoken: str,
    session_mgr,
    loop: asyncio.AbstractEventLoop,
    active_project: str,
) -> CommandResult:
    """Switch active project and lock routing to it."""
    log.debug("Executing command 'switch_project'")
    target = _resolve_project(cmd.get("project", ""), session_mgr.aliases)
    if target:
        session_mgr.on_session_switch(target)
        text = spoken or f"Switched to {target}. Routing locked."
        log.info("Command 'switch_project' completed: locked to '%s'", target)
        return CommandResult(
            spoken=text,
            new_active_project=target,
            new_project_locked=True,
            log_message=f"[Brain] {text}",
        )
    else:
        text = f"No session matching '{cmd.get('project', '')}' found."
        log.warning("switch_project: no match for '%s'", cmd.get("project", ""))
        return CommandResult(spoken=text, log_message=f"[Brain] {text}")


def _handle_unlock(
    cmd: dict,
    spoken: str,
    session_mgr,
    loop: asyncio.AbstractEventLoop,
    active_project: str,
) -> CommandResult:
    """Release project lock and return to auto-follow mode."""
    log.debug("Executing command 'unlock'")
    text = spoken or "Following window focus."
    log.info("Command 'unlock' completed")
    return CommandResult(
        spoken=text,
        new_project_locked=False,
        log_message="[Brain] Routing unlocked.",
    )


def _handle_which_project(
    cmd: dict,
    spoken: str,
    session_mgr,
    loop: asyncio.AbstractEventLoop,
    active_project: str,
) -> CommandResult:
    """Report current active project and lock status."""
    log.debug("Executing command 'which_project'")
    # Read _project_locked under its lock (read-only — no global statement needed)
    with _project_locked_lock:
        locked = _project_locked
    status = "locked" if locked else "following focus"
    text = spoken or f"Active project: {active_project or 'none'}, {status}."
    log.info("Command 'which_project' completed")
    return CommandResult(spoken=text, log_message=f"[Brain] {text}")


def _handle_last_message(
    cmd: dict,
    spoken: str,
    session_mgr,
    loop: asyncio.AbstractEventLoop,
    active_project: str,
) -> CommandResult:
    """Replay the last response in the active session."""
    log.debug("Executing command 'last_message'")
    resp = session_mgr.last_response(active_project)
    if resp:
        log.info("Command 'last_message' completed: replaying %d chars", len(resp))
        # Use speak_project so TTS is routed to the correct project session
        return CommandResult(spoken=resp, speak_project=active_project)
    else:
        text = spoken or f"No recorded response for {active_project or 'this session'}."
        log.warning("last_message: no recorded response for '%s'", active_project)
        return CommandResult(spoken=text, log_message=f"[Brain] {text}")


def _handle_rename_session(
    cmd: dict,
    spoken: str,
    session_mgr,
    loop: asyncio.AbstractEventLoop,
    active_project: str,
) -> CommandResult:
    """Rename a project session alias."""
    log.debug("Executing command 'rename'")
    new_name = cmd.get("name", "").strip()
    old_hint = cmd.get("old", "").strip()
    proj = (
        _resolve_project(old_hint, session_mgr.aliases) if old_hint else active_project
    )
    if proj and new_name:
        old_alias = next((a for a, p in session_mgr.aliases.items() if p == proj), proj)
        session_mgr.rename_alias(old_alias, new_name, proj)
        text = spoken or f"Renamed to '{new_name}'."
        log.info("Command 'rename' completed: '%s' → '%s'", proj, new_name)
        return CommandResult(
            spoken=text,
            # Print both the alias change and the confirmation
            log_message=f"[Brain] {proj} → alias '{new_name}'\n[Brain] {text}",
        )
    else:
        text = spoken or "Could not find that session to rename."
        log.warning("rename: no project match (proj=%r, new_name=%r)", proj, new_name)
        return CommandResult(spoken=text, log_message=f"[Brain] {text}")


def _handle_pause(
    cmd: dict,
    spoken: str,
    session_mgr,
    loop: asyncio.AbstractEventLoop,
    active_project: str,
) -> CommandResult:
    """Toggle listening pause state (delegates to voice service)."""
    log.debug("Executing command 'pause'")
    # Delegate to voice service; TTS is handled by voice, not the brain
    asyncio.run_coroutine_threadsafe(_send({"type": "pause"}), loop)
    log.info("Command 'pause' completed")
    return CommandResult(skip_tts=True)


# Dispatch table mapping command type strings → handler functions.
# To add a new command: write a handler above and add one entry here.
_COMMAND_HANDLERS: dict[str, object] = {
    "switch": _handle_switch_project,
    "unlock": _handle_unlock,
    "which_project": _handle_which_project,
    "last_message": _handle_last_message,
    "rename": _handle_rename_session,
    "pause": _handle_pause,
}


def _execute_cyrus_command(
    ctype: str, cmd: dict, spoken: str, session_mgr, loop: asyncio.AbstractEventLoop
) -> str:
    """Execute a Cyrus command using the dispatch table.

    Reads active_project under lock, delegates to the appropriate handler,
    then applies state mutations under locks and queues TTS based on the
    returned CommandResult. All handler exceptions are caught and logged —
    a bad command never crashes the listener.

    Returns:
        The spoken text produced by the handler, or ``""`` if the command
        produced no speech. Callers can inspect the text to decide whether to
        stay in conversation mode (e.g. if it ends with "?").
    """
    global _active_project, _project_locked

    log.debug("Executing command '%s'", ctype)

    handler = _COMMAND_HANDLERS.get(ctype)
    if not handler:
        log.warning("Unknown command type: '%s'", ctype)
        return ""

    # Read active_project snapshot under lock — handlers receive it as a parameter
    # so they never need to access the global directly.
    with _active_project_lock:
        active_project = _active_project

    try:
        result = handler(cmd, spoken, session_mgr, loop, active_project)
    except Exception:
        log.exception("Error executing command '%s'", ctype)
        return ""

    log.info("Command '%s' completed", ctype)

    # Apply state mutations under their respective locks
    if result.new_active_project is not None:
        with _active_project_lock:
            _active_project = result.new_active_project
    if result.new_project_locked is not None:
        with _project_locked_lock:
            _project_locked = result.new_project_locked

    # Queue TTS unless the handler opted out (e.g. pause delegates to voice)
    if not result.skip_tts and result.spoken:
        asyncio.run_coroutine_threadsafe(
            _speak_queue.put((result.speak_project, result.spoken)), loop
        )

    # Print log message if the handler set one
    if result.log_message:
        log.info("%s", result.log_message)

    return result.spoken or ""


# ── Active window tracker ──────────────────────────────────────────────────────


def _start_active_tracker(session_mgr: SessionManager, loop: asyncio.AbstractEventLoop):
    """Poll pygetwindow for the active VS Code window and update _active_project.

    In HEADLESS mode this function returns immediately — pygetwindow is
    unavailable on Linux/Docker.  The companion extension sends focus/blur
    messages to update the active project instead.
    """
    if HEADLESS:
        return
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
                    log.debug("Active project: %s", proj)
                    session_mgr.on_session_switch(proj)
        except Exception:
            pass
        time.sleep(0.5)


# ── VS Code submit ─────────────────────────────────────────────────────────────


def _find_chat_input(target_subname: str = "") -> object:
    subname = target_subname or VSCODE_TITLE
    vscode = auto.WindowControl(searchDepth=1, SubName=subname)
    if not vscode.Exists(2):
        vscode = auto.WindowControl(searchDepth=1, SubName=VSCODE_TITLE)
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


def _open_companion_connection(safe: str) -> socket.socket:
    """Open a socket to the Cyrus Companion extension for the given workspace.
    Windows: TCP localhost, port read from %LOCALAPPDATA%\\cyrus\\companion-{safe}.port
    Unix/Mac: AF_UNIX socket at /tmp/cyrus-companion-{safe}.sock
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        port_file = os.path.join(base, "cyrus", f"companion-{safe}.port")
        try:
            with open(port_file) as f:
                port = int(f.read().strip())
        except FileNotFoundError:
            log.error("Port file not found: %s", port_file, exc_info=True)
            raise
        except ValueError:
            log.error("Invalid port number in %s", port_file, exc_info=True)
            raise
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(("127.0.0.1", port))
        return s
    else:
        import tempfile

        sock_path = os.path.join(tempfile.gettempdir(), f"cyrus-companion-{safe}.sock")
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

    safe = re.sub(r"[^\w\-]", "_", proj or "default")[:40]

    try:
        with _open_companion_connection(safe) as s:
            # Include auth token so companion extension can validate the connection
            payload = json.dumps({"text": text, "token": AUTH_TOKEN}) + "\n"
            s.sendall(payload.encode("utf-8"))
            raw = b""
            while b"\n" not in raw:
                chunk = s.recv(4096)
                if not chunk:
                    break
                raw += chunk
            result = json.loads(raw.decode("utf-8").strip())
            if result.get("ok"):
                return True
            log.error("Extension error: %s", result.get("error"))
            return False
    except FileNotFoundError:
        # Discovery file or socket not found — extension not running
        return False
    except (ConnectionRefusedError, OSError) as e:
        log.warning("Companion extension unavailable: %s", e)
        return False
    except Exception as e:
        log.error("Companion extension error: %s", e, exc_info=True)
        return False


def _submit_to_vscode_impl(text: str) -> bool:
    """Runs on the dedicated submit thread.

    Uses pixel coords — no COM cross-thread issues.

    In HEADLESS mode only the companion extension path is used.  The UIA /
    pyautogui fallback requires Windows GUI libraries that are unavailable on
    Linux/Docker, so if the companion is down the submission fails gracefully.
    """
    # ── 0. Try companion extension (no pixel coords, cross-platform) ──────────
    if _submit_via_extension(text):
        return True
    if HEADLESS:
        # No UIA fallback available — companion is the only submit path.
        log.warning("Companion extension unavailable in HEADLESS mode — submit failed")
        return False
    log.warning("Companion extension unavailable -- falling back to UIA")

    with _active_project_lock:
        proj = _active_project

    # ── 1. Resolve coords BEFORE activating window ─────────────────────────────
    # Busy-wait with lock: check under lock, sleep outside lock so other threads
    # can write coords while we wait.
    deadline = time.time() + 6.0
    while time.time() < deadline:
        with _chat_input_coords_lock:
            if proj in _chat_input_coords:
                break
        time.sleep(0.3)
    with _chat_input_coords_lock:
        coords = _chat_input_coords.get(proj)

    if not coords:
        # Last-resort UIA search — no window activation yet
        target_sub = f"{proj} - Visual Studio Code" if proj else VSCODE_TITLE
        ctrl = _find_chat_input(target_sub)
        if ctrl:
            try:
                r = ctrl.BoundingRectangle
                if r.width() > 0:
                    coords = ((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                    with _chat_input_coords_lock:
                        _chat_input_coords[proj] = coords
            except Exception:
                pass
        if not coords:
            log.error("Claude chat input not found.")
            return False

    # ── 2. Find and activate VS Code window ───────────────────────────────────
    with _vscode_win_cache_lock:
        win = _vscode_win_cache.get(proj)
    if win is not None:
        try:
            if VSCODE_TITLE not in (win.title or ""):
                raise ValueError("wrong window")
        except Exception:
            win = None
            with _vscode_win_cache_lock:
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
            log.error("VS Code window not found.")
            return False
        win = matches[0]
        with _vscode_win_cache_lock:
            _vscode_win_cache[proj] = win

    try:
        win.activate()
        time.sleep(0.25)
    except Exception:
        pass

    # ── 3. Click chat input by pixel coords ───────────────────────────────────
    # Guard: verify VS Code still has focus before sending keystrokes
    try:
        _assert_vscode_focus()
    except RuntimeError as _focus_err:
        log.error(
            "Submit aborted — focus check failed before click: %s",
            _focus_err,
            exc_info=True,
        )
        return False
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
    time.sleep(0.15)
    # Re-assert focus before Enter — focus can be stolen between paste and submit
    try:
        win.activate()
    except Exception:
        pass
    time.sleep(0.05)
    try:
        _assert_vscode_focus()
    except RuntimeError as _focus_err:
        log.error(
            "Submit aborted — focus check failed before Enter: %s",
            _focus_err,
            exc_info=True,
        )
        return False
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
    """Dedicated thread: COM initialized once, handles all VS Code submits.

    In HEADLESS mode, comtypes is not imported so CoInitializeEx() is skipped.
    Submissions go via the companion extension only (no UIA).
    """
    if not HEADLESS:
        # Initialize a COM STA apartment for UIA operations on this thread.
        # comtypes is only imported in non-HEADLESS mode.
        comtypes.CoInitializeEx()
    while True:
        text, ev, result_holder = _submit_request_queue.get()
        try:
            result_holder[0] = _submit_to_vscode_impl(text)
        except Exception as e:
            log.error("Submit error: %s", e, exc_info=True)
            result_holder[0] = False
        ev.set()


# ── Voice reader — process incoming messages from voice service ────────────────


async def voice_reader(
    reader: asyncio.StreamReader,
    session_mgr: SessionManager,
    loop: asyncio.AbstractEventLoop,
) -> None:
    global _tts_active_remote

    while True:
        try:
            line = await reader.readline()
            if not line:
                break
            msg = json.loads(line.decode().strip())
            mtype = msg.get("type", "")

            if mtype == "tts_start":
                _tts_active_remote = True

            elif mtype == "tts_end":
                _tts_active_remote = False

            elif mtype == "utterance":
                text = msg.get("text", "").strip()
                during_tts = msg.get("during_tts", False)
                if not text:
                    continue
                await _utterance_queue.put((text, during_tts))

        except json.JSONDecodeError:
            pass
        except Exception as e:
            log.error("Voice reader error: %s", e, exc_info=True)
            break


# ── Mobile WebSocket handler ──────────────────────────────────────────────────


async def handle_mobile_ws(ws) -> None:
    """Handle a single mobile WebSocket client.

    The first message must be an auth handshake: {"type": "auth", "token": "..."}.
    Clients that omit the auth message or send the wrong token are disconnected
    immediately.  Subsequent messages are processed normally (utterance / ping).
    """
    addr = ws.remote_address
    log.info("Mobile client connected: %s", addr)

    # ── Authentication handshake ───────────────────────────────────────────────
    # Expect the first message to carry the shared-secret token.  Reject
    # connections that mismatch; log the address, not the expected token value.
    try:
        first_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        first_msg = json.loads(first_raw)
        received_token = first_msg.get("token", "")
        if not validate_auth_token(received_token):
            log.warning("Mobile auth failed from %s — unauthorized", addr)
            # Send generic error (no token details) then close
            await ws.send(json.dumps({"error": "unauthorized"}))
            await ws.close()
            return
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
        log.warning("Mobile auth error from %s: %s", addr, e)
        try:
            await ws.close()
        except Exception:
            pass
        return

    # Authentication succeeded — acknowledge before joining broadcast set
    await ws.send(json.dumps({"type": "auth_ok"}))
    with _mobile_clients_lock:
        _mobile_clients.add(ws)
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
                mtype = msg.get("type", "")
                if mtype == "utterance":
                    text = msg.get("text", "").strip()
                    if text:
                        await _utterance_queue.put((text, False))
                elif mtype == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except Exception as e:
        log.error("Mobile client error: %s: %s", type(e).__name__, e, exc_info=True)
    finally:
        with _mobile_clients_lock:
            _mobile_clients.discard(ws)
        log.info(
            "Mobile client disconnected: %s (close_code=%s, close_reason=%s)",
            addr,
            ws.close_code,
            ws.close_reason,
        )


# ── Utterance routing loop ─────────────────────────────────────────────────────


async def routing_loop(
    session_mgr: SessionManager, loop: asyncio.AbstractEventLoop
) -> None:
    global _active_project

    while True:
        text, during_tts = await _utterance_queue.get()

        # Echo guard: only wake-word interrupts get through during TTS
        if during_tts or _tts_active_remote:
            fw = text.lower().strip().split()
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
                    text = parts[1].lstrip(", ").strip() if len(parts) > 1 else text
                if pw.handle_prompt_response(text):
                    handled = True
                    break
        if handled:
            continue

        # Wake word check
        words = text.lower().strip().split()
        first = words[0].rstrip(",.!?") if words else ""

        if _conversation_active.is_set():
            if first in WAKE_WORDS:
                rest = text.split(None, 1)
                text = rest[1].lstrip(", ").strip() if len(rest) > 1 else ""
            if not text:
                continue
            log.debug("Conversation heard: %s", text)
        else:
            if first not in WAKE_WORDS:
                log.debug("Ignored -- say 'Cyrus, ...' (heard: %s)", first)
                continue
            rest = text.split(None, 1)
            text = rest[1].lstrip(", ").strip() if len(rest) > 1 else ""
            if not text:
                log.debug("Wake word -- listening for command...")
                await _send({"type": "listen_chime"})
                try:
                    follow_text, _ = await asyncio.wait_for(
                        _utterance_queue.get(), timeout=6.0
                    )
                    fw = follow_text.lower().strip().split()
                    if fw and fw[0].rstrip(",.!?") in WAKE_WORDS:
                        parts = follow_text.split(None, 1)
                        follow_text = (
                            parts[1].lstrip(", ").strip() if len(parts) > 1 else ""
                        )
                    text = follow_text
                    if not text:
                        log.debug("No command heard")
                        continue
                    log.debug("Follow-up text: %s", text)
                except asyncio.TimeoutError:
                    log.debug("No command heard (timeout)")
                    continue

        # ── Route ─────────────────────────────────────────────────────────────
        fast = _fast_command(text)

        if fast is not None:
            # Meta-command detected — execute via dispatch table.
            ctype = fast.get("command", "")
            log.debug("Brain command: %s", ctype)
            cmd_spoken = _execute_cyrus_command(ctype, fast, "", session_mgr, loop)
            # Stay in conversation mode if the command response is a question
            # (e.g. "Which project do you mean?") so the user can reply without
            # repeating the wake word.
            if cmd_spoken.rstrip().endswith("?"):
                _conversation_active.set()
            else:
                _conversation_active.clear()

        elif _is_answer_request(text):
            with _active_project_lock:
                proj = _active_project
            resp = (
                session_mgr.last_response(proj)
                or "I don't have a recent response to share."
            )
            resp_words = resp.split()
            if len(resp_words) > 30:
                resp = " ".join(resp_words[:30]) + ". See the chat for more."
            if resp:
                suffix = "..." if len(resp) > 80 else ""
                log.info("Brain answers: %s", resp[:80] + suffix)
                await _speak_queue.put(("", resp))
            _conversation_active.clear()

        else:  # forward to LLM
            raw_msg = _strip_fillers(text)
            message = raw_msg + VOICE_HINT
            with _active_project_lock:
                proj = _active_project
            log.info("You [%s]: %s", proj or "VS Code", message)
            try:
                submitted = await asyncio.wait_for(
                    loop.run_in_executor(None, submit_to_vscode, message),
                    timeout=12.0,
                )
            except asyncio.TimeoutError:
                log.warning("Submit timed out.")
                submitted = False
            if not submitted:
                log.error("Could not find VS Code window.")
            else:
                await _send({"type": "chime"})
                await _send({"type": "prompt", "text": raw_msg, "project": proj or ""})
                await _send({"type": "thinking"})
            _conversation_active.clear()


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


async def handle_hook_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    session_mgr: "SessionManager",
) -> None:
    """
    Accepts a single connection from cyrus_hook.py, reads one JSON message,
    validates the auth token, then dispatches on event type:
    stop / pre_tool / post_tool / notification.
    """
    addr = writer.get_extra_info("peername")
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=3.0)
        if not raw:
            return
        msg = json.loads(raw.decode().strip())

        # ── Authentication ─────────────────────────────────────────────────────
        # Every hook message must carry the shared-secret token.  Reject
        # connections that omit or mismatch the token; log the address (not the
        # expected token value) so the operator can identify the source.
        received_token = msg.get("token", "")
        if not validate_auth_token(received_token):
            # Log the rejection — do NOT send the token back or expose it
            log.warning("Hook connection rejected: invalid auth token from %s", addr)
            # Send generic error (no token details) then close
            writer.write(json.dumps({"error": "unauthorized"}).encode() + b"\n")
            writer.close()
            return

        event = msg.get("event", "stop")
        cwd = msg.get("cwd", "")
        proj = _resolve_project_from_cwd(cwd, session_mgr)
        log.debug("Hook event=%s, cwd=%r, resolved_proj=%r", event, cwd, proj)
        loop = asyncio.get_event_loop()

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
            log.info("Cyrus [%s] (hook): %s", proj or "Claude", preview)
            await _speak_queue.put((proj, spoken, text))

        elif event == "pre_tool":
            tool = msg.get("tool", "")
            cmd = msg.get("command", "")
            log.debug(
                "pre_tool received: tool=%s, proj=%r, cmd=%s", tool, proj, cmd[:60]
            )
            await _send({"type": "tool", "tool": tool, "command": cmd, "project": proj})
            pw = session_mgr._perm_watchers.get(proj) or next(
                iter(session_mgr._perm_watchers.values()), None
            )
            if pw:
                pw.arm_from_hook(tool, cmd, loop)
            else:
                log.warning(
                    "No PermissionWatcher found for proj=%r, known=%s",
                    proj,
                    list(session_mgr._perm_watchers.keys()),
                )

        elif event == "post_tool":
            tool = msg.get("tool", "")
            prefix = f"In {proj}: " if proj else ""
            if tool == "Bash":
                exit_code = msg.get("exit_code", 0)
                if exit_code != 0:
                    spoken = f"{prefix}Command failed with exit code {exit_code}."
                    log.info("PostTool: %s", spoken)
                    await _speak_urgent(spoken)
            elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                file_path = msg.get("file_path", "")
                basename = os.path.basename(file_path) if file_path else "a file"
                verb = "wrote" if tool == "Write" else "edited"
                spoken = f"{prefix}Claude {verb} {basename}."
                log.info("PostTool: %s", spoken)
                await _speak_queue.put(("", spoken))

        elif event == "notification":
            message = (msg.get("message") or "").strip()
            if message:
                prefix = f"In {proj}: " if proj else ""
                spoken = f"{prefix}{message}"
                log.info("Notification: %s", spoken)
                await _speak_urgent(spoken)

        elif event == "pre_compact":
            trigger = msg.get("trigger", "auto")
            reason = "manual compact" if trigger == "manual" else "context window full"
            spoken = f"Memory compacting: {reason}."
            log.info("PreCompact: %s (proj=%r)", spoken, proj)
            await _send(
                {
                    "type": "status",
                    "status": "compacting",
                    "trigger": trigger,
                    "project": proj,
                }
            )
            await _speak_queue.put((proj, spoken))

    except asyncio.TimeoutError:
        pass
    except Exception as e:
        log.error("Hook handler error: %s", e, exc_info=True)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ── TCP server ─────────────────────────────────────────────────────────────────


async def handle_voice_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    session_mgr: SessionManager,
    loop: asyncio.AbstractEventLoop,
) -> None:
    global _voice_writer
    addr = writer.get_extra_info("peername")

    # ── Authentication handshake ───────────────────────────────────────────────
    # Voice must send {"type": "auth", "token": "..."} as its first message.
    # Reject connections that omit or mismatch the token; log the address only
    # (not the expected token value) to avoid credential exposure in logs.
    try:
        first_raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not first_raw:
            log.warning("Voice auth failed from %s — empty first message", addr)
            writer.close()
            return
        first_msg = json.loads(first_raw.decode().strip())
        received_token = first_msg.get("token", "")
        if not validate_auth_token(received_token):
            log.warning("Voice auth failed from %s — unauthorized", addr)
            writer.write((json.dumps({"error": "unauthorized"}) + "\n").encode())
            writer.close()
            return
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
        log.warning("Voice auth error from %s: %s", addr, e)
        try:
            writer.close()
        except Exception:
            pass
        return

    # Authentication succeeded — acknowledge before entering voice loop
    writer.write(json.dumps({"type": "auth_ok"}).encode() + b"\n")
    await writer.drain()
    log.info("Voice service connected from %s", addr)
    _voice_writer = writer

    # Announce sessions to voice so it can prime Whisper prompt
    with _whisper_prompt_lock:
        current_prompt = _whisper_prompt
    if current_prompt:
        await _send({"type": "whisper_prompt", "text": current_prompt})

    # Startup greeting
    windows = _vs_code_windows()
    if not windows:
        greeting = "Cyrus is online. No VS Code sessions detected."
    elif len(windows) == 1:
        greeting = f"Cyrus is online. Session: {_make_alias(windows[0][0])}."
    else:
        names = ", ".join(_make_alias(p) for p, _ in windows)
        greeting = f"Cyrus is online. {len(windows)} sessions: {names}."

    await _send({"type": "speak", "text": greeting, "project": ""})
    await _send({"type": "listen_chime"})
    log.info("Listening for wake word...")

    try:
        await voice_reader(reader, session_mgr, loop)
    finally:
        _voice_writer = None
        log.info("Voice service disconnected.")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ── Companion extension registration handler ───────────────────────────────────


async def _handle_registration_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle one companion extension connection on COMPANION_PORT.

    Reads line-delimited JSON messages and dispatches on type:
    - register: authenticate and track session in _registered_sessions
    - focus: set _active_project to the workspace name
    - blur: clear _active_project if it matches the workspace
    - permission_respond: log and route to PermissionWatcher (stub)
    - prompt_respond: log and route to waiting code (stub)

    On disconnect (EOF or exception), removes the session from both
    cyrus_brain._registered_sessions and cyrus_common._registered_sessions.
    """
    peer = writer.get_extra_info("peername")
    addr = f"{peer[0]}:{peer[1]}" if peer else "unknown"
    log.info("[REG] New connection from %s", addr)

    session_workspace: str | None = None
    authenticated = False

    try:
        while True:
            data = await reader.readline()
            if not data:
                break  # EOF — client disconnected

            try:
                msg = json.loads(data.decode().strip())
            except json.JSONDecodeError:
                log.debug("[REG] Skipping malformed JSON line from %s", addr)
                continue

            msg_type = msg.get("type", "")

            # ── Authentication ─────────────────────────────────────────────
            # First message must be "register" with a valid auth token.
            # Subsequent messages on an authenticated connection don't need
            # to re-send the token.
            if not authenticated:
                if msg_type == "register":
                    received_token = msg.get("token", "")
                    if not validate_auth_token(received_token):
                        log.warning(
                            "[REG] Connection rejected: invalid auth token from %s",
                            addr,
                        )
                        writer.write(
                            json.dumps({"error": "unauthorized"}).encode() + b"\n"
                        )
                        writer.close()
                        return
                    authenticated = True
                else:
                    # Non-register first message: reject unauthenticated
                    log.warning(
                        "[REG] Unexpected first message type %r from %s"
                        " — expected register",
                        msg_type,
                        addr,
                    )
                    writer.write(json.dumps({"error": "unauthorized"}).encode() + b"\n")
                    writer.close()
                    return

            if msg_type == "register":
                workspace = msg.get("workspace", "unknown")
                safe = msg.get("safe", workspace)
                port = msg.get("port", 8768)

                info = SessionInfo(
                    workspace=workspace,
                    safe=safe,
                    port=port,
                    connection=writer,
                )
                with _sessions_lock:
                    _registered_sessions[workspace] = info
                # Also update cyrus_common._registered_sessions for
                # _vs_code_windows() compat — expects {workspace: "workspace - VS Code"}
                _cyrus_common_module._registered_sessions[workspace] = (
                    f"{workspace} - Visual Studio Code"
                )
                session_workspace = workspace
                log.info("[REG] %s registered (port %s)", workspace, port)

            elif msg_type == "focus":
                workspace = msg.get("workspace")
                if workspace:
                    global _active_project
                    with _active_project_lock:
                        _active_project = workspace
                    log.info("[REG] Active project: %s", workspace)

            elif msg_type == "blur":
                workspace = msg.get("workspace")
                if workspace:
                    with _active_project_lock:
                        if _active_project == workspace:
                            _active_project = ""
                            log.info(
                                "[REG] Blur: %s (active project cleared)",
                                workspace,
                            )
                        else:
                            log.debug(
                                "[REG] Blur: %s (not active, current=%s)",
                                workspace,
                                _active_project,
                            )

            elif msg_type == "permission_respond":
                action = msg.get("action", "")
                log.info(
                    "[REG] permission_respond: action=%s (workspace=%s)",
                    action,
                    session_workspace,
                )
                # TODO: route to PermissionWatcher when full watcher integration lands

            elif msg_type == "prompt_respond":
                text = msg.get("text", "")
                preview = text[:50] if text else ""
                log.info(
                    "[REG] prompt_respond: %s... (workspace=%s)",
                    preview,
                    session_workspace,
                )
                # TODO: route to waiting prompt handler when prompt flow is implemented

            else:
                log.debug("[REG] Unknown message type %r from %s", msg_type, addr)

    except Exception as e:
        log.error("[REG] Error handling connection from %s: %s", addr, e, exc_info=True)
    finally:
        if session_workspace:
            with _sessions_lock:
                _registered_sessions.pop(session_workspace, None)
            _cyrus_common_module._registered_sessions.pop(session_workspace, None)
            log.info("[REG] %s disconnected", session_workspace)
        try:
            writer.close()
        except Exception:
            pass


# ── Session state persistence ──────────────────────────────────────────────────


def _get_state_file() -> Path:
    """Resolve and return the session state file path.

    Reads ``CYRUS_STATE_FILE`` from the environment at call time so tests and
    operators can override the path without reloading the module.  If the var
    is set to a non-empty string that path is returned directly; otherwise the
    default ``~/.cyrus/state.json`` is used and its parent directory is created.

    Returns:
        A ``pathlib.Path`` pointing to the state file location.
    """
    # Read at call-time (not module import) so env overrides take effect.
    custom = os.environ.get("CYRUS_STATE_FILE", "")
    if custom:
        return Path(custom)
    default = Path.home() / ".cyrus" / "state.json"
    # Create parent directory on first run — safe if it already exists.
    default.parent.mkdir(parents=True, exist_ok=True)
    return default


def _save_state(session_mgr: "SessionManager") -> None:
    """Serialize brain session state to disk using an atomic write.

    Collects aliases, pending queues, and project names from ``session_mgr``
    and writes them to the state file as JSON.  Uses a write-to-temp-then-
    rename strategy to prevent partial writes from corrupting the file.
    File permissions are restricted to 0600 on Unix after the write.

    Args:
        session_mgr: The live ``SessionManager`` instance whose state is saved.
    """
    state = {
        "version": 1,
        "timestamp": time.time(),
        "aliases": session_mgr.aliases,  # returns a copy via the property
        "projects": list(session_mgr._chat_watchers.keys()),
        "pending_queues": {
            proj: list(cw._pending_queue)
            for proj, cw in session_mgr._chat_watchers.items()
        },
    }

    state_file = _get_state_file()
    # Write to a sibling .tmp file first; rename atomically so readers never
    # see a partially-written state file (POSIX rename(2) is atomic).
    temp_file = state_file.with_suffix(".tmp")

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        temp_file.replace(state_file)
        # Restrict read/write to the owner only — state may contain path names.
        try:
            state_file.chmod(0o600)
        except (NotImplementedError, AttributeError):
            # chmod is a no-op on Windows; silently skip.
            pass
        log.info("[State] Saved to %s (%d aliases)", state_file, len(state["aliases"]))
    except Exception as e:
        log.error(
            "[State] Failed to save state to %s: %s",
            state_file,
            e,
            exc_info=True,
        )


def _load_state(session_mgr: "SessionManager") -> None:
    """Restore brain session state from disk into ``session_mgr``.

    Handles the following failure modes without raising:
    - Missing state file (normal on first run)
    - Invalid / corrupted JSON
    - Unsupported state version

    Aliases are merged into the existing ``session_mgr._aliases`` dict so
    that any aliases already seeded by ``_init_session()`` are preserved.

    Pending queues are stored in the file for manual recovery but are NOT
    auto-replayed on startup (per interview Q&A decision) — the user triggers
    replay by switching to the project ("switch to X").

    Args:
        session_mgr: The ``SessionManager`` instance to restore state into.
    """
    state_file = _get_state_file()

    if not state_file.exists():
        log.info("[State] No state file at %s — starting fresh", state_file)
        return

    try:
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
    except json.JSONDecodeError as e:
        log.warning(
            "[State] Corrupted state file at %s (%s) — starting fresh",
            state_file,
            e,
        )
        return
    except Exception as e:
        log.error(
            "[State] Failed to read state file %s: %s — starting fresh",
            state_file,
            e,
            exc_info=True,
        )
        return

    version = state.get("version", 0)
    if version != 1:
        log.warning(
            "[State] Unsupported state version %s in %s — skipping restore",
            version,
            state_file,
        )
        return

    # Restore aliases — merge so session-discovery aliases are not overwritten.
    aliases = state.get("aliases", {})
    if isinstance(aliases, dict):
        session_mgr._aliases.update(aliases)
        log.info("[State] Restored %d aliases from %s", len(aliases), state_file)

    # Pending queues are loaded for informational purposes; not auto-replayed.
    pending = state.get("pending_queues", {})
    if pending:
        log.info(
            "[State] %d project(s) had pending queues at last shutdown"
            " (not auto-replayed)",
            len(pending),
        )


# ── Subsystem initializers ─────────────────────────────────────────────────────


def _init_queues() -> tuple[asyncio.Queue, asyncio.Queue]:
    """Initialize the communication queues between brain subsystems.

    Returns a fresh (speak_queue, utterance_queue) pair on every call so
    there is no stale state across restarts. Callers must assign the return
    values to the module globals before starting any dependent tasks.
    """
    return asyncio.Queue(), asyncio.Queue()


def _init_session(loop: asyncio.AbstractEventLoop) -> "SessionManager":
    """Create, configure, and start the SessionManager; seed the active project.

    Seeds _active_project to the first detected VS Code window title so the
    routing loop has a project context available from the very first utterance —
    before the window-focus tracker fires its initial update.
    """
    global _active_project
    session_mgr = _make_session_manager(loop)
    session_mgr.start()
    # Seed the active project from the first detected VS Code window so routing
    # works immediately without waiting for a window-focus event.
    first = _vs_code_windows()
    if first:
        with _active_project_lock:
            _active_project = first[0][0]
    return session_mgr


def _init_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    session_mgr: "SessionManager",
) -> None:
    """Register SIGTERM/SIGINT handlers that save state then stop the event loop.

    Uses ``loop.add_signal_handler()`` for clean asyncio integration on Unix.
    Falls back to ``atexit.register()`` on Windows where
    ``add_signal_handler()`` raises ``NotImplementedError``.

    Args:
        loop: The running asyncio event loop.
        session_mgr: The live ``SessionManager`` whose state is saved on exit.
    """

    def _shutdown_handler() -> None:
        log.info("Shutdown signal received — saving state...")
        _save_state(session_mgr)
        loop.stop()

    try:
        loop.add_signal_handler(signal.SIGTERM, _shutdown_handler)
        loop.add_signal_handler(signal.SIGINT, _shutdown_handler)
    except (NotImplementedError, AttributeError):
        # Windows: asyncio does not support add_signal_handler().
        # Fall back to atexit so state is saved on normal process exit.
        atexit.register(_save_state, session_mgr)


def _init_background_threads(
    session_mgr: "SessionManager",
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Start the window-focus tracker and VS Code submit worker as daemon threads.

    Both threads are daemons so they exit cleanly when the process exits.
    The submit worker owns a single COM STA apartment for all VS Code UIA
    writes, preventing race conditions when multiple coroutines need to type.
    """
    # Window focus tracker — updates _active_project when the user switches windows
    threading.Thread(
        target=_start_active_tracker,
        args=(session_mgr, loop),
        daemon=True,
    ).start()
    # VS Code submit worker — single COM apartment, stable across sessions
    threading.Thread(target=_submit_worker, daemon=True).start()


def _init_async_tasks(
    session_mgr: "SessionManager",
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Schedule the speak-worker and routing-loop as fire-and-forget async tasks.

    Both coroutines run concurrently alongside serve_forever() on the TCP/WS
    servers. The speak worker drains _speak_queue and forwards messages to the
    voice service; the routing loop processes inbound utterances and dispatches
    commands.
    """
    asyncio.create_task(_speak_worker())
    asyncio.create_task(routing_loop(session_mgr, loop))


async def _start_health_server(host: str) -> "_aiohttp_web.AppRunner":
    """Start the HTTP health check server on HEALTH_PORT (default 8771).

    Creates an aiohttp application with a single GET /health route that
    returns brain status as JSON.  All other paths return 404.  Access logs
    are suppressed (access_log=None) to avoid flooding the log with the
    frequent probe requests that Docker and Kubernetes send every 30 s.

    The server runs as a non-blocking coroutine integrated with the event loop
    — no separate thread is needed.

    Args:
        host: Interface to bind (e.g. ``"0.0.0.0"`` or ``"127.0.0.1"``).

    Returns:
        The ``AppRunner`` that manages the aiohttp server lifecycle.  Call
        ``await runner.cleanup()`` to shut down the server gracefully.
    """

    async def health_handler(
        request: "_aiohttp_web.Request",
    ) -> "_aiohttp_web.Response":
        """Return brain status JSON for liveness probes and monitoring tools."""
        with _active_project_lock:
            project = _active_project
        with _sessions_lock:
            session_count = len(_registered_sessions)
        return _aiohttp_web.json_response(
            {
                "status": "ok",
                "timestamp": time.time(),
                "sessions": session_count,
                "active_project": project,
                "headless": HEADLESS,
            }
        )

    app = _aiohttp_web.Application()
    app.router.add_get("/health", health_handler)

    # access_log=None silences per-request access logs that would flood the
    # output with ~2880 lines/day per container from Docker/k8s health probes.
    runner = _aiohttp_web.AppRunner(app, access_log=None)
    await runner.setup()
    site = _aiohttp_web.TCPSite(runner, host, HEALTH_PORT)
    await site.start()
    log.info("Health check server listening on %s:%s", host, HEALTH_PORT)
    return runner


async def _init_servers(
    host: str,
    port: int,
    session_mgr: "SessionManager",
    loop: asyncio.AbstractEventLoop,
) -> tuple:
    """Bind TCP, WebSocket, and HTTP health servers; return all server objects.

    Returns (voice_server, hook_server, mobile_server, reg_server,
    health_runner).  The first two are asyncio.Server objects managed via
    async context managers; mobile_server is a websockets.WebSocketServer
    closed via wait_closed(); reg_server is an asyncio.Server or None
    (headless only); health_runner is an aiohttp.AppRunner — call
    ``await health_runner.cleanup()`` to shut it down.
    """
    # Voice TCP (port 8766) — receives utterances and TTS status from cyrus_voice.py
    voice_server = await asyncio.start_server(
        lambda r, w: handle_voice_connection(r, w, session_mgr, loop),
        host,
        port,
    )
    addr = voice_server.sockets[0].getsockname()
    log.info("Listening for voice service on %s:%s", addr[0], addr[1])

    # Hook TCP (port 8767) — Claude Code Stop hook sends completion events here
    hook_server = await asyncio.start_server(
        lambda r, w: handle_hook_connection(r, w, session_mgr),
        host,
        HOOK_PORT,
    )
    hook_addr = hook_server.sockets[0].getsockname()
    log.info("Listening for Claude hooks on %s:%s", hook_addr[0], hook_addr[1])

    # Mobile WebSocket (port 8769) — streams events to the mobile companion app
    mobile_server = await websockets.serve(
        handle_mobile_ws,
        host,
        MOBILE_PORT,
        ping_interval=None,
        ping_timeout=None,
    )
    log.info("Listening for mobile clients on %s:%s (WebSocket)", host, MOBILE_PORT)

    # Registration TCP (port 8770) — companion extension registers here in
    # HEADLESS mode. Non-headless uses native window tracking instead.
    reg_server = None
    if HEADLESS:
        reg_server = await asyncio.start_server(
            _handle_registration_client,
            host,
            COMPANION_PORT,
        )
        reg_addr = reg_server.sockets[0].getsockname()
        log.info(
            "Listening for companion registrations on %s:%s", reg_addr[0], reg_addr[1]
        )

    # Health HTTP (port 8771) — liveness probes from Docker/k8s hit this endpoint
    health_runner = await _start_health_server(host)

    return voice_server, hook_server, mobile_server, reg_server, health_runner


# ── Main ───────────────────────────────────────────────────────────────────────


async def main() -> None:
    """Initialize and run Cyrus Brain — logic and VS Code watcher service."""
    global _speak_queue, _utterance_queue

    # Startup sequence:
    # 1. Queues initialized (enables inter-task communication)
    # 2. Chime handlers registered (enables audio feedback to voice service)
    # 3. Session manager started (scans VS Code windows, seeds active project)
    # 4. Background threads started (window tracker + VS Code submit worker)
    # 5. Async tasks created (speak worker + routing loop)
    # 6. Servers started (voice TCP :8766, hook TCP :8767, mobile WS :8769)

    setup_logging("cyrus")

    if HEADLESS:
        log.info("Brain running in HEADLESS mode — Windows GUI paths disabled")
        log.info("Companion extension registration required for full functionality")

    parser = argparse.ArgumentParser(description="Cyrus Brain — logic/watcher service")
    parser.add_argument("--host", default=BRAIN_HOST, help="Listen host")
    parser.add_argument("--port", type=int, default=BRAIN_PORT, help="Listen port")
    args = parser.parse_args()
    loop = asyncio.get_event_loop()
    _speak_queue, _utterance_queue = _init_queues()
    register_chime_handlers(
        chime_fn=lambda: _send_threadsafe({"type": "chime"}, loop),
        listen_chime_fn=lambda: _send_threadsafe({"type": "listen_chime"}, loop),
    )
    session_mgr = _init_session(loop)
    _load_state(session_mgr)
    _init_signal_handlers(loop, session_mgr)
    _init_background_threads(session_mgr, loop)
    _init_async_tasks(session_mgr, loop)
    servers = await _init_servers(args.host, args.port, session_mgr, loop)
    voice_server, hook_server, mobile_server, reg_server, health_runner = servers
    log.info("Waiting for voice to connect...")
    coros = [
        voice_server.serve_forever(),
        hook_server.serve_forever(),
        mobile_server.wait_closed(),
    ]
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(voice_server)
        await stack.enter_async_context(hook_server)
        if reg_server is not None:
            await stack.enter_async_context(reg_server)
            coros.append(reg_server.serve_forever())
        stack.push_async_callback(health_runner.cleanup)
        await asyncio.gather(*coros)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Cyrus Brain signing off.")
