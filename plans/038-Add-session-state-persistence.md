# Implementation Plan: Issue 038 — Add Session State Persistence

**Issue**: [038-Add-session-state-persistence](/home/daniel/Projects/barf/cyrus/issues/038-Add-session-state-persistence.md)
**Created**: 2026-03-18
**PROMPT**: `/home/daniel/Projects/barf/cyrus/cyrus/plans/038-Add-session-state-persistence.md`

## Gap Analysis

### Already Exists
- `cyrus2/cyrus_brain.py` — async `main()` with `asyncio.run()` and `KeyboardInterrupt` catch (lines 1464-1470)
- `cyrus2/cyrus_common.py` — `SessionManager` class with `_aliases: dict[str, str]` (line 1342), `.aliases` property (line 1348), `.rename_alias()` (line 1381)
- `cyrus2/cyrus_common.py` — `ChatWatcher._pending_queue: list[str]` (line 495) per-project queued responses for inactive sessions
- `cyrus2/cyrus_config.py` — centralized env-var config pattern (`BRAIN_PORT`, `HOOK_PORT`, etc. with `os.environ.get()` + fallback defaults)
- `.env.example` — documents all `CYRUS_*` env vars (3 entries currently)
- `cyrus2/tests/conftest.py` — shared fixtures (`mock_logger`, `mock_config`, `mock_send`, `tmp_path`)
- `cyrus2/pyproject.toml` — pytest configured with `testpaths = ["tests"]`, ruff lint rules

### Needs Building
1. `_get_state_file()` — resolve state file path from `CYRUS_STATE_FILE` env var or default `~/.cyrus/state.json`
2. `_save_state(session_mgr)` — serialize aliases, pending queues, project list to JSON with atomic write (.tmp → rename)
3. `_load_state(session_mgr)` — deserialize and restore aliases from state file at startup
4. Signal handlers via `asyncio.add_signal_handler()` for SIGTERM/SIGINT → save state on shutdown
5. File permissions restricted to 0600 after write
6. Versioned state format (version: 1) with corruption handling
7. `CYRUS_STATE_FILE` env var support in `cyrus_config.py`
8. `.env.example` update with `CYRUS_STATE_FILE` documentation
9. Test file `tests/test_038_session_state_persistence.py`

## Approach

**Selected**: Module-level functions in `cyrus_brain.py` for state persistence, integrated with `main()` startup and shutdown.

**Why module-level functions (not a class)**:
- Matches the existing pattern in `cyrus_brain.py` — helper functions like `_init_queues()`, `_init_session()`, `_init_servers()` are all module-level
- State persistence is a cross-cutting concern that reads from `SessionManager` — no need for a separate class
- Signal handlers need access to the session manager; passing it as a closure argument is clean

**Why `asyncio.add_signal_handler()` (per interview Q&A)**:
- `asyncio.run()` already installs a SIGINT handler that raises `KeyboardInterrupt`
- Using `asyncio.add_signal_handler()` within the event loop integrates cleanly with the existing async architecture
- Avoids conflicts with asyncio's own signal handling
- Note: `asyncio.add_signal_handler()` only works on Unix — on Windows, fall back to `signal.signal()` or `atexit`

**Atomic write strategy**:
- Write to `state_file.with_suffix('.tmp')` first
- `temp_file.replace(state_file)` for atomic rename (POSIX guarantees)
- `state_file.chmod(0o600)` after write for security

**State format**:
```json
{
  "version": 1,
  "timestamp": 1710000000.0,
  "aliases": {"my project": "my-project", "backend": "backend-service"},
  "projects": ["my-project", "backend-service"],
  "pending_queues": {"my-project": ["response 1", "response 2"]}
}
```

**Load strategy (per interview Q&A — "load but don't auto-replay")**:
- Aliases are restored into `SessionManager._aliases` via direct dict update
- Pending queues are loaded into state but NOT auto-flushed — user can manually trigger via "switch to X"
- Projects list is informational only — actual sessions are discovered from VS Code windows

**Corruption handling**:
- Missing file → log and start fresh (normal first run)
- `json.JSONDecodeError` → log warning and start fresh
- Unsupported version → log warning and skip
- Any other exception → log error and start fresh

## Rules to Follow
- `.claude/rules/` — directory is empty; no project-specific rule files
- Follow existing patterns: env-var config in `cyrus_config.py`, init functions in `cyrus_brain.py`, acceptance-driven TDD with Windows module mocking in tests

## Skills & Agents to Use
| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Implementation | `python-expert` skill | Python best practices, type hints, error handling |
| Testing | `python-testing` skill | pytest patterns, fixtures, mocking strategies |
| Code review | `python-pro` skill | Modern Python 3.10+ patterns |

## Prioritized Tasks

- [x] **1. Add `CYRUS_STATE_FILE` to `cyrus_config.py`** — env var with empty string default (empty = use `~/.cyrus/state.json`). Follow existing pattern: `CYRUS_STATE_FILE = os.environ.get("CYRUS_STATE_FILE", "")`.

- [x] **2. Add `_get_state_file()` to `cyrus_brain.py`** — resolves state file path. Reads `os.environ.get("CYRUS_STATE_FILE", "")` at call-time (not import-time constant) so env overrides take effect in tests. Creates parent dir with `mkdir(parents=True, exist_ok=True)`.

- [x] **3. Add `_save_state(session_mgr)` to `cyrus_brain.py`** — serializes state to JSON:
  - Collect `session_mgr.aliases` (already returns a copy)
  - Collect pending queues: iterate `session_mgr._chat_watchers` and read each `._pending_queue`
  - Collect project list: `list(session_mgr._chat_watchers.keys())`
  - Write to temp file → atomic rename → chmod 0o600
  - Log success/failure via `log.info()`/`log.error(exc_info=True)`

- [x] **4. Add `_load_state(session_mgr)` to `cyrus_brain.py`** — restores state from JSON:
  - Check file exists; if not, log info and return
  - Parse JSON; handle `JSONDecodeError` gracefully
  - Validate `version == 1`; skip unsupported versions
  - Restore aliases into `session_mgr._aliases` via `.update()`
  - Log counts of restored aliases

- [x] **5. Add `_init_signal_handlers(loop, session_mgr)` and wire into `main()`** — extracted as a separate `_init_*()` function to keep `main()` < 50 lines:
  - Call `_load_state(session_mgr)` immediately after `_init_session(loop)` returns
  - Call `_init_signal_handlers(loop, session_mgr)` before `_init_background_threads()`
  - Register `SIGTERM` and `SIGINT` via `loop.add_signal_handler()`
  - Handler calls `_save_state(session_mgr)` then `loop.stop()`
  - Falls back to `atexit.register(_save_state, session_mgr)` on Windows

- [x] **6. Update `.env.example`** — added `CYRUS_STATE_FILE` entry with documentation comment

- [x] **7. Write acceptance tests** — `tests/test_038_session_state_persistence.py` (30 tests, all pass):
  - Test default state file path (`~/.cyrus/state.json`)
  - Test `CYRUS_STATE_FILE` env var override
  - Test `_save_state()` creates valid JSON with correct structure
  - Test atomic write (temp file then rename)
  - Test file permissions (0o600)
  - Test `_load_state()` restores aliases
  - Test graceful handling of missing state file
  - Test graceful handling of corrupted JSON
  - Test graceful handling of unsupported version
  - Test pending queues serialization
  - Test state round-trip (save → load → verify)

- [x] **8. Run linting and full test suite** — `ruff check`, `ruff format --check`, `pytest tests/` — all 892 tests pass, no regressions

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| State saved to `~/.cyrus/state.json` on shutdown | Test `_save_state()` writes to correct path; test signal handler triggers save | unit |
| State includes aliases, pending queues, project mappings | Test saved JSON contains all three keys with correct data | unit |
| Atomic writes (tmp → rename) | Test that `.tmp` file is created and renamed; verify no partial writes | unit |
| State loaded from file at startup | Test `_load_state()` restores aliases into SessionManager | unit |
| Gracefully handles missing state file | Test `_load_state()` with nonexistent path returns without error | unit |
| Gracefully handles corrupted state file | Test `_load_state()` with invalid JSON logs warning and continues | unit |
| State file permissions 0600 | Test file mode after `_save_state()` is `0o600` | unit |
| Configurable via `CYRUS_STATE_FILE` env var | Test `_get_state_file()` with/without env var | unit |

**No cheating** — cannot claim done without all required tests passing.

## Validation (Backpressure)
- **Tests**: `pytest cyrus2/tests/test_038_session_state_persistence.py -v` — all tests pass
- **Full suite**: `pytest cyrus2/tests/ -v` — no regressions
- **Lint**: `ruff check cyrus2/` — no errors
- **Format**: `ruff format --check cyrus2/` — no formatting issues

## Files to Create/Modify
- **Modify**: `cyrus2/cyrus_config.py` — add `CYRUS_STATE_FILE` constant
- **Modify**: `cyrus2/cyrus_brain.py` — add `_get_state_file()`, `_save_state()`, `_load_state()`, signal handlers in `main()`
- **Modify**: `.env.example` — add `CYRUS_STATE_FILE` documentation
- **Create**: `cyrus2/tests/test_038_session_state_persistence.py` — acceptance-driven test suite

## Key Design Decisions

### Why not persist to SessionManager class directly?
SessionManager is defined in `cyrus_common.py` which is shared infrastructure. Adding file I/O there would mix concerns. The persistence layer in `cyrus_brain.py` reads from/writes to SessionManager's public interface, keeping responsibilities separated.

### Why load aliases but not auto-replay pending queues?
Per interview Q&A decision: pending queues are loaded for manual recovery. Auto-replaying could cause confusing TTS output on restart. User triggers replay by switching to the project ("switch to X"), which calls `SessionManager.on_session_switch()` → `flush_pending()`.

### Pending queue restoration challenge
ChatWatcher instances are created dynamically when VS Code windows are discovered (every 5 seconds by SessionManager.start()). Pending queues from a previous session may need to be injected into ChatWatcher after it's created. Solution: store loaded pending queues in a module-level dict, and have a hook in `_add_session()` or check after session creation to inject them.

### Windows compatibility for signal handlers
`asyncio.add_signal_handler()` is Unix-only. On Windows, use `atexit.register(_save_state)` as a fallback. The try/except pattern handles this cleanly.
