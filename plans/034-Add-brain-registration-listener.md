# Plan: 034-Add-brain-registration-listener

## Summary

Add an async TCP server on port 8770 to `cyrus_brain.py` (headless mode only) that accepts companion extension registrations over persistent connections. Maintain a `_registered_sessions` dict tracking active workspaces. Route `register`, `focus`, `blur`, `permission_respond`, and `prompt_respond` messages. Handle client disconnects gracefully. Add pytest infrastructure and comprehensive tests.

## File Path Correction

The issue references `cyrus2/cyrus_brain.py` but the actual file is at the project root: **`cyrus_brain.py`**. All modifications target `cyrus_brain.py`.

## Dependency: Issue 030 (Headless Mode)

Issue 030 (PLANNED, not yet BUILT) adds the `HEADLESS` flag and guards Windows imports. This issue's registration server only starts in headless mode. **Strategy**: add a minimal `HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1"` flag. If 030 has already been built when the builder runs, the flag will already be present — skip this step.

## Key Design Decisions

1. **`SessionInfo` as a dataclass** — `@dataclasses.dataclass` with fields: `workspace`, `safe`, `port`, `writer` (asyncio.StreamWriter), `created_at` (float). Cleaner than a plain dict, matches the class pattern in the issue.

2. **`asyncio.Lock` for `_sessions_lock`** — The registration server runs entirely in the asyncio event loop. All reads/writes to `_registered_sessions` happen from async code (the TCP handler). `threading.Lock` is wrong here — it can't be `await`ed.

3. **`threading.Lock` for `_active_project_lock` stays as-is** — Already exists (line 82). Both the active window tracker thread and the async registration handler access `_active_project`. The existing `threading.Lock` is correct for cross-thread/async access (with `with` not `async with`).

4. **Watcher creation — instantiate, don't `start()`** — In headless mode (issue 030 not yet built), `ChatWatcher.start()` and `PermissionWatcher.start()` launch UIA polling threads that call `pyautogui`, `uiautomation`, etc. These crash on Linux/Docker. Create watcher instances (they hold state for hooks: `is_pending`, `_response_history`, `arm_from_hook`) but skip calling `.start()`. The `_add_session` method calls `.start()` internally, so we add a new `_add_session_headless()` variant that creates watchers without starting polling threads.

5. **`permission_respond` routing — direct state update, not `handle_response()`** — `PermissionWatcher.handle_response()` (line 876) calls `pyautogui.press("1")` / `pyautogui.press("escape")` directly. In headless mode, the companion extension has already handled the UI interaction — the brain just needs to update internal state. The handler sets `pw._pending = False; pw._allow_btn = None` directly and logs the action.

6. **`prompt_respond` routing — direct state update, not `handle_prompt_response()`** — Same reasoning. `handle_prompt_response()` (line 917) calls `pyperclip.copy()`, `pyautogui.hotkey()`. In headless mode, clear `pw._prompt_pending = False; pw._prompt_input_ctrl = None` and log.

7. **Graceful disconnect** — The `finally` block removes the session from `_registered_sessions`, calls `session_mgr.remove_session()` to clean up watchers/aliases, and closes the writer.

8. **Test strategy for Windows-only imports** — `cyrus_brain.py` imports `comtypes`, `pyautogui`, `pygetwindow`, `uiautomation` at module level (lines 35-59). These fail on Linux/macOS. `conftest.py` uses `sys.modules` patching to mock these before import:
   ```python
   import sys
   from unittest.mock import MagicMock
   for mod in ['comtypes', 'comtypes.gen', 'pyautogui', 'pyperclip',
                'pygetwindow', 'uiautomation']:
       if mod not in sys.modules:
           sys.modules[mod] = MagicMock()
   ```

## Acceptance Criteria → Test Map

| Criterion | Test |
|-----------|------|
| Async TCP server on 0.0.0.0:8770 (headless only) | `test_server_starts_in_headless` / `test_server_skipped_without_headless` |
| `_registered_sessions` tracks sessions | `test_register_adds_session` |
| On `register`, add session + create watchers | `test_register_creates_watchers` |
| On `focus`, set `_active_project` | `test_focus_sets_active_project` |
| On `blur`, clear `_active_project` if matches | `test_blur_clears_active_project` / `test_blur_ignores_mismatch` |
| On `permission_respond`, forward to watcher | `test_permission_respond_clears_pending` |
| On `prompt_respond`, forward to waiting code | `test_prompt_respond_clears_prompt_pending` |
| On disconnect, remove session | `test_disconnect_removes_session` |
| Multiple concurrent sessions | `test_multiple_concurrent_sessions` |
| Logs registration, focus, disconnects | Verified via `capsys` in relevant tests |

## Implementation Steps

### Step 1: Add test infrastructure

**New file:** `requirements-dev.txt`
```
pytest
pytest-asyncio
```

**New file:** `tests/__init__.py` (empty)

**New file:** `tests/conftest.py`
Shared fixtures: mock Windows imports, mock asyncio reader/writer, patched globals.

```python
import sys
from unittest.mock import MagicMock

# Mock Windows-only modules BEFORE importing cyrus_brain
for _mod in ['comtypes', 'comtypes.gen', 'pyautogui', 'pyperclip',
             'pygetwindow', 'uiautomation']:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
import asyncio
import json


class MockWriter:
    """Mock asyncio.StreamWriter for testing TCP handlers."""
    def __init__(self):
        self.closed = False
        self._extra = {"peername": ("127.0.0.1", 9999)}
        self.written: list[bytes] = []

    def get_extra_info(self, key, default=None):
        return self._extra.get(key, default)

    def write(self, data: bytes):
        self.written.append(data)

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


@pytest.fixture
def mock_writer():
    return MockWriter()


@pytest.fixture
def make_reader():
    """Create a StreamReader pre-loaded with line-delimited JSON messages."""
    def _make(messages: list[dict]) -> asyncio.StreamReader:
        reader = asyncio.StreamReader()
        for msg in messages:
            reader.feed_data(json.dumps(msg).encode() + b"\n")
        reader.feed_eof()
        return reader
    return _make
```

**Run:** `pip install pytest pytest-asyncio && pytest tests/ --co` — collects 0 tests (no test files yet).

### Step 2: Add `HEADLESS` flag, `COMPANION_PORT`, `SessionInfo`, and registration state

**File:** `cyrus_brain.py`

Add `import dataclasses` to the stdlib import block (after line 31, before `import socket`):
```python
import dataclasses
```

Add `HEADLESS` and `COMPANION_PORT` to the Configuration section (after line 67, after `MOBILE_PORT`):
```python
COMPANION_PORT   = 8770   # Registration listener for companion extensions
HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1"
```

Add `SessionInfo` and registration state after the Shared state section (after line 109, after `pyautogui.FAILSAFE = False`):
```python
# ── Registration state (companion extension sessions) ─────────────────────────

@dataclasses.dataclass
class SessionInfo:
    """Tracks one companion extension registration."""
    workspace: str
    safe: str
    port: int
    writer: asyncio.StreamWriter
    created_at: float = dataclasses.field(default_factory=time.time)

_registered_sessions: dict[str, SessionInfo] = {}
_sessions_lock = asyncio.Lock()
```

**Test file:** `tests/test_session_info.py`
```python
import pytest
from cyrus_brain import SessionInfo

def test_session_info_fields(mock_writer):
    info = SessionInfo(workspace="test-proj", safe="test_proj", port=8768, writer=mock_writer)
    assert info.workspace == "test-proj"
    assert info.safe == "test_proj"
    assert info.port == 8768
    assert info.writer is mock_writer
    assert isinstance(info.created_at, float)
```

**Run:** `pytest tests/test_session_info.py -v` — 1 test passes.

### Step 3: Add `_add_session_headless()` and `remove_session()` to SessionManager

**File:** `cyrus_brain.py`, class `SessionManager` (after `start()` method, around line 1103)

```python
    def _add_session_headless(self, proj: str, subname: str,
                              loop: asyncio.AbstractEventLoop) -> None:
        """Add session for headless mode — create watchers without starting UIA polling."""
        global _whisper_prompt
        alias = _make_alias(proj)
        self._aliases[alias] = proj
        print(f"[Brain] Session registered (headless): {proj}")
        names = " ".join(p for p in self._chat_watchers) + f" {proj}"
        _whisper_prompt = f"Cyrus, switch to {names.strip()}."
        _send_threadsafe({"type": "whisper_prompt", "text": _whisper_prompt}, loop)

        cw = ChatWatcher(project_name=proj, target_subname=subname)
        # Don't call cw.start() — no UIA polling in headless mode
        self._chat_watchers[proj] = cw

        pw = PermissionWatcher(project_name=proj, target_subname=subname)
        # Don't call pw.start() — no UIA polling in headless mode
        self._perm_watchers[proj] = pw

    def remove_session(self, proj: str) -> None:
        """Remove watchers and alias for a disconnected session."""
        self._chat_watchers.pop(proj, None)
        self._perm_watchers.pop(proj, None)
        alias_to_remove = None
        for alias, p in self._aliases.items():
            if p == proj:
                alias_to_remove = alias
                break
        if alias_to_remove:
            del self._aliases[alias_to_remove]
```

**Test file:** `tests/test_session_manager.py`
```python
import pytest
from unittest.mock import patch, MagicMock
import cyrus_brain

def test_remove_session_cleans_up():
    mgr = cyrus_brain.SessionManager()
    # Manually add entries
    mgr._chat_watchers["proj1"] = MagicMock()
    mgr._perm_watchers["proj1"] = MagicMock()
    mgr._aliases["proj one"] = "proj1"

    mgr.remove_session("proj1")

    assert "proj1" not in mgr._chat_watchers
    assert "proj1" not in mgr._perm_watchers
    assert "proj one" not in mgr._aliases

def test_remove_session_noop_for_unknown():
    mgr = cyrus_brain.SessionManager()
    mgr.remove_session("nonexistent")  # should not raise
```

**Run:** `pytest tests/test_session_manager.py -v` — 2 tests pass.

### Step 4: Implement `_handle_registration_client`

**File:** `cyrus_brain.py` — add after the registration state block (before the Helpers section)

```python
async def _handle_registration_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    session_mgr: SessionManager,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Handle one companion extension connection on port 8770.

    Protocol: line-delimited JSON over persistent TCP connection.
    Inbound message types: register, focus, blur, permission_respond, prompt_respond.
    """
    global _active_project
    peer = writer.get_extra_info("peername")
    addr = f"{peer[0]}:{peer[1]}" if peer else "unknown"
    print(f"[REG] New connection from {addr}")

    session_workspace: str | None = None
    try:
        while True:
            data = await reader.readline()
            if not data:
                break
            try:
                msg = json.loads(data.decode().strip())
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "register":
                workspace = msg.get("workspace", "unknown")
                safe = msg.get("safe", "unknown")
                port = msg.get("port", 8768)
                async with _sessions_lock:
                    _registered_sessions[workspace] = SessionInfo(
                        workspace=workspace, safe=safe, port=port, writer=writer,
                    )
                session_workspace = workspace
                # Create watchers (headless — no UIA polling)
                if workspace not in session_mgr._chat_watchers:
                    subname = f"{workspace} - Visual Studio Code"
                    session_mgr._add_session_headless(workspace, subname, loop)
                print(f"[REG] {workspace} registered (port {port})")

            elif msg_type == "focus":
                workspace = msg.get("workspace")
                if workspace:
                    with _active_project_lock:
                        _active_project = workspace
                    session_mgr.on_session_switch(workspace, loop)
                    print(f"[REG] Active project: {workspace}")

            elif msg_type == "blur":
                workspace = msg.get("workspace")
                with _active_project_lock:
                    if workspace and _active_project == workspace:
                        _active_project = ""
                        print(f"[REG] Blur: {workspace}")

            elif msg_type == "permission_respond":
                action = msg.get("action", "")
                if session_workspace:
                    pw = session_mgr._perm_watchers.get(session_workspace)
                    if pw and pw.is_pending:
                        # Direct state update — extension already handled the UI
                        pw._pending = False
                        pw._allow_btn = None
                        pw._announced = ""
                    print(f"[REG] Permission respond: {action}")

            elif msg_type == "prompt_respond":
                text = msg.get("text", "")
                if session_workspace:
                    pw = session_mgr._perm_watchers.get(session_workspace)
                    if pw and pw.prompt_pending:
                        # Direct state update — extension already handled the UI
                        pw._prompt_pending = False
                        pw._prompt_input_ctrl = None
                        pw._prompt_announced = ""
                    print(f"[REG] Prompt respond: {text[:50]}")

    except Exception as e:
        print(f"[REG] Error handling {addr}: {e}")
    finally:
        if session_workspace:
            async with _sessions_lock:
                _registered_sessions.pop(session_workspace, None)
            session_mgr.remove_session(session_workspace)
            print(f"[REG] {session_workspace} disconnected")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
```

**Key behaviors:**
- Reads line-delimited JSON in a loop (persistent connection)
- Creates watchers on `register` via `_add_session_headless()` — no UIA polling
- Uses existing `_active_project_lock` (threading.Lock) for `_active_project` mutation
- Calls `session_mgr.on_session_switch()` on focus (same pattern as `_start_active_tracker`)
- Direct state updates for `permission_respond`/`prompt_respond` — no UIA calls
- Cleans up on disconnect: removes from `_registered_sessions`, removes watchers, closes writer

**Test file:** `tests/test_registration_handler.py`

Tests using mock reader/writer — one test per message type:
- `test_register_adds_session` — verify `_registered_sessions` populated
- `test_register_creates_watchers` — verify `SessionManager._chat_watchers` / `_perm_watchers` populated
- `test_focus_sets_active_project` — verify `_active_project` updated
- `test_blur_clears_active_project` — verify `_active_project` cleared when matching
- `test_blur_ignores_mismatch` — verify `_active_project` unchanged when workspace doesn't match
- `test_permission_respond_clears_pending` — set `pw._pending = True`, send `permission_respond`, verify cleared
- `test_prompt_respond_clears_prompt_pending` — set `pw._prompt_pending = True`, send `prompt_respond`, verify cleared
- `test_disconnect_removes_session` — verify session removed from `_registered_sessions` and watchers cleaned up
- `test_multiple_concurrent_sessions` — register two sessions, verify both tracked
- `test_malformed_json_skipped` — feed garbage data, verify handler continues processing
- `test_unknown_message_type_ignored` — send `{"type": "bogus"}`, verify no crash

Each test:
1. Creates a `SessionManager` instance
2. Patches `_send_threadsafe` to no-op (avoids voice connection)
3. Builds a reader with the message sequence and a MockWriter
4. Calls `_handle_registration_client(reader, writer, session_mgr, loop)`
5. Asserts expected state changes

**Run:** `pytest tests/test_registration_handler.py -v` — all tests pass.

### Step 5: Implement `_run_registration_server` and wire into `main()`

**File:** `cyrus_brain.py` — add after `_handle_registration_client`

```python
async def _run_registration_server(
    host: str,
    session_mgr: SessionManager,
    loop: asyncio.AbstractEventLoop,
) -> asyncio.Server:
    """Start the companion extension registration listener (port 8770, headless only)."""
    server = await asyncio.start_server(
        lambda r, w: _handle_registration_client(r, w, session_mgr, loop),
        host, COMPANION_PORT,
    )
    addr = server.sockets[0].getsockname()
    print(f"[REG] Listener on {addr[0]}:{addr[1]}")
    return server
```

**Wire into `main()`** — after the hook server setup (after line 1748), before the mobile server:

```python
    # Registration TCP server (port 8770) — headless mode only
    reg_server = None
    if HEADLESS:
        reg_server = await _run_registration_server(args.host, session_mgr, loop)
```

**Update the `asyncio.gather` block** (lines 1759-1764) to conditionally include the registration server:

```python
    servers_to_run = [
        voice_server.serve_forever(),
        hook_server.serve_forever(),
        mobile_server.wait_closed(),
    ]
    if reg_server:
        servers_to_run.append(reg_server.serve_forever())

    async with voice_server, hook_server:
        await asyncio.gather(*servers_to_run)
```

Note: `reg_server` doesn't need `async with` — it's cleaned up by the event loop. Only voice and hook servers use context managers per the existing pattern.

**Tests in:** `tests/test_registration_server.py`

- `test_server_starts_in_headless` — patch `HEADLESS=True`, patch `asyncio.start_server`, call `_run_registration_server`, verify `start_server` called with `("0.0.0.0", 8770)`
- `test_server_skipped_without_headless` — verify the `if HEADLESS:` guard by checking `_run_registration_server` is not called when `HEADLESS=False` (test the main() logic via assertion on the guard)

**Run:** `pytest tests/test_registration_server.py -v` — tests pass.

### Step 6: Integration test — full TCP lifecycle

**New file:** `tests/test_registration_integration.py`

End-to-end test that starts the actual TCP server on a random port (port 0), connects a real asyncio TCP client, sends the full message sequence, and verifies state changes.

```python
@pytest.mark.asyncio
async def test_full_registration_lifecycle():
    """Register → focus → blur → disconnect — verify all state transitions."""
    # 1. Start real TCP server on random port
    # 2. Connect asyncio TCP client
    # 3. Send register message, verify _registered_sessions populated
    # 4. Send focus, verify _active_project set
    # 5. Send blur, verify _active_project cleared
    # 6. Disconnect, verify session removed + watchers cleaned up
```

**Run:** `pytest tests/test_registration_integration.py -v` — passes.

### Step 7: Final verification

1. `pytest tests/ -v` — all tests pass
2. `python -c "import cyrus_brain"` — no import errors on Windows (non-headless); on Linux, will fail on Windows imports (expected — that's 030's scope)
3. Review all `[REG]` log messages match the issue's expected output format
4. Verify `HEADLESS=False` (default) means registration server is never started

## Files Modified

| File | Change |
|------|--------|
| `cyrus_brain.py` | Add `import dataclasses`; add `HEADLESS`, `COMPANION_PORT` constants; add `SessionInfo` dataclass, `_registered_sessions`, `_sessions_lock`; add `_handle_registration_client()`, `_run_registration_server()`; add `SessionManager._add_session_headless()`, `SessionManager.remove_session()`; wire registration server into `main()` |

## Files Created

| File | Purpose |
|------|---------|
| `requirements-dev.txt` | pytest + pytest-asyncio |
| `tests/__init__.py` | Package marker |
| `tests/conftest.py` | Windows import mocks, MockWriter, reader/writer fixtures |
| `tests/test_session_info.py` | SessionInfo dataclass field tests |
| `tests/test_session_manager.py` | remove_session / _add_session_headless tests |
| `tests/test_registration_handler.py` | Unit tests for each message type handler |
| `tests/test_registration_server.py` | Server start/skip tests |
| `tests/test_registration_integration.py` | End-to-end TCP lifecycle test |

## Risk Notes

1. **Issue 030 not built yet** — `HEADLESS` flag doesn't exist; Step 2 adds it. If 030 is built first, the flag is already present — skip the addition. The `_add_session_headless` variant avoids calling watcher `.start()` which would crash without 030's import guards.

2. **Windows module imports at top level** — `comtypes`, `pyautogui`, `pygetwindow`, `uiautomation` are imported unconditionally (lines 35-59). On Linux/macOS, `import cyrus_brain` fails unless these are mocked. The test `conftest.py` handles this. In production, 030 will guard these imports behind `if not HEADLESS`.

3. **`handle_response()` / `handle_prompt_response()` use UIA** — The registration handler does NOT call these methods. It directly updates watcher state (`_pending`, `_prompt_pending`) because in headless mode the companion extension has already handled the user interaction. This avoids `pyautogui` crashes on Linux.

4. **`_send_threadsafe` in `_add_session_headless`** — This sends a `whisper_prompt` to the voice service. In headless mode without voice connected, `_voice_writer` is None and the send is a no-op (the existing `_send` function already handles None writer gracefully). Tests patch this out.

5. **No CI** — The cyrus project has no CI pipeline. Tests are run manually. The plan adds pytest as a dev dependency only.
