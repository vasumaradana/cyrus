---
id=028-Add-TCP-authentication-3
title=Add client-side auth tokens and acceptance test suite
state=COMPLETE
parent=028-Add-TCP-authentication
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=483873
total_output_tokens=183
total_duration_seconds=1269
total_iterations=12
run_count=11
---

# Add client-side auth tokens and acceptance test suite

## Parent
Issue 028: Add TCP Authentication

## Depends On
- 028-Add-TCP-authentication-1 (AUTH_TOKEN must exist in cyrus_config.py)
- 028-Add-TCP-authentication-2 (brain handlers must validate tokens before client-side auth can be verified)

## Description
Add token-sending logic to the two client components (`cyrus_hook.py` and `cyrus_voice.py`),
then write the full acceptance test suite (`test_028_tcp_auth.py`) that verifies all 16
acceptance criteria from the parent issue plan.

## Acceptance Criteria

### Client-side changes
- [ ] `cyrus_hook.py._send()` merges `{"token": AUTH_TOKEN}` into every outgoing message dict
- [ ] `cyrus_voice.py.voice_loop()` sends `{"type": "auth", "token": AUTH_TOKEN}` as the first message after connecting to brain

### Test suite (16 tests in `cyrus2/tests/test_028_tcp_auth.py`)
- [ ] `test_auth_token_from_env` — AUTH_TOKEN matches CYRUS_AUTH_TOKEN env var when set
- [ ] `test_auth_token_generated_if_missing` — token auto-generated + WARN printed when env var absent
- [ ] `test_validate_token_correct` — validate_auth_token returns True on match
- [ ] `test_validate_token_wrong` — validate_auth_token returns False on mismatch
- [ ] `test_validate_uses_constant_time` — validate_auth_token uses hmac.compare_digest (not `==`)
- [ ] `test_hook_send_includes_token` — _send() merges token into outgoing dict
- [ ] `test_hook_send_without_token_env` — _send() still works (sends auto-generated token) when env var not set
- [ ] `test_brain_voice_rejects_no_token` — brain disconnects voice client that sends no token
- [ ] `test_brain_voice_rejects_wrong_token` — brain disconnects voice client with wrong token
- [ ] `test_brain_voice_accepts_correct_token` — brain accepts voice client with correct token
- [ ] `test_brain_hook_rejects_wrong_token` — brain disconnects hook with wrong token
- [ ] `test_brain_hook_accepts_correct_token` — brain accepts hook with correct token
- [ ] `test_brain_mobile_rejects_wrong_token` — brain disconnects mobile WS with wrong token
- [ ] `test_brain_mobile_accepts_correct_token` — brain accepts mobile WS with correct token
- [ ] `test_mismatch_logged_not_exposed` — token mismatch is logged but not sent to client
- [ ] `test_env_example_has_auth_token` — .env.example contains CYRUS_AUTH_TOKEN

### Verification
- [ ] All 16 acceptance tests pass
- [ ] All existing tests still pass (no regression in test_027_cyrus_config.py or others)
- [ ] `uv run ruff check .` passes
- [ ] Token never logged verbatim in any test output

## Implementation Steps

### 1. cyrus_hook.py — add token to _send()
```python
# In _send(), before json.dumps:
from cyrus2.cyrus_config import AUTH_TOKEN
msg["token"] = AUTH_TOKEN
```

### 2. cyrus_voice.py — send auth handshake first
```python
# In voice_loop(), immediately after connecting:
from cyrus2.cyrus_config import AUTH_TOKEN
writer.write(json.dumps({"type": "auth", "token": AUTH_TOKEN}).encode() + b"\n")
await writer.drain()
# Then read {"type": "auth_ok"} before proceeding
```

### 3. cyrus2/tests/test_028_tcp_auth.py
Use `importlib.reload` or monkeypatching to test token-from-env and token-generation
behaviors without polluting the module cache. For brain integration tests, spin up
asyncio servers with `asyncio.start_server` on ephemeral ports (port=0) and connect
test clients.

Key testing patterns:
- Patch `cyrus2.cyrus_config.AUTH_TOKEN` directly for brain validation tests
- Use `asyncio.open_connection` for TCP tests against the brain handlers
- Use `aiohttp.ClientSession().ws_connect()` or `websockets.connect()` for mobile WS tests
- Assert `{"error": "unauthorized"}` received before connection closes
- Assert `{"type": "auth_ok"}` received after valid auth
- Capture `logging.WARNING` records to verify mismatch logging

## Files to Create/Modify
- `cyrus2/cyrus_hook.py` — add `msg["token"] = AUTH_TOKEN` in `_send()`
- `cyrus2/cyrus_voice.py` — send auth message first in `voice_loop()`
- `cyrus2/tests/test_028_tcp_auth.py` — **new file**, all 16 acceptance tests

## Stage Log

### NEW — 2026-03-18 02:34:24Z

- **From:** NEW
- **Duration in stage:** 176s
- **Input tokens:** 66,817 (final context: 66,817)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 33%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan

### NEW — 2026-03-18 02:34:45Z

- **From:** NEW
- **Duration in stage:** 41s
- **Input tokens:** 23,930 (final context: 23,930)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 12%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan

### NEW — 2026-03-18 02:35:15Z

- **From:** NEW
- **Duration in stage:** 218s
- **Input tokens:** 52,130 (final context: 52,130)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 26%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan

### GROOMED — 2026-03-18 14:41:14Z

- **From:** NEW
- **Duration in stage:** 0s
- **Input tokens:** 50,319 (final context: 50,319)
- **Output tokens:** 7
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage

### PLANNED — 2026-03-18 14:46:36Z

- **From:** PLANNED
- **Duration in stage:** 322s
- **Input tokens:** 77,790 (final context: 77,790)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 39%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan

### PLANNED — 2026-03-18 14:50:30Z

- **From:** PLANNED
- **Duration in stage:** 299s
- **Input tokens:** 122,482 (final context: 122,482)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 61%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan

### PLANNED — 2026-03-18 15:47:11Z

- **From:** PLANNED
- **Duration in stage:** 4s
- **Input tokens:** 19,123 (final context: 19,123)
- **Output tokens:** 8
- **Iterations:** 1
- **Context used:** 10%
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

### PLANNED — 2026-03-18 15:47:17Z

- **From:** PLANNED
- **Duration in stage:** 1s
- **Input tokens:** 0 (final context: 0)
- **Output tokens:** 0
- **Iterations:** 1
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

### PLANNED — 2026-03-18 16:21:22Z

- **From:** PLANNED
- **Duration in stage:** 0s
- **Input tokens:** 0 (final context: 0)
- **Output tokens:** 0
- **Iterations:** 1
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

### PLANNED — 2026-03-18 16:21:50Z

- **From:** PLANNED
- **Duration in stage:** 0s
- **Input tokens:** 0 (final context: 0)
- **Output tokens:** 0
- **Iterations:** 1
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

### COMPLETE — 2026-03-18 17:06:00Z

- **From:** BUILT
- **Duration in stage:** 0s
- **Input tokens:** 0 (final context: 0)
- **Output tokens:** 0
- **Iterations:** 0
- **Model:** 
- **Trigger:** auto/verify

### COMPLETE — 2026-03-18 17:06:00Z

- **From:** COMPLETE
- **Duration in stage:** 113s
- **Input tokens:** 71,282 (final context: 29,512)
- **Output tokens:** 38
- **Iterations:** 2
- **Context used:** 15%
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build
