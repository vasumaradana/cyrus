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
import json
import logging
import os
import queue as _stdlib_queue
import re
import socket
import threading
import time
from dataclasses import dataclass

import comtypes
import pyautogui
import pygetwindow as gw
import pyperclip
import websockets

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

BRAIN_HOST = "0.0.0.0"
BRAIN_PORT = 8766
HOOK_PORT = 8767  # Claude Code Stop hook sends here
MOBILE_PORT = 8769  # WebSocket endpoint for mobile clients

# ── Shared state ───────────────────────────────────────────────────────────────

_active_project: str = ""
_active_project_lock: threading.Lock = threading.Lock()

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
        log.warning(
            "rename: no project match (proj=%r, new_name=%r)", proj, new_name
        )
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
    """
    # ── 0. Try companion extension (no pixel coords, cross-platform) ──────────
    if _submit_via_extension(text):
        return True
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
    """Dedicated thread: COM initialized once, handles all VS Code submits."""
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
    """Handle a single mobile WebSocket client."""
    with _mobile_clients_lock:
        _mobile_clients.add(ws)
    addr = ws.remote_address
    log.info("Mobile client connected: %s", addr)
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
    and dispatches on event type: stop / pre_tool / post_tool / notification.
    """
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=3.0)
        if not raw:
            return
        msg = json.loads(raw.decode().strip())
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


async def _init_servers(
    host: str,
    port: int,
    session_mgr: "SessionManager",
    loop: asyncio.AbstractEventLoop,
) -> tuple:
    """Bind TCP and WebSocket servers and print their listening addresses.

    Returns (voice_server, hook_server, mobile_server). The first two are
    asyncio.Server objects that must be kept alive via an async context
    manager; mobile_server is a websockets.WebSocketServer closed via
    wait_closed().
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

    return voice_server, hook_server, mobile_server


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
    _init_background_threads(session_mgr, loop)
    _init_async_tasks(session_mgr, loop)
    voice_server, hook_server, mobile_server = await _init_servers(
        args.host, args.port, session_mgr, loop
    )
    log.info("Waiting for voice to connect...")

    async with voice_server, hook_server:
        await asyncio.gather(
            voice_server.serve_forever(),
            hook_server.serve_forever(),
            mobile_server.wait_closed(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Cyrus Brain signing off.")
