# Implementation Plan: Issue 036 — Add Health Check Endpoint

**Issue**: [036-Add-health-check-endpoint](/home/daniel/Projects/barf/cyrus/issues/036-Add-health-check-endpoint.md)
**Created**: 2026-03-18
**PROMPT**: `/home/daniel/Projects/barf/cyrus/cyrus/plans/036-Add-health-check-endpoint.md`

## Gap Analysis

### Already Exists
- `cyrus2/cyrus_brain.py` — async main loop with 3 servers (voice TCP :8766, hook TCP :8767, mobile WS :8769) and `asyncio.gather()` pattern
- `cyrus2/cyrus_config.py` — centralized env-var config with port constants (`BRAIN_PORT`, `HOOK_PORT`, `MOBILE_PORT`, `COMPANION_PORT`, `SERVER_PORT`), `HEADLESS` flag, `AUTH_TOKEN`
- `cyrus2/cyrus_brain.py` `_init_servers()` function (lines 1371-1413) — creates and returns all three servers, easily extensible
- `cyrus2/cyrus_brain.py` `main()` (lines 1419-1461) — `asyncio.gather()` with `serve_forever()` calls
- `cyrus2/.env.example` — documents all CYRUS_* env vars
- `cyrus2/requirements-brain.txt` — has `websockets` but NOT `aiohttp`
- `cyrus2/tests/conftest.py` — shared fixtures (mock_logger, mock_config, mock_send)
- Session tracking: `SessionManager` class manages registered sessions
- `_active_project` global with `_active_project_lock` for thread-safe access

### Needs Building
1. `HEALTH_PORT` constant in `cyrus_config.py` (default 8771, env var `CYRUS_HEALTH_PORT`)
2. `aiohttp` dependency in `requirements-brain.txt`
3. Health check HTTP handler using aiohttp (async, non-blocking)
4. Health server startup in `_init_servers()` or dedicated function
5. Integration into `main()` `asyncio.gather()` — must not block brain
6. `CYRUS_HEALTH_PORT` entry in `.env.example`
7. Test file `tests/test_036_health_check.py`

## Approach

**Selected**: aiohttp async HTTP server on port 8771 (per interview Q&A decisions).

**Why aiohttp over stdlib http.server**:
- Brain already uses asyncio extensively — aiohttp integrates natively with the event loop
- No separate thread needed — runs as a coroutine alongside existing servers
- Clean JSON response support via `web.json_response()`
- Non-blocking by design — won't stall the main loop
- Production-quality HTTP parsing (stdlib `http.server` is "not recommended for production")

**Why port 8771**:
- Port 8766 is voice TCP, 8767 is hook TCP, 8769 is mobile WS, 8770 is companion
- 8771 follows the sequential port allocation pattern and avoids conflicts
- Confirmed in interview Q&A

**Health response design**:
```json
{
  "status": "ok",
  "timestamp": 1710000000.0,
  "sessions": 2,
  "active_project": "my-project",
  "headless": true
}
```

Non-`/health` paths return 404. Logs are suppressed to avoid noise.

## Rules to Follow
- `.claude/rules/` — directory is empty; no project-specific rules files
- Follow existing code patterns observed in `cyrus_config.py` (env-var constants), `_init_servers()` (server creation), and test files (acceptance-driven TDD with Windows module mocking)

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Write tests first (TDD) | `python-testing` skill | pytest patterns, async test fixtures, mocking |
| Implementation code | `python-expert` skill | Type-safe async code, aiohttp patterns |
| Code style | `python-code-style` skill | ruff compliance, naming, docstrings |
| Test automation | `test-automator` agent | Run and validate test suite |

## Prioritized Tasks

- [x] 1. Add `HEALTH_PORT` constant to `cyrus2/cyrus_config.py`
- [x] 2. Add `CYRUS_HEALTH_PORT` entry to `cyrus2/.env.example`
- [x] 3. Add `aiohttp==3.13.3` to `cyrus2/requirements-brain.txt`
- [x] 4. Write acceptance-driven tests `cyrus2/tests/test_036_health_check.py` (TDD — tests first)
- [x] 5. Implement `HealthHandler` / health server in `cyrus2/cyrus_brain.py`:
  - Created `_start_health_server()` async function using aiohttp
  - `GET /health` → 200 JSON with status, timestamp, sessions, active_project, headless
  - All other paths → 404 (aiohttp default behaviour)
  - Suppress access logs via `access_log=None` on AppRunner
- [x] 6. Integrate health server into `_init_servers()` and `main()` asyncio.gather()
  - `_start_health_server()` called at end of `_init_servers()`; runner returned as 5th tuple element
  - Cleanup registered via `stack.push_async_callback(health_runner.cleanup)` in main()
- [x] 7. Run tests, lint, format — all 18 tests in test_036 pass, lint clean, format clean
- [x] 8. Fix port conflict: `test_034_brain_registration_listener.py` two tests calling `_init_servers()` left port 8771 bound between tests; patched `_start_health_server` in both test contexts. Full suite: 846 passed, 0 failed

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| HTTP server on port 8771 | `test_health_server_binds_to_configured_port` | unit |
| `GET /health` returns 200 with JSON | `test_health_endpoint_returns_200_json` | integration |
| Response includes status, sessions, active_project | `test_health_response_contains_required_fields` | integration |
| Response includes headless flag | `test_health_response_includes_headless` | unit |
| Response includes timestamp | `test_health_response_includes_timestamp` | unit |
| Non-/health paths return 404 | `test_non_health_path_returns_404` | integration |
| Never crashes/blocks brain main loop | `test_health_server_is_async_non_blocking` | unit |
| HEALTH_PORT configurable via env var | `test_health_port_from_env` | unit |
| HEALTH_PORT default is 8771 | `test_health_port_default` | unit |
| .env.example has CYRUS_HEALTH_PORT | `test_env_example_has_health_port` | unit |
| aiohttp in requirements-brain.txt | `test_requirements_has_aiohttp` | unit |
| Callable from docker/monitoring tools | `test_health_response_is_valid_json` | integration |
| Access logs suppressed | `test_health_server_suppresses_logs` | unit |

**No cheating** — cannot claim done without all required tests passing.

## Validation (Backpressure)

- **Tests**: `pytest cyrus2/tests/test_036_health_check.py -v` — all tests pass
- **Full suite**: `pytest cyrus2/tests/ -v` — no regressions
- **Lint**: `ruff check cyrus2/` — no errors
- **Format**: `ruff format --check cyrus2/` — no changes needed

## Files to Create/Modify

- **Modify**: `cyrus2/cyrus_config.py` — add `HEALTH_PORT` constant (line ~48, after COMPANION_PORT)
- **Modify**: `cyrus2/.env.example` — add `CYRUS_HEALTH_PORT=8771` entry
- **Modify**: `cyrus2/requirements-brain.txt` — add `aiohttp` dependency
- **Modify**: `cyrus2/cyrus_brain.py` — add health server function + integrate into `_init_servers()` and `main()`
- **Create**: `cyrus2/tests/test_036_health_check.py` — acceptance-driven tests

## Key Design Decisions

1. **aiohttp over stdlib**: Native async integration with existing event loop; no threading overhead; production-quality HTTP. Confirmed in interview Q&A.
2. **Port 8771**: Sequential allocation following existing pattern (8766-8770 already taken). Confirmed in interview Q&A.
3. **No auth on /health**: Health endpoints are typically unauthenticated for Docker/k8s probes. If needed later, can add optional token check.
4. **Separate from existing servers**: Health is HTTP, not TCP or WebSocket. Own port avoids protocol conflicts.
5. **aiohttp.web.AppRunner pattern**: Allows starting the HTTP server as a coroutine that integrates with `asyncio.gather()` without blocking.
6. **Session count from SessionManager**: Use `len(session_mgr.sessions)` or equivalent to report registered session count.

## Risks / Unknowns

- **aiohttp version pinning**: Need to check compatible version for Python 3.10+. Use latest stable (e.g., `aiohttp>=3.9`).
- **SessionManager access**: Need to verify how to access registered sessions count — may need to pass `session_mgr` to health handler or use a global reference. Will resolve during implementation by reading SessionManager API.
