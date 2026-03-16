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

import argparse
import asyncio
import json
import os
import queue as _stdlib_queue
import re
import socket
import threading
import time

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
        print("[Brain] Cleared corrupted comtypes cache, retrying...")
        importlib.invalidate_caches()
        import uiautomation as auto
    except Exception as _e2:
        print(
            f"[Brain] FATAL: UIAutomation still unavailable after cache clear ({_e2})."
        )
        print("[Brain] Try: pip install --force-reinstall comtypes uiautomation")
        raise
from cyrus_common import (
    _CHAT_INPUT_HINT,
    VOICE_HINT,
    VSCODE_TITLE,
    WAKE_WORDS,
    ChatWatcher,
    PermissionWatcher,
    SessionManager,
    _chat_input_coords,
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

# ── Configuration ──────────────────────────────────────────────────────────────

BRAIN_HOST = "0.0.0.0"
BRAIN_PORT = 8766
HOOK_PORT = 8767  # Claude Code Stop hook sends here
MOBILE_PORT = 8769  # WebSocket endpoint for mobile clients

# ── Shared state ───────────────────────────────────────────────────────────────

_active_project: str = ""
_active_project_lock: threading.Lock = threading.Lock()
_vscode_win_cache: dict = {}

_project_locked: bool = False
_project_locked_lock: threading.Lock = threading.Lock()

_conversation_active: bool = False
_whisper_prompt: str = "Cyrus,"
_tts_active_remote: bool = False  # True while voice service is playing TTS

# asyncio queues — set in main()
_speak_queue: asyncio.Queue = None  # (project, text) → sent to voice
_utterance_queue: asyncio.Queue = None  # utterances received from voice

# Mobile WebSocket clients
_mobile_clients: set = set()  # active websocket connections

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
    # Broadcast to mobile WebSocket clients
    if _mobile_clients and msg.get("type") in (
        "speak",
        "prompt",
        "thinking",
        "tool",
        "status",
    ):
        mobile_msg = dict(msg)
        if "full_text" in mobile_msg:
            mobile_msg["text"] = mobile_msg.pop("full_text")
        payload = json.dumps(mobile_msg)
        dead = set()
        for ws in _mobile_clients.copy():
            try:
                await ws.send(payload)
            except Exception:
                dead.add(ws)
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


def _execute_cyrus_command(
    ctype: str, cmd: dict, spoken: str, session_mgr, loop: asyncio.AbstractEventLoop
) -> None:
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
            asyncio.run_coroutine_threadsafe(_speak_queue.put((proj_name, resp)), loop)
            return
        else:
            spoken = (
                spoken or f"No recorded response for {proj_name or 'this session'}."
            )
            print(f"[Brain] {spoken}")

    elif ctype == "rename_session":
        new_name = cmd.get("new", "").strip()
        old_hint = cmd.get("old", "").strip()
        with _active_project_lock:
            active = _active_project
        proj = _resolve_project(old_hint, session_mgr.aliases) if old_hint else active
        if proj and new_name:
            old_alias = next(
                (a for a, p in session_mgr.aliases.items() if p == proj), proj
            )
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
                    print(f"[Brain] Active project: {proj}")
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
        port = int(open(port_file).read().strip())
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
    """Runs on the dedicated submit thread.

    Uses pixel coords — no COM cross-thread issues.
    """
    global _vscode_win_cache

    # ── 0. Try companion extension (no pixel coords, cross-platform) ──────────
    if _submit_via_extension(text):
        return True
    print("[Brain] Companion extension unavailable — falling back to UIA")

    with _active_project_lock:
        proj = _active_project

    # ── 1. Resolve coords BEFORE activating window ─────────────────────────────
    deadline = time.time() + 6.0
    while proj not in _chat_input_coords and time.time() < deadline:
        time.sleep(0.3)
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
    time.sleep(0.15)
    # Re-assert focus before Enter — another window can steal focus
    try:
        win.activate()
    except Exception:
        pass
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


async def voice_reader(
    reader: asyncio.StreamReader,
    session_mgr: SessionManager,
    loop: asyncio.AbstractEventLoop,
) -> None:
    global _conversation_active, _tts_active_remote

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
            print(f"[Brain] Voice reader error: {e}")
            break


# ── Mobile WebSocket handler ──────────────────────────────────────────────────


async def handle_mobile_ws(ws) -> None:
    """Handle a single mobile WebSocket client."""
    _mobile_clients.add(ws)
    addr = ws.remote_address
    print(f"[Brain] Mobile client connected: {addr}")
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
        print(f"[Brain] Mobile client error: {type(e).__name__}: {e}")
    finally:
        _mobile_clients.discard(ws)
        print(
            f"[Brain] Mobile client disconnected: {addr} "
            f"(close_code={ws.close_code}, close_reason={ws.close_reason})"
        )


# ── Utterance routing loop ─────────────────────────────────────────────────────


async def routing_loop(
    session_mgr: SessionManager, loop: asyncio.AbstractEventLoop
) -> None:
    global _conversation_active, _active_project

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
                        parts = follow_text.split(None, 1)
                        follow_text = (
                            parts[1].lstrip(", ").strip() if len(parts) > 1 else ""
                        )
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
                resp = (
                    session_mgr.last_response(proj)
                    or "I don't have a recent response to share."
                )
                resp_words = resp.split()
                if len(resp_words) > 30:
                    resp = " ".join(resp_words[:30]) + ". See the chat for more."
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
                    "\n[Brain answers] "
                    f"{spoken[:80]}{'...' if len(spoken) > 80 else ''}"
                )
                await _speak_queue.put(("", spoken))
            _conversation_active = False

        elif action == "command":
            ctype = decision.get("command", {}).get("type", "")
            spoken = decision.get("spoken", "")
            print(f"\n[Brain command] {ctype}")
            _execute_cyrus_command(
                ctype, decision.get("command", {}), spoken, session_mgr, loop
            )
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
                await _send({"type": "prompt", "text": raw_msg, "project": proj or ""})
                await _send({"type": "thinking"})
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
        print(f"[Hook] event={event}, cwd={cwd!r}, resolved_proj={proj!r}")
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
            print(f"\nCyrus [{proj or 'Claude'}] (hook): {preview}")
            await _speak_queue.put((proj, spoken, text))

        elif event == "pre_tool":
            tool = msg.get("tool", "")
            cmd = msg.get("command", "")
            print(f"[pre_tool] Received: tool={tool}, proj={proj!r}, cmd={cmd[:60]}")
            await _send({"type": "tool", "tool": tool, "command": cmd, "project": proj})
            pw = session_mgr._perm_watchers.get(proj) or next(
                iter(session_mgr._perm_watchers.values()), None
            )
            if pw:
                pw.arm_from_hook(tool, cmd, loop)
            else:
                print(
                    f"[pre_tool] No PermissionWatcher found for proj={proj!r}, "
                    f"known={list(session_mgr._perm_watchers.keys())}"
                )

        elif event == "post_tool":
            tool = msg.get("tool", "")
            prefix = f"In {proj}: " if proj else ""
            if tool == "Bash":
                exit_code = msg.get("exit_code", 0)
                if exit_code != 0:
                    spoken = f"{prefix}Command failed with exit code {exit_code}."
                    print(f"\n[PostTool] {spoken}")
                    await _speak_urgent(spoken)
            elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                file_path = msg.get("file_path", "")
                basename = os.path.basename(file_path) if file_path else "a file"
                verb = "wrote" if tool == "Write" else "edited"
                spoken = f"{prefix}Claude {verb} {basename}."
                print(f"\n[PostTool] {spoken}")
                await _speak_queue.put(("", spoken))

        elif event == "notification":
            message = (msg.get("message") or "").strip()
            if message:
                prefix = f"In {proj}: " if proj else ""
                spoken = f"{prefix}{message}"
                print(f"\n[Notification] {spoken}")
                await _speak_urgent(spoken)

        elif event == "pre_compact":
            trigger = msg.get("trigger", "auto")
            reason = "manual compact" if trigger == "manual" else "context window full"
            spoken = f"Memory compacting: {reason}."
            print(f"\n[PreCompact] {spoken} (proj={proj!r})")
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
        print(f"[Brain] Hook handler error: {e}")
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
        names = ", ".join(_make_alias(p) for p, _ in windows)
        greeting = f"Cyrus is online. {len(windows)} sessions: {names}."

    await _send({"type": "speak", "text": greeting, "project": ""})
    await _send({"type": "listen_chime"})
    print("[Brain] Listening for wake word...")

    try:
        await voice_reader(reader, session_mgr, loop)
    finally:
        _voice_writer = None
        print("[Brain] Voice service disconnected.")
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

    _speak_queue = asyncio.Queue()
    _utterance_queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    # Register brain's chime handlers (websocket IPC to voice service)
    register_chime_handlers(
        chime_fn=lambda: _send_threadsafe({"type": "chime"}, loop),
        listen_chime_fn=lambda: _send_threadsafe({"type": "listen_chime"}, loop),
    )

    # Session manager starts immediately — scans VS Code windows
    session_mgr = _make_session_manager(loop)
    session_mgr.start()

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
        args.host,
        args.port,
    )
    addr = voice_server.sockets[0].getsockname()
    print(f"[Brain] Listening for voice service on {addr[0]}:{addr[1]}")

    # Hook TCP server (port 8767) — Claude Code Stop hook connects here
    hook_server = await asyncio.start_server(
        lambda r, w: handle_hook_connection(r, w, session_mgr),
        args.host,
        HOOK_PORT,
    )
    hook_addr = hook_server.sockets[0].getsockname()
    print(f"[Brain] Listening for Claude hooks on {hook_addr[0]}:{hook_addr[1]}")
    # Mobile WebSocket server (port 8768)
    mobile_server = await websockets.serve(
        handle_mobile_ws,
        args.host,
        MOBILE_PORT,
        ping_interval=None,
        ping_timeout=None,
    )
    print(
        f"[Brain] Listening for mobile clients on {args.host}:{MOBILE_PORT} (WebSocket)"
    )
    print("[Brain] Waiting for voice to connect...")

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
        print("\nCyrus Brain signing off.")
