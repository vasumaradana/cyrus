# Plan: 036-Add-health-check-endpoint

## Summary

Add an HTTP `GET /health` endpoint on port 8771 to `cyrus_brain.py` using `aiohttp`, returning JSON status (ok/error, session count, active project, headless flag, uptime). Runs on the existing asyncio event loop as a lightweight `TCPSite` — never blocks or crashes the brain. Add `aiohttp` to requirements. Add pytest tests.

## File Path Correction

The issue references `cyrus2/cyrus_brain.py` but the actual file is at the project root: **`cyrus_brain.py`**. The `cyrus2/` directory is empty. Plans 030, 034, and 035 all made the same correction. All modifications target `cyrus_brain.py`.

## Gap Analysis

| Requirement | Current State | Action |
|-------------|--------------|--------|
| HTTP health endpoint | No HTTP server in codebase | Create using `aiohttp` |
| Port 8771 | Not allocated (8766=voice, 8767=hook, 8769=mobile, 8770=companion) | Add `HEALTH_PORT = 8771` constant |
| aiohttp dependency | Not in any requirements file | Add to `requirements-brain.txt` |
| JSON response with status details | No status endpoint exists | Implement handler returning status JSON |
| Never crashes brain | N/A | `try/except` around server startup; handler catches all exceptions |
| Tests | No pytest infrastructure (plan 018 creates it) | Create tests; reuse conftest.py if 018 is built, else create minimal version |

## Key Design Decisions

### D1: Port 8771 — separate from brain port

The interview confirmed port 8771. Port 8766 is the voice TCP server (raw TCP, not HTTP). Running HTTP on the same port would require replacing `asyncio.start_server` with an HTTP-aware server — a disruptive change. A separate port is cleaner and matches Docker best practices (one concern per port).

### D2: aiohttp — native async integration

The interview confirmed aiohttp over stdlib `http.server`. The brain already runs an asyncio event loop. aiohttp's `AppRunner` + `TCPSite` integrate directly — no extra threads, no blocking. The `TCPSite` starts on the existing loop and serves requests cooperatively.

### D3: Handler receives `session_mgr` via app state

aiohttp's `Application` supports `app["key"]` for dependency injection. Store `session_mgr` and `start_time` on the app object so the handler can access them without globals. This is cleaner than closure-captured state and easier to test.

### D4: Session count — use `SessionManager._chat_watchers`

The `SessionManager._chat_watchers` dict tracks all active sessions (both UIA-detected and headless-registered). `len(session_mgr._chat_watchers)` gives the session count. No need to also check `_registered_sessions` (which only exists after issue 034) — the session manager is the single source of truth.

### D5: Error resilience — catch-all in handler, guarded startup

The handler wraps response construction in `try/except` and returns `{"status": "error"}` with 503 on failure. The server startup in `main()` is wrapped in `try/except` so a port-bind failure (address in use) logs an error but doesn't crash the brain.

### D6: Non-health paths return 404

Any path other than `/health` returns 404 with `{"error": "not found"}`. Keeps the surface area minimal.

### D7: Test strategy — mock app, no live server needed for unit tests

aiohttp provides `aiohttp.test_utils.TestClient` for testing handlers without starting a real TCP server. This avoids port conflicts in CI. An optional integration test starts a real server on port 0 (random).

## Acceptance Criteria → Test Map

| Criterion | Test |
|-----------|------|
| HTTP server on port 8771 | `test_health_server_starts` — verify `TCPSite` created on port 8771 |
| `GET /health` returns 200 with JSON | `test_health_returns_200_ok` — TestClient GET /health, assert 200 + JSON |
| Response includes status, sessions, active_project | `test_health_response_fields` — assert all expected keys present |
| Response includes headless flag | `test_health_response_headless_flag` |
| Non-health path returns 404 | `test_non_health_path_returns_404` |
| Never crashes brain main loop | `test_health_handler_error_returns_503` — mock broken session_mgr, assert 503 |
| Callable from curl / monitoring tools | Manual: `curl http://localhost:8771/health` |
| Startup failure doesn't crash brain | `test_health_server_port_in_use` — bind port first, verify graceful degradation |

## Implementation Steps

### Step 1: Add `aiohttp` dependency

**File:** `requirements-brain.txt`

Add `aiohttp` at the end:
```
aiohttp
```

**Note for builder**: If `requirements-brain-headless.txt` exists (from issue 035), add `aiohttp` there too.

**Verify:** `pip install aiohttp` succeeds.

────

### Step 2: Add `HEALTH_PORT` constant and `_brain_start_time`

**File:** `cyrus_brain.py`, Configuration section (after line 67, after `MOBILE_PORT`)

```python
HEALTH_PORT      = 8771   # HTTP health check endpoint
```

Add to Shared state section (after line 106, after `_voice_lock`):
```python
_brain_start_time: float = time.time()
```

**Verify:** `python -c "import cyrus_brain; print(cyrus_brain.HEALTH_PORT)"` → `8771`

────

### Step 3: Add `aiohttp` import

**File:** `cyrus_brain.py`, imports section (after line 35, after `import websockets`)

```python
from aiohttp import web as _health_web
```

Use `_health_web` alias to avoid collision with any existing `web` name and signal this is internal infrastructure.

────

### Step 4: Implement health handler and server setup

**File:** `cyrus_brain.py` — add a new section before the `# ── Main` section (before line 1694)

```python
# ── Health check endpoint ─────────────────────────────────────────────────────

async def _health_handler(request: _health_web.Request) -> _health_web.Response:
    """GET /health — returns brain status as JSON. Never raises."""
    try:
        session_mgr: SessionManager = request.app["session_mgr"]
        start_time: float = request.app["start_time"]
        with _active_project_lock:
            active = _active_project
        body = {
            "status": "ok",
            "timestamp": time.time(),
            "uptime_seconds": round(time.time() - start_time, 1),
            "sessions": len(session_mgr._chat_watchers),
            "active_project": active,
            "headless": HEADLESS,
        }
        return _health_web.json_response(body)
    except Exception as exc:
        return _health_web.json_response(
            {"status": "error", "error": str(exc)},
            status=503,
        )


async def _handle_404(request: _health_web.Request) -> _health_web.Response:
    """Catch-all for non-health paths."""
    return _health_web.json_response({"error": "not found"}, status=404)


async def _start_health_server(
    host: str,
    session_mgr: SessionManager,
) -> _health_web.AppRunner | None:
    """Start the aiohttp health server. Returns the runner (for cleanup) or None on failure."""
    try:
        app = _health_web.Application()
        app["session_mgr"] = session_mgr
        app["start_time"] = _brain_start_time
        app.router.add_get("/health", _health_handler)
        # Catch-all for anything that isn't /health
        app.router.add_route("*", "/{path_info:.*}", _handle_404)
        runner = _health_web.AppRunner(app, access_log=None)
        await runner.setup()
        site = _health_web.TCPSite(runner, host, HEALTH_PORT)
        await site.start()
        print(f"[Brain] Health endpoint on http://{host}:{HEALTH_PORT}/health")
        return runner
    except OSError as exc:
        print(f"[Brain] WARNING: Health server failed to start: {exc}")
        print(f"[Brain] Brain continues without health endpoint")
        return None
    except Exception as exc:
        print(f"[Brain] WARNING: Health server unexpected error: {exc}")
        return None
```

**Design notes:**
- `access_log=None` suppresses per-request aiohttp logging (matches the issue's `log_message` suppression)
- `_start_health_server` returns the runner for potential cleanup; `None` on failure
- `OSError` catches "address already in use" (most common startup failure)
- The catch-all route handles arbitrary paths with 404
- `_active_project_lock` used consistently with the rest of the codebase

────

### Step 5: Wire health server into `main()`

**File:** `cyrus_brain.py`, function `main()` — after the mobile server setup (after line 1756), before the `async with` block

```python
    # Health check HTTP server (port 8771)
    health_runner = await _start_health_server(args.host, session_mgr)
```

No changes to `asyncio.gather` — the `TCPSite` registers itself on the event loop via `site.start()` and serves requests without needing `serve_forever()`. It runs cooperatively alongside the existing servers.

Add cleanup in main's finally (or after the gather block if refactored):
```python
    # After the gather block (or in a finally):
    if health_runner:
        await health_runner.cleanup()
```

Since the existing code doesn't have a `try/finally` in main (the brain runs until `KeyboardInterrupt`), and the daemon nature means cleanup is optional, the builder may either:
- Add a `try/finally` around the `async with` + `gather` block, or
- Skip explicit cleanup (the OS reclaims resources on process exit)

Both are acceptable. Explicit cleanup is cleaner but not strictly necessary for a daemon process.

**Verify:** Start brain → `curl http://localhost:8771/health` returns JSON with 200.

────

### Step 6: Add pytest infrastructure (if not already present from issue 018)

**Skip this step if `tests/conftest.py` already exists** (created by issue 018).

**New file:** `requirements-dev.txt`
```
pytest
pytest-asyncio
aiohttp
```

**New file:** `tests/__init__.py` (empty)

**New file:** `tests/conftest.py`
```python
import sys
from unittest.mock import MagicMock

# Mock Windows-only modules BEFORE importing cyrus_brain
for _mod in ['comtypes', 'comtypes.gen', 'pyautogui', 'pyperclip',
             'pygetwindow', 'uiautomation']:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
```

**Run:** `pip install pytest pytest-asyncio aiohttp && pytest tests/ --co` — collects 0 tests.

────

### Step 7: Write unit tests for health endpoint

**New file:** `tests/test_health.py`

```python
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import MagicMock
import time

# conftest.py already mocks Windows imports
import cyrus_brain


@pytest.fixture
def mock_session_mgr():
    mgr = MagicMock(spec=cyrus_brain.SessionManager)
    mgr._chat_watchers = {"proj-a": MagicMock(), "proj-b": MagicMock()}
    return mgr


@pytest.fixture
def health_app(mock_session_mgr):
    app = web.Application()
    app["session_mgr"] = mock_session_mgr
    app["start_time"] = time.time() - 60  # 60s ago
    app.router.add_get("/health", cyrus_brain._health_handler)
    app.router.add_route("*", "/{path_info:.*}", cyrus_brain._handle_404)
    return app


@pytest.fixture
async def client(health_app):
    async with TestClient(TestServer(health_app)) as c:
        yield c


@pytest.mark.asyncio
async def test_health_returns_200_ok(client):
    resp = await client.get("/health")
    assert resp.status == 200
    body = await resp.json()
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_health_response_fields(client):
    resp = await client.get("/health")
    body = await resp.json()
    assert "status" in body
    assert "timestamp" in body
    assert "uptime_seconds" in body
    assert "sessions" in body
    assert "active_project" in body
    assert "headless" in body


@pytest.mark.asyncio
async def test_health_session_count(client):
    resp = await client.get("/health")
    body = await resp.json()
    assert body["sessions"] == 2  # proj-a + proj-b from fixture


@pytest.mark.asyncio
async def test_health_uptime_positive(client):
    resp = await client.get("/health")
    body = await resp.json()
    assert body["uptime_seconds"] >= 60


@pytest.mark.asyncio
async def test_health_response_headless_flag(client):
    resp = await client.get("/health")
    body = await resp.json()
    assert isinstance(body["headless"], bool)


@pytest.mark.asyncio
async def test_non_health_path_returns_404(client):
    resp = await client.get("/metrics")
    assert resp.status == 404
    body = await resp.json()
    assert body["error"] == "not found"


@pytest.mark.asyncio
async def test_health_handler_error_returns_503():
    """If session_mgr access throws, handler returns 503 not a crash."""
    app = web.Application()
    app["session_mgr"] = None  # will cause AttributeError
    app["start_time"] = time.time()
    app.router.add_get("/health", cyrus_brain._health_handler)

    async with TestClient(TestServer(app)) as c:
        resp = await c.get("/health")
        assert resp.status == 503
        body = await resp.json()
        assert body["status"] == "error"
```

**Run:** `pytest tests/test_health.py -v` — all 7 tests pass.

────

### Step 8: Write startup/integration test

**New file:** `tests/test_health_server.py`

```python
import pytest
from unittest.mock import MagicMock, patch
import socket

import cyrus_brain


@pytest.mark.asyncio
async def test_health_server_starts():
    """_start_health_server returns a runner and the server is reachable."""
    mgr = MagicMock(spec=cyrus_brain.SessionManager)
    mgr._chat_watchers = {}

    # Use port 0 to get a random available port
    with patch.object(cyrus_brain, 'HEALTH_PORT', 0):
        runner = await cyrus_brain._start_health_server("127.0.0.1", mgr)

    assert runner is not None
    await runner.cleanup()


@pytest.mark.asyncio
async def test_health_server_port_in_use():
    """If port is already bound, _start_health_server returns None (no crash)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    bound_port = sock.getsockname()[1]
    sock.listen(1)

    mgr = MagicMock(spec=cyrus_brain.SessionManager)
    mgr._chat_watchers = {}

    try:
        with patch.object(cyrus_brain, 'HEALTH_PORT', bound_port):
            runner = await cyrus_brain._start_health_server("127.0.0.1", mgr)
        assert runner is None  # graceful failure
    finally:
        sock.close()
```

**Run:** `pytest tests/test_health_server.py -v` — both tests pass.

────

### Step 9: Update Dockerfile health check port (if 035 is built)

**Skip this step if `Dockerfile` does not exist** (issue 035 not yet built).

If `Dockerfile` exists, update the HEALTHCHECK line to target port 8771:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8771/health')"
```

Similarly update `docker-compose.yml` healthcheck and port mapping:
- Add `"8771:8771"` to the `ports` list
- Update the healthcheck test URL to port 8771

And update `Dockerfile` EXPOSE to include 8771:
```dockerfile
EXPOSE 8766 8767 8769 8770 8771
```

────

### Step 10: Final verification

1. `pip install aiohttp` — succeeds
2. `python cyrus_brain.py` — starts normally, prints health endpoint banner
3. `curl http://localhost:8771/health` — returns `{"status": "ok", "sessions": 0, ...}`
4. `curl http://localhost:8771/metrics` — returns 404
5. `curl http://localhost:8771/health` under load — responds in <100ms
6. Kill brain — health endpoint stops (connection refused)
7. `pytest tests/test_health.py tests/test_health_server.py -v` — all tests pass

## Files Modified

| File | Change |
|------|--------|
| `cyrus_brain.py` | Add `aiohttp` import, `HEALTH_PORT` constant, `_brain_start_time`, `_health_handler()`, `_handle_404()`, `_start_health_server()`; wire into `main()` |
| `requirements-brain.txt` | Add `aiohttp` |

## Files Created

| File | Purpose |
|------|---------|
| `tests/test_health.py` | Unit tests: 200 response, field validation, session count, 404, 503 error handling |
| `tests/test_health_server.py` | Server startup test, port-in-use graceful degradation |
| `requirements-dev.txt` | pytest + pytest-asyncio + aiohttp (skip if exists from 018) |
| `tests/__init__.py` | Package marker (skip if exists from 018) |
| `tests/conftest.py` | Windows import mocks (skip if exists from 018) |

## Files Conditionally Modified (if issue 035 is built)

| File | Change |
|------|--------|
| `Dockerfile` | Update HEALTHCHECK to port 8771; add 8771 to EXPOSE |
| `docker-compose.yml` | Update healthcheck URL to port 8771; add port 8771 mapping |
| `requirements-brain-headless.txt` | Add `aiohttp` |

## Dependency Notes

- **Issue 030** (HEADLESS flag): The health endpoint works in both headless and non-headless modes. `HEADLESS` is referenced in the response payload — if 030 isn't built yet, `HEADLESS` won't be defined. The builder should add `HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1"` if it doesn't exist, or use `globals().get("HEADLESS", False)` as a safe fallback.
- **Issue 018** (pytest infra): If built, `tests/conftest.py` and `requirements-dev.txt` already exist — reuse them. If not, Step 6 creates minimal versions.
- **Issue 035** (Dockerfile): If built, update HEALTHCHECK port from 8766 to 8771. If not, note in the issue that 035's plan references port 8766 and will need updating.

## Deltas from Issue Spec

| Issue spec says | Plan changes to | Rationale |
|----------------|----------------|-----------|
| Files in `cyrus2/` | Files at project root | cyrus2/ is empty; all other plans (030, 034, 035) made the same correction |
| Port 8766 "or separate port" | Port 8771 | Interview confirmed 8771; port 8766 is raw TCP (voice), not HTTP |
| `_registered_sessions` in response | `session_mgr._chat_watchers` count | `_registered_sessions` is from issue 034 (may not exist); SessionManager is the single source of truth for session count |
| Option 1: stdlib http.server + threads | aiohttp + async | Interview confirmed aiohttp; native async integration, no extra threads |
| Dockerfile HEALTHCHECK on 8766 | Conditional update to 8771 | Port changed; Dockerfile may not exist yet (035 dependency) |
