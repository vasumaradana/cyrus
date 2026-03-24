---
id=028-Add-TCP-authentication-2
title=Add auth validation to all brain server connection handlers
state=COMPLETE
parent=028-Add-TCP-authentication
children=
split_count=0
force_split=false
needs_interview=false
verify_count=1
total_input_tokens=318019
total_output_tokens=106
total_duration_seconds=1001
total_iterations=5
run_count=5
---

# Add auth validation to all brain server connection handlers

## Parent
Issue 028: Add TCP Authentication

## Depends On
028-Add-TCP-authentication-1 (AUTH_TOKEN + validate_auth_token must exist in cyrus_config.py)

## Description
Add token validation to all three server-side connection handlers in `cyrus2/cyrus_brain.py`.
Unauthorized clients must be disconnected immediately with a generic error; mismatches must be
logged (not exposed to the client).

## Acceptance Criteria
- [x] `handle_voice_connection` (port 8766): reads first message as JSON, expects `{"type": "auth", "token": "..."}`, disconnects with `{"error": "unauthorized"}` on missing/wrong token
- [x] `handle_hook_connection` (port 8767): reads single JSON message, expects `"token"` key, disconnects with `{"error": "unauthorized"}` on missing/wrong token
- [x] `handle_mobile_ws` (port 8769): reads first WebSocket message as JSON, expects `{"type": "auth", "token": "..."}`, disconnects with `{"error": "unauthorized"}` on missing/wrong token
- [x] Token mismatch is logged at WARNING level (masked, not verbatim), not exposed in error response
- [x] Authorized connections proceed normally after auth
- [x] `uv run ruff check .` passes

## Auth Protocol

### Voice handler (port 8766) — raw TCP
```
client → brain:  {"type": "auth", "token": "<AUTH_TOKEN>"}\n
brain  → client: {"type": "auth_ok"}\n        # if valid
brain  → client: {"error": "unauthorized"}\n   # if invalid, then close
```

### Hook handler (port 8767) — raw TCP, single message per connection
```
client → brain:  {"event": "...", "token": "<AUTH_TOKEN>", ...}\n
# brain validates "token" key before dispatching event
# if invalid: {"error": "unauthorized"}\n then close
```

### Mobile WS handler (port 8769) — WebSocket
```
client → brain:  {"type": "auth", "token": "<AUTH_TOKEN>"}   (first WS message)
brain  → client: {"type": "auth_ok"}                          # if valid
brain  → client: {"error": "unauthorized"}                    # if invalid, then close
```

## Implementation Steps

1. In `handle_voice_connection`:
   - After accepting the connection, `await reader.readline()` for the first message
   - Parse JSON; validate token with `validate_auth_token()`
   - On failure: `writer.write(json.dumps({"error": "unauthorized"}).encode() + b"\n")`, log WARNING, close
   - On success: continue existing logic

2. In `handle_hook_connection`:
   - Parse the single incoming JSON message
   - Check `msg.get("token", "")` with `validate_auth_token()`
   - On failure: send error, log WARNING, close before dispatching
   - On success: dispatch as before (token key can be stripped before further processing)

3. In `handle_mobile_ws`:
   - Await the first WebSocket message
   - Parse JSON; validate token
   - On failure: `await ws.send_json({"error": "unauthorized"})`, log WARNING, close
   - On success: add client to broadcast set and continue

4. Import `validate_auth_token` from `cyrus_config` at top of file.

## Files to Modify
- `cyrus2/cyrus_brain.py` — auth validation in handle_voice_connection, handle_hook_connection, handle_mobile_ws

## Testing
Full auth tests covering brain behavior are in child issue 028-3.
After implementing, run `uv run pytest cyrus2/tests/` to check for regressions.

## Stage Log

### GROOMED — 2026-03-18 02:30:15Z

- **From:** NEW
- **Duration in stage:** 0s
- **Input tokens:** 64,644 (final context: 64,644)
- **Output tokens:** 4
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage

### PLANNED — 2026-03-18 02:34:04Z

- **From:** PLANNED
- **Duration in stage:** 280s
- **Input tokens:** 98,088 (final context: 98,088)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 49%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan

### PLANNED — 2026-03-18 02:34:32Z

- **From:** PLANNED
- **Duration in stage:** 120s
- **Input tokens:** 35,664 (final context: 35,664)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 18%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan

<!-- root-cause:072 -->

### STUCK — 2026-03-18 15:14:27Z

- **From:** STUCK
- **Duration in stage:** 328s
- **Input tokens:** 74,723 (final context: 74,723)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 37%
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

### COMPLETE — 2026-03-18 17:40:45Z

- **From:** BUILT
- **Duration in stage:** 0s
- **Input tokens:** 0 (final context: 0)
- **Output tokens:** 0
- **Iterations:** 0
- **Model:** 
- **Trigger:** auto/verify

### COMPLETE — 2026-03-18 17:40:45Z

- **From:** COMPLETE
- **Duration in stage:** 215s
- **Input tokens:** 44,900 (final context: 44,900)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 22%
- **Model:** claude-sonnet-4-6
- **Trigger:** manual/build
