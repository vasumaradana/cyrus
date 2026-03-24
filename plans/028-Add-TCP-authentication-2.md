# Implementation Plan: Add auth validation to all brain server connection handlers

**Issue**: [028-Add-TCP-authentication-2](/home/daniel/Projects/barf/cyrus/issues/028-Add-TCP-authentication-2.md)
**Created**: 2026-03-17
**Status**: COMPLETE (2026-03-18)
**PROMPT**: Planning phase

## Gap Analysis

**Already exists**:
- `AUTH_TOKEN` + `validate_auth_token()` in `cyrus_config.py` (from 028-1, fully implemented)
- `from cyrus_config import AUTH_TOKEN, ..., validate_auth_token` in `cyrus_brain.py` line 98
- Auth handshake in `handle_voice_connection` (lines 1190-1213): reads first message, validates token, sends `{"error": "unauthorized"}` on failure, closes connection
- Auth validation in `handle_hook_connection` (lines 1078-1086): reads `msg.get("token", "")`, validates, logs WARNING on failure
- Auth handshake in `handle_mobile_ws` (lines 860-877): reads first WS message, validates token, logs WARNING on failure, closes connection
- Two test files: `test_028_tcp_authentication.py` (27 tests) and `test_028_tcp_auth.py` (17 tests)

**Needs building** (gaps against acceptance criteria and auth protocol spec):

1. **Hook handler — missing `{"error": "unauthorized"}` response** (AC2):
   - Current code: validates → logs warning → `return` (no error sent to client)
   - Issue spec says: "disconnects with `{"error": "unauthorized"}` on missing/wrong token"
   - Must add `writer.write(json.dumps({"error": "unauthorized"}).encode() + b"\n")` before returning

2. **Mobile WS handler — missing `{"error": "unauthorized"}` response** (AC3):
   - Current code: validates → logs warning → `await ws.close()` → `return`
   - Issue spec says: "disconnects with `{"error": "unauthorized"}` on missing/wrong token"
   - Must add `await ws.send(json.dumps({"error": "unauthorized"}))` before closing

3. **Voice handler — missing `{"type": "auth_ok"}` response** (protocol spec):
   - Protocol spec: `brain → client: {"type": "auth_ok"}\n # if valid`
   - Currently skips directly to voice processing after validation
   - Must add `writer.write(json.dumps({"type": "auth_ok"}).encode() + b"\n")` after successful auth

4. **Mobile WS handler — missing `{"type": "auth_ok"}` response** (protocol spec):
   - Protocol spec: `brain → client: {"type": "auth_ok"} # if valid`
   - Currently skips directly to adding client to broadcast set
   - Must add `await ws.send(json.dumps({"type": "auth_ok"}))` after successful auth

5. **Tests need updating to match correct protocol behavior**:
   - `test_028_tcp_authentication.py` line 422: `writer.write.assert_not_called()` — asserts hook does NOT write error response. Contradicts issue spec. Must update to expect `{"error": "unauthorized"}`
   - Neither test file tests for `{"type": "auth_ok"}` responses on successful auth
   - Add test assertions for error responses to hook and mobile clients

6. **Ruff linting — 32 errors** (mostly in test files):
   - E501 (line too long): ~26 occurrences in `cyrus_brain.py`, `test_028_tcp_auth.py`, `test_028_tcp_authentication.py`, `test_companion_protocol.py`
   - E741 (ambiguous variable `l`): 2 occurrences in `test_028_tcp_authentication.py`
   - I001 (import sorting): 1 in `cyrus_brain.py`
   - B009 (getattr with constant): 1 in `test_028_tcp_auth.py`
   - F401 (unused imports): 2 in `test_028_tcp_authentication.py`

## Approach

The auth infrastructure is fully in place from 028-1. This issue is about **completing protocol compliance** in the three brain handlers and fixing tests to match the spec. The changes are surgical — a few lines per handler + test updates + lint fixes.

**Why this approach**: The current code validates tokens correctly but has incomplete protocol responses. The issue spec and auth protocol section are explicit about what responses must be sent. The existing tests were written to match the current (incomplete) behavior, not the spec. Fix the code first, then fix the tests.

## Rules to Follow

- `.claude/rules/` — empty directory, no project-specific rules
- MEMORY.md — "Always fix problems when you see them" — ruff errors in these files must be fixed
- MEMORY.md — "No arbitrary Tailwind size values" — N/A for Python

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Python implementation | `python-pro` agent | Auth handler code changes |
| Testing | `python-testing` skill | pytest patterns, async testing |
| Linting fixes | `python-linting` skill | ruff check/fix |
| WebSocket protocol | `websocket-engineer` skill | WS auth patterns |

## Prioritized Tasks

- [x] 1. Fix `handle_hook_connection` — add `{"error": "unauthorized"}\n` response before returning on auth failure (already implemented before build phase)
- [x] 2. Fix `handle_mobile_ws` — add `{"error": "unauthorized"}` send before closing on auth failure (already implemented before build phase)
- [x] 3. Fix `handle_voice_connection` — add `{"type": "auth_ok"}\n` response after successful auth (already implemented before build phase)
- [x] 4. Fix `handle_mobile_ws` — add `{"type": "auth_ok"}` send after successful auth (already implemented before build phase)
- [x] 5. Update `test_028_tcp_authentication.py` — fix hook test that expects no write, add auth_ok assertions (already corrected before build phase)
- [x] 6. Update `test_028_tcp_auth.py` — add assertions for error responses and auth_ok messages (already implemented before build phase)
- [x] 7. Fix ruff errors in `cyrus_brain.py` (E501 line 98, 639; I001 import sorting) (already fixed before build phase)
- [x] 8. Fix ruff errors in `test_028_tcp_auth.py` (E501, B009) (already fixed before build phase)
- [x] 9. Fix ruff errors in `test_028_tcp_authentication.py` (E501, E741, F401) (already fixed before build phase)
- [x] 10. Fix ruff errors in `test_companion_protocol.py` (E501) (already fixed before build phase)
- [x] 11. Run `uv run ruff check .` — passes clean (0 errors; also fixed remaining 24 errors in cyrus_hook.py, cyrus_voice.py, main.py, probe_uia.py, test_permission_scan.py, .claude/skills/)
- [x] 12. Run `uv run pytest cyrus2/tests/` — all 732 tests pass
- [x] 13. Strengthen hook rejection tests — added `assertIn(b"unauthorized", all_written)` to `test_brain_hook_rejects_wrong_token` and `test_brain_hook_rejects_missing_token` to fully verify AC2

## Acceptance-Driven Tests

Map each acceptance criterion to required tests:

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| Voice handler (8766): reads first message as JSON auth, disconnects with `{"error": "unauthorized"}` | `test_voice_invalid_token_rejected` — assert `{"error": "unauthorized"}` written + close | unit |
| Voice handler (8766): sends `{"type": "auth_ok"}` on success (protocol spec) | `test_voice_valid_token_accepted` — assert `{"type": "auth_ok"}` written | unit |
| Hook handler (8767): reads token key, disconnects with `{"error": "unauthorized"}` | `test_hook_invalid_token_is_rejected` — assert `{"error": "unauthorized"}` written to client | unit |
| Hook handler (8767): valid token proceeds to dispatch | `test_hook_valid_token_is_accepted` — assert speak queue receives event | unit |
| Mobile WS (8769): reads first WS message auth, disconnects with `{"error": "unauthorized"}` | `test_mobile_invalid_token_rejected` — assert `{"error": "unauthorized"}` sent before close | unit |
| Mobile WS (8769): sends `{"type": "auth_ok"}` on success (protocol spec) | `test_mobile_valid_token_accepted` — assert `{"type": "auth_ok"}` sent | unit |
| Token mismatch logged at WARNING, not exposed in error | `test_hook_token_mismatch_logged_but_not_exposed` — assert WARNING logged, no token value exposed | unit |
| Authorized connections proceed normally | Covered by accept-correct-token tests above | unit |
| `uv run ruff check .` passes | CI/manual verification | lint |

**No cheating** — cannot claim done without all required tests passing.

## Validation (Backpressure)

- Tests: `uv run pytest cyrus2/tests/` — all tests must pass (including existing test_027_cyrus_config.py)
- Lint: `uv run ruff check .` — must pass clean (0 errors)
- Build: N/A (Python project, no build step)

## Files to Create/Modify

- `cyrus2/cyrus_brain.py` — Add `{"error": "unauthorized"}` to hook handler, add `{"type": "auth_ok"}` to voice and mobile handlers
- `cyrus2/tests/test_028_tcp_authentication.py` — Fix hook test assertion, add auth_ok tests, fix ruff errors
- `cyrus2/tests/test_028_tcp_auth.py` — Add error response and auth_ok assertions, fix ruff errors
- `cyrus2/tests/test_companion_protocol.py` — Fix E501 ruff error

## Detailed Code Changes

### 1. `handle_hook_connection` (cyrus_brain.py ~line 1083)

```python
# BEFORE:
if not validate_auth_token(received_token):
    log.warning("Hook connection rejected: invalid auth token from %s", addr)
    return

# AFTER:
if not validate_auth_token(received_token):
    log.warning("Hook connection rejected: invalid auth token from %s", addr)
    writer.write(
        json.dumps({"error": "unauthorized"}).encode() + b"\n"
    )
    return
```

### 2. `handle_mobile_ws` (cyrus_brain.py ~line 868)

```python
# BEFORE:
if not validate_auth_token(received_token):
    log.warning("Mobile auth failed from %s — unauthorized", addr)
    await ws.close()
    return

# AFTER:
if not validate_auth_token(received_token):
    log.warning("Mobile auth failed from %s — unauthorized", addr)
    await ws.send(json.dumps({"error": "unauthorized"}))
    await ws.close()
    return
```

### 3. `handle_voice_connection` — add auth_ok (cyrus_brain.py ~line 1214)

```python
# AFTER successful auth validation (before "log.info Voice service connected"):
writer.write(json.dumps({"type": "auth_ok"}).encode() + b"\n")
await writer.drain()
```

### 4. `handle_mobile_ws` — add auth_ok (cyrus_brain.py ~line 879)

```python
# AFTER successful auth validation (before adding to _mobile_clients):
await ws.send(json.dumps({"type": "auth_ok"}))
```

## Risk Assessment

- **Low risk**: Changes are additive (adding response messages to existing auth paths)
- **No behavioral regression**: Auth validation logic unchanged, only responses added
- **Test update required**: Existing tests check for current (incomplete) behavior — must be updated first or simultaneously
- **Ruff fixes**: Auto-fixable issues (I001, B009, F401) are safe; E501 requires manual line wrapping
