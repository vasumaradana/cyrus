# Plan 029: Make Hook Brain Host Configurable

## Summary

Add `CYRUS_BRAIN_HOST` and `CYRUS_HOOK_PORT` environment variable support to `cyrus_hook.py` so the hook can connect to a brain running on a different host (e.g. Docker container). Default to `localhost:8767` for backward compatibility. Update `.env.example` to document both variables.

## Dependencies

None blocking. Issue 027 (centralized config module) is PLANNED but not BUILT — `cyrus2/` is empty. This plan reads env vars directly in `cyrus_hook.py` using the same `CYRUS_*` variable names that plan 027 defines, so the future config consolidation will be a clean replacement.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `CYRUS_BRAIN_HOST` env var | `BRAIN_HOST = "localhost"` hardcoded (line 15) | Replace with `os.environ.get` |
| `CYRUS_HOOK_PORT` env var | `BRAIN_PORT = 8767` hardcoded (line 16) | Replace with `os.environ.get` |
| Defaults to `localhost` | Hardcoded `localhost` | Default value in `os.environ.get` |
| Connects to `{host}:{port}` | Already uses `(BRAIN_HOST, BRAIN_PORT)` tuple | No change needed (variables already used) |
| Socket timeout respected | Already `timeout=2` in `socket.create_connection` | No change needed |
| `.env.example` documents vars | Only has `ANTHROPIC_API_KEY=` | Add `CYRUS_BRAIN_HOST` and `CYRUS_HOOK_PORT` |
| Test coverage for env var behavior | No tests exist (issue 022 not built) | Create focused test |

## Key Findings from Codebase Exploration

### Current `cyrus_hook.py` (lines 15–24)

```python
BRAIN_HOST = "localhost"
BRAIN_PORT = 8767

def _send(msg: dict) -> None:
    try:
        with socket.create_connection((BRAIN_HOST, BRAIN_PORT), timeout=2) as s:
            s.sendall((json.dumps(msg) + "\n").encode())
    except Exception:
        pass   # Brain not running — silent, never block Claude
```

The change is surgical: replace the two constant assignments on lines 15–16 with `os.environ.get()` calls. The `_send` function, `main()`, and all event dispatch logic remain untouched.

### Naming alignment with plan 027

Plan 027 defines `CYRUS_HOOK_PORT` (not `CYRUS_BRAIN_PORT`) for port 8767, and `CYRUS_BRAIN_CONNECT_HOST` for the client-side host. However, issue 029's acceptance criteria explicitly name `CYRUS_BRAIN_HOST` — not `CYRUS_BRAIN_CONNECT_HOST`. We follow the issue spec. When 027 consolidates config, it can alias or rename as needed.

### Test infrastructure status

- Issue 018 (test infra): PLANNED, not built — `cyrus2/tests/` doesn't exist
- Issue 022 (test_hook.py): PLANNED, not built — no hook tests exist
- Both plans handle the "create if missing" case, so us creating minimal infrastructure won't conflict

### Docker deployment scenario (from docs/13)

With Docker, brain runs in container with ports mapped to host. The hook (running on host via Claude Code) needs to reach the brain. Options:
- **Default** (`localhost`): works when brain runs on same host or when Docker ports are mapped to host
- **`host.docker.internal`**: works when hook runs inside container and brain runs on host
- **Custom IP/hostname**: any network topology

## Design Decisions

### D1. Read env vars at module level (not per-call)

Same pattern as the current code — constants evaluated once at import time. This matches the existing architecture and what plan 027 will do. No per-call overhead.

### D2. Use `CYRUS_BRAIN_HOST` (not `CYRUS_BRAIN_CONNECT_HOST`)

The acceptance criteria explicitly name `CYRUS_BRAIN_HOST`. Plan 027 uses `CYRUS_BRAIN_CONNECT_HOST` for a different semantic (general client connect host shared across voice/hook). When 027 lands, it will import and map appropriately. We follow the issue spec.

### D3. Keep `BRAIN_HOST` and `BRAIN_PORT` as local variable names

The `_send` function already references `BRAIN_HOST` and `BRAIN_PORT`. Changing only the assignment (from hardcoded to env var) means zero changes to `_send()` or `main()`. Minimal diff, minimal risk.

### D4. Create focused test, not full hook test suite

Issue 022 will create 17 comprehensive hook tests. Our test focuses narrowly on the env var configuration behavior — verifying defaults and overrides. This avoids duplicating 022's scope while still covering 029's acceptance criteria.

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Test |
|---|---|---|
| AC1 | `CYRUS_BRAIN_HOST` env var read | `test_brain_host_default` + `test_brain_host_override` |
| AC2 | Defaults to `localhost` if not set | `test_brain_host_default` |
| AC3 | Connects to `{CYRUS_BRAIN_HOST}:8767` (or CYRUS_HOOK_PORT) | `test_brain_port_default` + `test_brain_port_override` + `test_send_uses_configured_host_port` |
| AC4 | Socket timeout respected during connection | `test_send_uses_configured_host_port` (asserts timeout=2 in mock) |
| AC5 | Documented in .env.example | Manual: grep `.env.example` for both var names |

## Implementation Steps

### Step 1: Create test infrastructure (if missing)

The test directory and conftest may not exist (issues 018/022 not built). Create the minimal structure needed. Both 018 and 022 plans explicitly handle the "already exists" case.

**Create** (if missing):
- `cyrus2/__init__.py` — empty, makes `cyrus2` a Python package
- `cyrus2/tests/__init__.py` — empty
- `cyrus2/tests/conftest.py` — minimal `mock_send` fixture
- `cyrus2/pytest.ini` — with `pythonpath = ..` so `cyrus_hook` imports resolve

```bash
cd /home/daniel/Projects/barf/cyrus

# Create directories
mkdir -p cyrus2/tests

# Create __init__.py files
touch cyrus2/__init__.py
touch cyrus2/tests/__init__.py
```

**File**: `cyrus2/tests/conftest.py`
```python
"""Minimal conftest — mock_send fixture for hook tests."""

import pytest


@pytest.fixture
def mock_send():
    class MockSend:
        def __init__(self):
            self.messages: list[dict] = []
        def __call__(self, msg: dict) -> None:
            self.messages.append(msg)
        def reset(self) -> None:
            self.messages.clear()
    return MockSend()
```

**File**: `cyrus2/pytest.ini`
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
pythonpath = ..
```

**Verify**:
```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
python3 -c "import cyrus_hook; print('import OK')"
```

### Step 2: Write test for env var config behavior (RED)

**File**: `cyrus2/tests/test_hook_config.py`

Tests verify:
1. Default values (`localhost`, `8767`) when env vars not set
2. `CYRUS_BRAIN_HOST` override changes `BRAIN_HOST`
3. `CYRUS_HOOK_PORT` override changes `BRAIN_PORT`
4. `_send()` passes configured host, port, and timeout to `socket.create_connection`

```python
"""Tests for cyrus_hook.py host/port configuration (Issue 029).

Verifies CYRUS_BRAIN_HOST and CYRUS_HOOK_PORT env var support.
"""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch, MagicMock

import pytest


def _reload_hook():
    """Re-import cyrus_hook to pick up env var changes."""
    import cyrus_hook
    return importlib.reload(cyrus_hook)


class TestBrainHostConfig:
    """CYRUS_BRAIN_HOST env var behavior."""

    def test_defaults_to_localhost(self):
        """AC2: BRAIN_HOST defaults to localhost when env var not set."""
        os.environ.pop("CYRUS_BRAIN_HOST", None)
        hook = _reload_hook()
        assert hook.BRAIN_HOST == "localhost"

    def test_reads_env_var(self):
        """AC1: BRAIN_HOST reads from CYRUS_BRAIN_HOST."""
        os.environ["CYRUS_BRAIN_HOST"] = "192.168.1.100"
        try:
            hook = _reload_hook()
            assert hook.BRAIN_HOST == "192.168.1.100"
        finally:
            del os.environ["CYRUS_BRAIN_HOST"]

    def test_docker_host(self):
        """Docker deployment: host.docker.internal works."""
        os.environ["CYRUS_BRAIN_HOST"] = "host.docker.internal"
        try:
            hook = _reload_hook()
            assert hook.BRAIN_HOST == "host.docker.internal"
        finally:
            del os.environ["CYRUS_BRAIN_HOST"]


class TestBrainPortConfig:
    """CYRUS_HOOK_PORT env var behavior."""

    def test_defaults_to_8767(self):
        """AC3: BRAIN_PORT defaults to 8767 when env var not set."""
        os.environ.pop("CYRUS_HOOK_PORT", None)
        hook = _reload_hook()
        assert hook.BRAIN_PORT == 8767

    def test_reads_env_var(self):
        """AC3: BRAIN_PORT reads from CYRUS_HOOK_PORT."""
        os.environ["CYRUS_HOOK_PORT"] = "9999"
        try:
            hook = _reload_hook()
            assert hook.BRAIN_PORT == 9999
        finally:
            del os.environ["CYRUS_HOOK_PORT"]

    def test_port_is_int(self):
        """Port value is converted to int."""
        os.environ["CYRUS_HOOK_PORT"] = "5555"
        try:
            hook = _reload_hook()
            assert isinstance(hook.BRAIN_PORT, int)
            assert hook.BRAIN_PORT == 5555
        finally:
            del os.environ["CYRUS_HOOK_PORT"]


class TestSendUsesConfig:
    """_send() uses the configured host, port, and timeout."""

    def test_send_passes_host_port_timeout(self):
        """AC3+AC4: create_connection called with (host, port) and timeout=2."""
        os.environ.pop("CYRUS_BRAIN_HOST", None)
        os.environ.pop("CYRUS_HOOK_PORT", None)
        hook = _reload_hook()

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch("socket.create_connection", return_value=mock_conn) as mock_create:
            hook._send({"event": "test"})
            mock_create.assert_called_once_with(("localhost", 8767), timeout=2)

    def test_send_uses_overridden_values(self):
        """Overridden host/port flow through to socket.create_connection."""
        os.environ["CYRUS_BRAIN_HOST"] = "10.0.0.5"
        os.environ["CYRUS_HOOK_PORT"] = "4444"
        try:
            hook = _reload_hook()

            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)

            with patch("socket.create_connection", return_value=mock_conn) as mock_create:
                hook._send({"event": "test"})
                mock_create.assert_called_once_with(("10.0.0.5", 4444), timeout=2)
        finally:
            del os.environ["CYRUS_BRAIN_HOST"]
            del os.environ["CYRUS_HOOK_PORT"]
```

**Run** (expected: FAIL — `BRAIN_HOST` is still hardcoded, not read from env):
```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_hook_config.py -v
```

### Step 3: Modify `cyrus_hook.py` (GREEN)

**File**: `cyrus_hook.py` — Replace lines 15–16:

```python
# BEFORE
BRAIN_HOST = "localhost"
BRAIN_PORT = 8767

# AFTER
BRAIN_HOST = os.environ.get("CYRUS_BRAIN_HOST", "localhost")
BRAIN_PORT = int(os.environ.get("CYRUS_HOOK_PORT", "8767"))
```

That's it. Two lines changed. The `_send` function already uses `(BRAIN_HOST, BRAIN_PORT)` and `timeout=2` — no other changes needed.

**Run** (expected: all PASS):
```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_hook_config.py -v
```

### Step 4: Update `.env.example`

**File**: `.env.example` — Add the two new variables with documentation:

```env
ANTHROPIC_API_KEY=

# ── Hook Configuration ──────────────────────────────────────────────────────
# Brain host for hook connections. Set to Docker container hostname/IP
# when brain runs on a different host (e.g. host.docker.internal).
# CYRUS_BRAIN_HOST=localhost

# Port the hook uses to reach the brain's hook listener.
# CYRUS_HOOK_PORT=8767
```

### Step 5: Verify end-to-end

```bash
cd /home/daniel/Projects/barf/cyrus

# 1. Tests pass
cd cyrus2 && pytest tests/test_hook_config.py -v && cd ..

# 2. Default behavior (no env vars) — hook exits cleanly
echo '{}' | python3 cyrus_hook.py

# 3. Custom host — hook exits cleanly (brain not running, silent failure)
CYRUS_BRAIN_HOST=192.168.1.100 echo '{}' | python3 cyrus_hook.py

# 4. Custom port — hook exits cleanly
CYRUS_HOOK_PORT=9999 echo '{}' | python3 cyrus_hook.py

# 5. .env.example has both vars
grep "CYRUS_BRAIN_HOST" .env.example && grep "CYRUS_HOOK_PORT" .env.example
```

### Step 6: Commit

```bash
cd /home/daniel/Projects/barf/cyrus
git add cyrus_hook.py .env.example cyrus2/
git commit -m "feat(hook): make brain host and port configurable via env vars

Add CYRUS_BRAIN_HOST (default: localhost) and CYRUS_HOOK_PORT (default: 8767)
env var support to cyrus_hook.py. Enables Docker deployment where brain runs
in container and hook runs on host.

Issue: 029-Make-hook-brain-host-configurable"
```

## Files Created/Modified

| File | Action | Purpose |
|---|---|---|
| `cyrus_hook.py` | **Modify** (2 lines) | Read `CYRUS_BRAIN_HOST` and `CYRUS_HOOK_PORT` from env vars |
| `.env.example` | **Update** | Document both new env vars |
| `cyrus2/__init__.py` | **Create** (if missing) | Make cyrus2 a Python package |
| `cyrus2/tests/__init__.py` | **Create** (if missing) | Test package init |
| `cyrus2/tests/conftest.py` | **Create** (if missing) | `mock_send` fixture |
| `cyrus2/pytest.ini` | **Create** (if missing) | pytest config with `pythonpath = ..` |
| `cyrus2/tests/test_hook_config.py` | **Create** | 8 tests for env var config behavior |

## Risk Assessment

**Very low risk.** Two-line change in production code. No logic changes to event dispatch.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| `int()` on invalid CYRUS_HOOK_PORT crashes hook | Hook blocks Claude Code | Very low | Invalid port env vars are a user config error; same pattern used by plan 027. Could add try/except but that's over-engineering for an env var. |
| Test infrastructure conflicts with issues 018/022 | Merge conflicts | Low | Both plans explicitly handle "create if missing". Minimal conftest matches 022's expected shape. |
| Module reload in tests leaves stale state | Flaky tests | Low | Each test cleans up env vars in `finally` blocks. `_reload_hook()` forces fresh import. |
