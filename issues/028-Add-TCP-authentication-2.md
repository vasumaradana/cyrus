---
id=028-Add-TCP-authentication-2
title=Add auth validation to all brain server connection handlers
state=NEW
parent=028-Add-TCP-authentication
children=
split_count=0
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
- [ ] `handle_voice_connection` (port 8766): reads first message as JSON, expects `{"type": "auth", "token": "..."}`, disconnects with `{"error": "unauthorized"}` on missing/wrong token
- [ ] `handle_hook_connection` (port 8767): reads single JSON message, expects `"token"` key, disconnects with `{"error": "unauthorized"}` on missing/wrong token
- [ ] `handle_mobile_ws` (port 8769): reads first WebSocket message as JSON, expects `{"type": "auth", "token": "..."}`, disconnects with `{"error": "unauthorized"}` on missing/wrong token
- [ ] Token mismatch is logged at WARNING level (masked, not verbatim), not exposed in error response
- [ ] Authorized connections proceed normally after auth
- [ ] `uv run ruff check .` passes

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
