# Plan: Issue 028 — Add TCP Authentication

## Gap Analysis

### What Exists
- `cyrus2/cyrus_config.py` — centralized config (plan 027 complete), all ports defined, no AUTH_TOKEN
- `cyrus2/cyrus_brain.py` — 3 TCP/WS servers (8766 voice, 8767 hook, 8769 mobile); no auth
- `cyrus2/cyrus_hook.py` — sends one JSON message per hook event; no token included
- `cyrus2/cyrus_voice.py` — connects to brain on 8766; sends utterances; no auth handshake
- `cyrus2/.env.example` — documents CYRUS_* vars; no CYRUS_AUTH_TOKEN entry
- `cyrus2/tests/test_027_cyrus_config.py` — tests for config module (all passing)

### What Needs Building
1. `AUTH_TOKEN` constant + `validate_auth_token()` helper in `cyrus_config.py`
2. Token generation warning if `CYRUS_AUTH_TOKEN` not set
3. Auth validation on all 3 brain servers (voice, hook, mobile WS)
4. Token inclusion in hook messages (`cyrus_hook.py._send()`)
5. Token auth handshake when voice connects (`cyrus_voice.py.voice_loop()`)
6. `CYRUS_AUTH_TOKEN` entry in `.env.example`
7. Test file `tests/test_028_tcp_auth.py`

## Prioritized Tasks

- [x] Write acceptance-driven tests first (TDD)
- [x] Add `AUTH_TOKEN` + `validate_auth_token()` to `cyrus_config.py`
- [x] Update `cyrus2/.env.example` with `CYRUS_AUTH_TOKEN`
- [x] Add auth validation in `handle_voice_connection` (brain, port 8766)
- [x] Add auth validation in `handle_hook_connection` (brain, port 8767)
- [x] Add auth validation in `handle_mobile_ws` (brain, port 8769)
- [x] Add token to `_send()` in `cyrus_hook.py`
- [x] Add token auth handshake in `voice_loop()` in `cyrus_voice.py`

## Auth Protocol Design

### Token in first message (brain server side)
- **Voice (8766)**: Voice client sends `{"type": "auth", "token": "..."}` as first message. Brain validates and proceeds or disconnects.
- **Hook (8767)**: Hook includes `"token": AUTH_TOKEN` in its single JSON message. Brain validates before dispatching.
- **Mobile WS (8769)**: Mobile client sends `{"type": "auth", "token": "..."}` as first WebSocket message. Brain validates before adding to broadcast set.

### Token in outgoing messages (client side)
- `cyrus_hook.py._send()`: merges `{"token": AUTH_TOKEN}` into every message dict
- `cyrus_voice.py.voice_loop()`: sends `{"type": "auth", "token": AUTH_TOKEN}` immediately after connecting

### Missing token behavior
- If `CYRUS_AUTH_TOKEN` env var not set → auto-generate with `secrets.token_hex(16)`, print WARN to stderr suggesting user set it. This makes auth fail for any client that also didn't get the same env var, forcing explicit configuration.
- Token mismatch: logged at WARNING (not exposed to client). Client receives generic error `{"error": "unauthorized"}` then connection closed.

## Acceptance-Driven Tests

| # | Acceptance Criterion | Test Name |
|---|---------------------|-----------|
| 1 | AUTH_TOKEN read from CYRUS_AUTH_TOKEN env | `test_auth_token_from_env` |
| 2 | Token generation if missing (with WARN) | `test_auth_token_generated_if_missing` |
| 3 | validate_auth_token returns True on match | `test_validate_token_correct` |
| 4 | validate_auth_token returns False on mismatch | `test_validate_token_wrong` |
| 5 | validate_auth_token constant-time (hmac) | `test_validate_uses_constant_time` |
| 6 | Hook _send includes token | `test_hook_send_includes_token` |
| 7 | Hook _send with no token env still sends | `test_hook_send_without_token_env` |
| 8 | Brain disconnects voice on missing token | `test_brain_voice_rejects_no_token` |
| 9 | Brain disconnects voice on wrong token | `test_brain_voice_rejects_wrong_token` |
| 10 | Brain accepts voice with correct token | `test_brain_voice_accepts_correct_token` |
| 11 | Brain disconnects hook on wrong token | `test_brain_hook_rejects_wrong_token` |
| 12 | Brain accepts hook with correct token | `test_brain_hook_accepts_correct_token` |
| 13 | Brain disconnects mobile on wrong token | `test_brain_mobile_rejects_wrong_token` |
| 14 | Brain accepts mobile with correct token | `test_brain_mobile_accepts_correct_token` |
| 15 | Token mismatch logged, not exposed | `test_mismatch_logged_not_exposed` |
| 16 | .env.example has CYRUS_AUTH_TOKEN | `test_env_example_has_auth_token` |

## Files to Create/Modify

| File | Action |
|------|--------|
| `cyrus2/cyrus_config.py` | Add AUTH_TOKEN, validate_auth_token() |
| `cyrus2/cyrus_brain.py` | Add auth in handle_voice_connection, handle_hook_connection, handle_mobile_ws |
| `cyrus2/cyrus_hook.py` | Add token to _send() |
| `cyrus2/cyrus_voice.py` | Send auth message first in voice_loop() |
| `cyrus2/.env.example` | Add CYRUS_AUTH_TOKEN |
| `cyrus2/tests/test_028_tcp_auth.py` | New acceptance test file |

## Verification Checklist

- [ ] All 16 acceptance-driven tests pass
- [ ] Existing test_027_cyrus_config.py still passes (no regression)
- [ ] All other existing tests still pass
- [ ] `uv run ruff check .` passes
- [ ] Token never logged verbatim (only masked in mismatch logs)
- [ ] AUTH_TOKEN not in any repr/str output that could end up in logs

## Open Questions

None — issue is clear on implementation approach.
