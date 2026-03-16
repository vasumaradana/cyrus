# Plan 018: Setup pytest framework with conftest

## Summary

Create `cyrus2/tests/` directory with `conftest.py` containing four shared fixtures (`tmp_project_dir`, `mock_logger`, `mock_config`, `mock_send`) and a `pytest.ini` for asyncio configuration. Ensure `requirements-dev.txt` has the correct test dependencies. This is the foundation for all test tiers defined in `docs/14-test-suite.md`.

## Dependencies

**Requires Issue 003** (state: PLANNED). Issue 003 creates `cyrus2/requirements-dev.txt` with `pytest`, `pytest-asyncio`, `pytest-mock`, `ruff`, `pytest-cov`. If Issue 003 is complete, we verify and update the file. If not, we create it ourselves.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/tests/` directory | Does not exist (`cyrus2/` is empty) | Create directory |
| `cyrus2/tests/__init__.py` | Does not exist | Create empty file |
| `cyrus2/tests/conftest.py` | Does not exist | Create with 4 fixtures |
| `requirements-dev.txt` has pytest deps | File does not exist anywhere | Create or update `cyrus2/requirements-dev.txt` |
| `pytest tests/ -v` runs clean | No pytest config, no test dir | Fixtures + pytest.ini + directory structure |
| Fixture documentation | N/A | Docstrings on every fixture |

## Key Findings from Codebase Exploration

### Config pattern (module-level constants, not a dict/dataclass)
```python
# cyrus_brain.py lines 62-76
BRAIN_HOST       = "0.0.0.0"
BRAIN_PORT       = 8766
HOOK_PORT        = 8767
MAX_SPEECH_WORDS = 50
WAKE_WORDS       = {"cyrus", "sire", ...}
```
No config class exists yet — Issue 005 will extract shared code into `cyrus_common.py`. The `mock_config` fixture should provide a dict with these same keys in snake_case, using test-safe values.

### Logger pattern (print statements, no logging module)
```python
# cyrus_brain.py throughout
print(f"[Brain] {spoken}")
print(f"[Brain] Extension error: {result.get('error')}")
```
Issue 009 will create a proper `cyrus_log` module. The `mock_logger` fixture should provide a standard `logging.Logger`-like interface (`.info()`, `.warning()`, `.error()`, `.debug()`) that records messages for assertion, so tests are forward-compatible with Issue 009.

### IPC send pattern (TCP socket, JSON lines)
```python
# cyrus_hook.py lines 19-24
def _send(msg: dict) -> None:
    try:
        with socket.create_connection((BRAIN_HOST, BRAIN_PORT), timeout=2) as s:
            s.sendall((json.dumps(msg) + "\n").encode())
    except Exception:
        pass
```
The `mock_send` fixture should be a callable that records dispatched dicts — no socket needed.

## Design Decisions

1. **Do NOT shadow built-in `tmp_path`** — pytest already provides `tmp_path`. The issue mentions it, but redefining it would break pytest internals. Instead, create `tmp_project_dir` that *uses* `tmp_path` to build a realistic project directory structure (matching how Cyrus expects project layouts). Document that `tmp_path` is already available as a built-in.

2. **`mock_logger` uses standard logging interface** — Even though the codebase currently uses `print()`, Issue 009 will introduce a proper logger. Building fixtures against the future interface means tests won't need rewriting. The fixture records `(level, message)` tuples in a `.messages` list for easy assertion.

3. **`mock_config` returns a plain dict** — No dataclass or TypedDict yet (that's post-Issue 005). A dict with test-safe defaults (port 0 for OS-assigned, localhost only, short timeouts) is the right abstraction level. Tests can override individual keys via `dict.update()` or spread.

4. **`mock_send` is a callable class** — Matches the `_send(msg: dict) -> None` signature from `cyrus_hook.py`. Records to `.messages` list. Has `.reset()` for multi-phase tests.

5. **Create `cyrus2/pytest.ini`** — Configures `asyncio_mode = auto` and `testpaths = tests`. Using `pytest.ini` rather than `pyproject.toml` because Issue 001 may or may not have created `pyproject.toml` yet, and adding a section to a file that may not exist is fragile. `pytest.ini` is self-contained and can be merged into `pyproject.toml` later.

6. **Version pins in requirements-dev.txt** — The issue explicitly specifies `pytest>=7.0`, `pytest-asyncio>=0.21.0`, `pytest-mock>=3.10.0`. We follow the issue spec even though Issue 004 will handle broader pinning later. These are minimum-version floors, not exact pins.

## Acceptance Criteria → Verification Mapping

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC1 | `cyrus2/tests/` directory created | `test -d cyrus2/tests/` |
| AC2 | `conftest.py` exists with shared fixtures (tmp_path, mock_logger, mock_config) | `pytest cyrus2/tests/ --fixtures -q` shows all 4 fixtures |
| AC3 | `requirements-dev.txt` includes pytest>=7.0, pytest-asyncio, pytest-mock | Read file, assert all 3 packages present with version constraints |
| AC4 | `pytest tests/ -v` runs without import errors | Run from `cyrus2/`, exit code 0 (no tests collected = pass) |
| AC5 | conftest.py documents fixture purpose and usage | Every fixture has a docstring with purpose, return type, and usage example |

## Implementation Steps

### Step 1: Create directory structure

```bash
mkdir -p /home/daniel/Projects/barf/cyrus/cyrus2/tests
touch /home/daniel/Projects/barf/cyrus/cyrus2/tests/__init__.py
```

Creates:
- `cyrus2/tests/` — test directory
- `cyrus2/tests/__init__.py` — empty, for package discovery (per issue spec)

### Step 2: Create or update `cyrus2/requirements-dev.txt`

If the file already exists (from Issue 003), verify it contains our deps and add version floors. If it doesn't exist, create it.

**Target content** (alphabetical, with version floors from issue spec):
```
pytest>=7.0
pytest-asyncio>=0.21.0
pytest-cov
pytest-mock>=3.10.0
ruff
```

Note: `pytest-cov` and `ruff` included per Issue 003 scope. No version floor on those (Issue 004 will handle).

### Step 3: Create `cyrus2/pytest.ini`

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

Minimal config. `asyncio_mode = auto` means `@pytest.mark.asyncio` is not required on async test functions — pytest-asyncio detects them automatically. `testpaths` scopes discovery to `tests/` only.

### Step 4: Create `cyrus2/tests/conftest.py`

Write the file with four fixtures, each with full docstrings:

```python
"""Shared test fixtures for the Cyrus test suite.

Fixtures defined here are automatically available to all test files
in the tests/ directory without explicit imports.

Available fixtures:
    tmp_project_dir — Temporary directory pre-populated with a project layout
    mock_logger     — Logger that records messages for assertion
    mock_config     — Configuration dict with test-safe defaults
    mock_send       — Callable that records IPC messages
"""

from __future__ import annotations

import pytest


@pytest.fixture
def tmp_project_dir(tmp_path):
    """Temporary directory pre-populated with a realistic project layout.

    Built on pytest's built-in ``tmp_path`` fixture. Creates a directory
    structure matching Cyrus's expected project conventions.

    Returns:
        pathlib.Path: Root of the temporary project directory.

    Usage::

        def test_something(tmp_project_dir):
            config_file = tmp_project_dir / ".env"
            config_file.write_text("ANTHROPIC_API_KEY=test-key")
            assert config_file.exists()
    """
    (tmp_path / ".env").write_text("")
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture
def mock_logger():
    """Logger that records all messages for test assertions.

    Provides a standard logging interface (info, warning, error, debug)
    that stores each call as a ``(level, message)`` tuple in ``.messages``.
    Forward-compatible with the cyrus_log module (Issue 009).

    Returns:
        MockLogger: Logger instance with ``.messages`` list.

    Usage::

        def test_logs_warning(mock_logger):
            mock_logger.warning("disk full")
            assert ("WARNING", "disk full") in mock_logger.messages
    """

    class MockLogger:
        def __init__(self):
            self.messages: list[tuple[str, str]] = []

        def _log(self, level: str, msg: str, *args: object) -> None:
            self.messages.append((level, msg % args if args else msg))

        def debug(self, msg: str, *args: object) -> None:
            self._log("DEBUG", msg, *args)

        def info(self, msg: str, *args: object) -> None:
            self._log("INFO", msg, *args)

        def warning(self, msg: str, *args: object) -> None:
            self._log("WARNING", msg, *args)

        def error(self, msg: str, *args: object) -> None:
            self._log("ERROR", msg, *args)

        def reset(self) -> None:
            self.messages.clear()

    return MockLogger()


@pytest.fixture
def mock_config():
    """Configuration dict with test-safe defaults.

    Mirrors the module-level constants from ``cyrus_brain.py`` and
    ``main.py`` with values safe for testing (port 0 for OS-assigned,
    localhost only, short timeouts).

    Returns:
        dict: Configuration dictionary. Modify individual keys as needed.

    Usage::

        def test_custom_port(mock_config):
            mock_config["brain_port"] = 9999
            assert mock_config["brain_port"] == 9999
    """
    return {
        "brain_host": "localhost",
        "brain_port": 0,
        "hook_port": 0,
        "mobile_port": 0,
        "vscode_title": "Visual Studio Code",
        "max_speech_words": 50,
        "speech_threshold": 0.5,
        "wake_words": frozenset({"cyrus", "test"}),
    }


@pytest.fixture
def mock_send():
    """Callable that records IPC messages instead of sending over TCP.

    Drop-in replacement for ``_send(msg: dict)`` from ``cyrus_hook.py``.
    Records each call's argument in ``.messages`` for assertion.

    Returns:
        MockSend: Callable with ``.messages`` list and ``.reset()`` method.

    Usage::

        def test_hook_sends_stop(mock_send):
            mock_send({"event": "stop", "cwd": "/tmp"})
            assert mock_send.messages[-1]["event"] == "stop"
    """

    class MockSend:
        def __init__(self):
            self.messages: list[dict] = []

        def __call__(self, msg: dict) -> None:
            self.messages.append(msg)

        def reset(self) -> None:
            self.messages.clear()

    return MockSend()
```

### Step 5: Verify — install deps and run pytest

```bash
cd /home/daniel/Projects/barf/cyrus
pip install -r cyrus2/requirements-dev.txt
```

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/ -v --collect-only
```

Expected: exit code 0, "no tests ran" or "0 items collected". No import errors.

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/ --fixtures -q | grep -E "(tmp_project_dir|mock_logger|mock_config|mock_send)"
```

Expected: all 4 custom fixtures listed with their docstrings.

### Step 6: Verify — conftest.py imports without error

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
python -c "import tests.conftest; print('OK')"
```

Expected: prints "OK" with no errors.

## Files Created/Modified

| File | Action | Purpose |
|---|---|---|
| `cyrus2/tests/__init__.py` | Create (empty) | Package discovery |
| `cyrus2/tests/conftest.py` | Create | Shared fixtures |
| `cyrus2/requirements-dev.txt` | Create or update | Test dependencies |
| `cyrus2/pytest.ini` | Create | pytest + asyncio config |

## Risk Assessment

**Low risk.** Four new files, no changes to existing code. The only dependencies are:
- Issue 003 may have already created `requirements-dev.txt` — handled by create-or-update logic
- Issue 001 may have created `pyproject.toml` — we use standalone `pytest.ini` to avoid conflicts
- Fixtures are forward-compatible with planned Issues 005 (config extraction) and 009 (logger module)

The fixtures define interfaces that downstream test issues (019–024) will consume. Getting these interfaces right now prevents churn later.
