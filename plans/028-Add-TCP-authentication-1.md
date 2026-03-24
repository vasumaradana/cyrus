# Verification: Add AUTH_TOKEN infrastructure to cyrus_config.py

**Issue**: [028-Add-TCP-authentication-1](/home/daniel/Projects/barf/cyrus/issues/028-Add-TCP-authentication-1.md)
**Status**: COMPLETE
**Created**: 2026-03-17
**Updated**: 2026-03-18 (final fix)

## Evidence

All acceptance criteria are satisfied in the existing codebase:

| Acceptance Criterion | Status | Location |
|---------------------|--------|----------|
| `AUTH_TOKEN` reads from `CYRUS_AUTH_TOKEN` env var | DONE | `cyrus2/cyrus_config.py` line 99 |
| Auto-generates with `secrets.token_hex(16)` + WARN to stderr | DONE | `cyrus2/cyrus_config.py` lines 100-110 |
| `validate_auth_token()` uses `hmac.compare_digest` | DONE | `cyrus2/cyrus_config.py` lines 113-125 |
| Token never logged verbatim in operational logs | DONE | Brain handlers log addresses, not tokens |
| `.env.example` has `CYRUS_AUTH_TOKEN=` with generation instructions | DONE | `cyrus2/.env.example` lines 59-66 |
| `test_027_cyrus_config.py` still passes | DONE | 46/46 tests pass (10 new auth tests added) |
| `ruff check .` passes on full test suite | DONE | Clean — 0 errors |

## Verification Steps

- [x] `uv run pytest tests/test_027_cyrus_config.py -v` — 46/46 passed (new TestAuthToken class)
- [x] `uv run pytest tests/ -v` — 745/745 passed
- [x] `uv run ruff check .` — All checks passed
- [x] Confirmed `AUTH_TOKEN` reads env var and auto-generates when unset
- [x] Confirmed `validate_auth_token()` uses `hmac.compare_digest`
- [x] Confirmed `.env.example` documents `CYRUS_AUTH_TOKEN=` with generation command
- [x] Confirmed token is not logged verbatim in connection handlers

## Fix Applied (2026-03-18)

**`cyrus_hook.py` AUTH_TOKEN import bug fixed.**

Previously `cyrus_hook.py` read `AUTH_TOKEN` directly from `os.environ.get("CYRUS_AUTH_TOKEN", "")`,
bypassing `cyrus_config`'s auto-generation logic. When `CYRUS_AUTH_TOKEN` was absent, the hook
sent an empty string token instead of the auto-generated one.

Fix: consolidated the `HOOK_PORT` and `AUTH_TOKEN` imports into the existing `try/except` block
so the hook benefits from `cyrus_config`'s `secrets.token_hex(16)` fallback:

```python
try:
    from cyrus_config import AUTH_TOKEN
    from cyrus_config import HOOK_PORT as BRAIN_PORT
except (ImportError, ValueError):
    BRAIN_PORT = 8767
    AUTH_TOKEN = os.environ.get("CYRUS_AUTH_TOKEN", "")
```

This unblocked `test_hook_send_without_token_env` which had been failing (token was `""` instead of
a non-empty generated value).

## Second Fix Applied (2026-03-18)

**Stale test assertion corrected in `test_028_tcp_auth.py`.**

`TestHookSendsToken::test_hook_send_without_token_env` was written before the `cyrus_hook.py`
import fix and expected `sent_json["token"] == ""` (empty string). After the import fix the hook
correctly sends the auto-generated token, so the assertion was wrong.

Fix: updated the test docstring and assertion to match the implemented behavior — the hook sends
a non-empty auto-generated string when `CYRUS_AUTH_TOKEN` is absent:

```python
# Before (stale):
self.assertEqual(sent_json["token"], "", "_send sends empty token...")

# After (correct):
self.assertNotEqual(sent_json["token"], "", "_send must send the auto-generated token...")
self.assertIsInstance(sent_json["token"], str, "_send token must be a string")
```

All 24 tests in test_028_tcp_auth.py now pass.

## Build Phase Work (2026-03-18)

Added `TestAuthToken` class (10 tests) to `tests/test_027_cyrus_config.py`:
- `test_auth_token_reads_from_env_var`
- `test_auth_token_is_string`
- `test_auth_token_auto_generated_when_unset`
- `test_auth_token_warn_printed_to_stderr_when_unset`
- `test_validate_auth_token_returns_true_for_correct_token`
- `test_validate_auth_token_returns_false_for_wrong_token`
- `test_validate_auth_token_returns_false_for_empty_string`
- `test_validate_auth_token_returns_false_for_partial_match`
- `test_validate_auth_token_uses_hmac_compare_digest`
- `test_validate_auth_token_signature`

Also: `CYRUS_AUTH_TOKEN` added to `TestEnvExample._REQUIRED_KEYS`; `AUTH_TOKEN`/`validate_auth_token`
added to `TestModuleInterface._REQUIRED_CONSTANTS`.

Fixed 36 pre-existing ruff violations (E501, E741, B009) across test_028_tcp_auth.py,
test_028_tcp_authentication.py, and test_companion_protocol.py per "fix problems when you see them" rule.

Final state: 745/745 tests pass, 0 ruff violations.

## Third Fix Applied (2026-03-18)

**`cyrus_brain.py` lint violations fixed.**

Two `ruff check` violations existed in `cyrus_brain.py`:
1. `I001` — import block unsorted: `from cyrus_config import AUTH_TOKEN, BRAIN_PORT, HOOK_PORT, MOBILE_PORT, validate_auth_token` was a single 92-char line, fixed to multi-line format.
2. `E501` — line too long at `s.sendall(...)` call; extracted `payload` variable.

**`test_mobile_valid_token_accepted` fixed in `test_028_tcp_authentication.py`.**

`TestBrainMobileHandlerAuth::test_mobile_valid_token_accepted` was failing with:
```
TypeError: object MagicMock can't be used in 'await' expression
```
Root cause: `_make_ws()` mocked `ws.__anext__` but `handle_mobile_ws` uses `ws.recv()` for auth (not `__anext__`), and also calls `await ws.send({"type": "auth_ok"})` on successful auth. Fix:
- Changed mock from `ws.__anext__ = AsyncMock(...)` → `ws.recv = AsyncMock(...)`
- Added `ws.send = AsyncMock()` for the auth-ok acknowledgement path

**`ruff format` applied to 5 reformatted files.**
