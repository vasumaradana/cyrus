# Implementation Plan: Add Brain Registration Listener

**Issue**: [034-Add-brain-registration-listener](/home/daniel/Projects/barf/cyrus/cyrus/issues/034-Add-brain-registration-listener.md)
**Created**: 2026-03-18
**PROMPT**: `/home/daniel/Projects/barf/cyrus/prompts/PROMPT_plan.md`

## Gap Analysis

**Already exists**:
- `COMPANION_PORT = 8770` in `cyrus_config.py` (line 45), importable
- `HEADLESS` flag fully integrated — guards Windows imports, disables UIA paths
- `_registered_sessions: dict[str, str]` in `cyrus_common.py` (line 151) — simple workspace→title mapping used by `_vs_code_windows()` for session discovery
- `_active_project` global with `_active_project_lock` in `cyrus_brain.py` (lines 132-133)
- Three existing async TCP/WS servers in `_init_servers()` following consistent pattern: `asyncio.start_server()` with lambda handler, log listening address
- Auth infrastructure: `AUTH_TOKEN`, `validate_auth_token()` from `cyrus_config`
- `ChatWatcher` and `PermissionWatcher` classes in `cyrus_common.py` — created via `SessionManager`
- Test fixtures in `conftest.py` and established async test pattern using `unittest.IsolatedAsyncioTestCase`
- Windows module mocking pattern for cyrus_brain tests (`_WIN_MODS` list)

**Needs building**:
1. `SessionInfo` dataclass in `cyrus_brain.py` — tracks workspace, safe name, port, connection writer, created_at
2. `_registered_sessions: dict[str, SessionInfo]` in `cyrus_brain.py` (richer than the `cyrus_common` one, which stays as-is for `_vs_code_windows()` compat)
3. `_sessions_lock: threading.Lock` for thread-safe access
4. `_handle_registration_client(reader, writer)` async handler — processes register/focus/blur/permission_respond/prompt_respond messages
5. Registration server startup in `_init_servers()` (headless-only) or separate `_run_registration_server()`
6. Wire registration server into `main()` via `asyncio.gather()`
7. On register: populate both `cyrus_brain._registered_sessions` (SessionInfo) AND `cyrus_common._registered_sessions` (str) for backward compat
8. On disconnect: clean up both dicts
9. Tests: `test_034_brain_registration_listener.py`

## Approach

**Strategy: Add a fourth server to the existing server infrastructure.** Follow the exact same pattern as the voice/hook/mobile servers — `asyncio.start_server()` in `_init_servers()`, guarded by `HEADLESS` flag. The handler reads line-delimited JSON (same protocol as voice/hook connections) and dispatches on `msg["type"]`.

**Key design decisions**:
- **SessionInfo lives in cyrus_brain.py** — it holds `asyncio.StreamWriter` (connection reference) which is brain-specific, not common module material
- **Dual dict approach** — `cyrus_brain._registered_sessions` holds rich `SessionInfo` objects; on register/unregister, also update `cyrus_common._registered_sessions` (the simple `dict[str, str]`) so `_vs_code_windows()` continues working without changes
- **Auth token required** — follow Issue 028 pattern: first message must include `token` field validated via `validate_auth_token()`, consistent with other servers
- **Headless-only guard** — registration server only starts when `HEADLESS=True`. In non-headless mode, session discovery uses native window tracking.
- **Import COMPANION_PORT** from `cyrus_config` — it's already defined there (8770)

## Rules to Follow

- `.claude/rules/` — currently empty, no custom rules
- Follow existing server patterns in `cyrus_brain.py` (start_server, lambda handler, log address)
- Line-delimited JSON protocol with `\n` separator
- Proper locking for shared state (`threading.Lock`)
- Structured logging via `log` module logger (not print statements)
- Auth validation on connections (Issue 028 pattern)

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Implement SessionInfo + handler | `python-expert` skill | Type-safe async Python with dataclasses |
| Write tests | `python-testing` skill | pytest patterns, async test cases, mocking |
| Protocol implementation | `websocket-engineer` skill | TCP connection lifecycle, disconnect handling |
| Code quality check | `python-linting` skill | ruff check before commit |

## Prioritized Tasks

- [x] **1. Import COMPANION_PORT** — Add `COMPANION_PORT` to the `cyrus_config` import block in `cyrus_brain.py`
- [x] **2. Add SessionInfo dataclass** — Define `SessionInfo` with fields: `workspace: str`, `safe: str`, `port: int`, `connection: asyncio.StreamWriter`, `created_at: float` (default `time.time()`)
- [x] **3. Add module-level state** — `_registered_sessions: dict[str, SessionInfo] = {}` and `_sessions_lock = threading.Lock()` in cyrus_brain.py shared state section
- [x] **4. Implement `_handle_registration_client()`** — Async handler for registration connections:
  - Read line-delimited JSON in a loop
  - On `register`: create SessionInfo, store in `_registered_sessions`, also update `cyrus_common._registered_sessions[workspace] = f"{workspace} - Visual Studio Code"` for compat
  - On `focus`: set `_active_project` with lock
  - On `blur`: clear `_active_project` if it matches, with lock
  - On `permission_respond`: log and route to PermissionWatcher (TODO stub for now, per issue)
  - On `prompt_respond`: log and route to waiting code (TODO stub for now, per issue)
  - On disconnect (EOF or exception): remove from both dicts, log
- [x] **5. Add registration server to `_init_servers()`** — Conditionally start when `HEADLESS=True`:
  ```python
  if HEADLESS:
      reg_server = await asyncio.start_server(
          _handle_registration_client, host, COMPANION_PORT
      )
      log.info("Listening for companion registrations on %s:%s", host, COMPANION_PORT)
  ```
  Return it as part of the tuple (or None if not HEADLESS)
- [x] **6. Wire into `main()` asyncio.gather()** — Add `reg_server.serve_forever()` to the gather when HEADLESS (via contextlib.AsyncExitStack)
- [x] **7. Write tests** — `cyrus2/tests/test_034_brain_registration_listener.py`:
  - Test SessionInfo dataclass creation
  - Test register message adds to both dicts
  - Test focus message updates _active_project
  - Test blur message clears _active_project (only if matching)
  - Test blur message does NOT clear if workspace doesn't match
  - Test disconnect removes session from both dicts
  - Test multiple concurrent sessions
  - Test malformed JSON is skipped gracefully
  - Test permission_respond and prompt_respond are logged
  - Test server only starts in HEADLESS mode
- [x] **8. Lint & validate** — Run `ruff check` and `pytest`

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| Async TCP server on 0.0.0.0:8770 (headless only) | Test server binds in HEADLESS mode; test it does NOT bind when not HEADLESS | integration |
| `_registered_sessions: dict[str, SessionInfo]` tracks workspace, connection, port | Test SessionInfo fields populated correctly after register | unit |
| On `register`, add session + create watchers | Test register message populates both dicts; log output | unit |
| On `focus`, set `_active_project` | Test focus message sets `_active_project` to workspace | unit |
| On `blur`, clear `_active_project` if matches | Test blur clears when matching; test blur does NOT clear when different | unit |
| On `permission_respond`, forward to PermissionWatcher | Test log message for permission_respond | unit |
| On `prompt_respond`, forward to waiting code | Test log message for prompt_respond | unit |
| On disconnect, remove session | Test EOF triggers cleanup of both dicts | unit |
| Multiple concurrent sessions | Test two sessions registered, both tracked, one disconnect doesn't affect other | unit |
| Logs registration, focus, disconnects | Test log.info calls for each event type | unit |

**No cheating** — cannot claim done without required tests passing.

## Validation (Backpressure)

- **Tests**: `pytest cyrus2/tests/test_034_brain_registration_listener.py -v` must pass
- **Lint**: `ruff check cyrus2/cyrus_brain.py` must pass
- **Build**: Python import succeeds without errors
- **Existing tests**: `pytest cyrus2/tests/test_030_headless_mode.py -v` must still pass (backward compat with `cyrus_common._registered_sessions`)

## Files to Create/Modify

- **Modify**: `cyrus2/cyrus_brain.py` — add COMPANION_PORT import, SessionInfo dataclass, _registered_sessions dict, _sessions_lock, _handle_registration_client(), update _init_servers(), update main()
- **Create**: `cyrus2/tests/test_034_brain_registration_listener.py` — all acceptance-driven tests

## Risks & Open Questions

- **ChatWatcher/PermissionWatcher creation on register**: The issue says "create ChatWatcher (hooks-only) + PermissionWatcher (hooks-only)" on register. These are currently created by SessionManager. For this issue, the handler will log the intent but route to existing SessionManager infrastructure. Full watcher creation may need SessionManager API changes — document as TODO if not straightforward.
- **Auth on registration port**: Issue doesn't mention auth explicitly, but all other ports require it (Issue 028). Following the established pattern and requiring auth token.
- **`_init_servers()` return type change**: Currently returns 3-tuple. Adding optional 4th element (reg_server or None) changes the contract. Alternative: start reg_server separately in main(). Choose whichever is cleaner.
