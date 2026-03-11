---
id=028-Add-TCP-authentication
title=Issue 028: Add TCP Authentication
state=NEW
parent=
children=
split_count=0
force_split=false
verify_count=0
total_input_tokens=0
total_output_tokens=0
total_duration_seconds=0
total_iterations=0
run_count=0
---

# Issue 028: Add TCP Authentication

## Sprint
Sprint 4 — Configuration & Auth

## Priority
High

## References
- docs/15-recommendations.md — #3 (Authentication on TCP ports)
- docs/12-code-audit.md — L1 (Unencrypted localhost sockets)

## Description
Add shared-secret token authentication to all TCP server ports (8766, 8767, 8769, 8770). Clients must provide a token from `CYRUS_AUTH_TOKEN` env var or loaded from `.env` file. Validate on connection; reject unauthorized connections with an error message.

## Blocked By
- Issue 027 (centralized config module)

## Acceptance Criteria
- [ ] Token read from CYRUS_AUTH_TOKEN env var (or .env file via python-dotenv)
- [ ] Token generation helper (if token missing, suggest generating one)
- [ ] All server ports in cyrus2/cyrus_brain.py require token on connect
- [ ] cyrus2/cyrus_hook.py sends token in first message
- [ ] cyrus2/cyrus_voice.py sends token in first message
- [ ] Mobile client port (8769) validates token
- [ ] Companion registration port (8770) validates token
- [ ] Unauthorized clients disconnected immediately
- [ ] Token mismatch logged (not exposed in error message)

## Implementation Steps
1. Add to `cyrus2/cyrus_config.py`:
   ```python
   AUTH_TOKEN = os.environ.get("CYRUS_AUTH_TOKEN", "")
   if not AUTH_TOKEN:
       # Generate a random token on first run
       import secrets
       AUTH_TOKEN = secrets.token_hex(16)
       print(f"WARN: No CYRUS_AUTH_TOKEN set. Generated: {AUTH_TOKEN}")
       print(f"      Set CYRUS_AUTH_TOKEN={AUTH_TOKEN} in .env or shell")
   ```
2. Create auth validation helper in cyrus_config.py:
   ```python
   def validate_auth_token(received_token: str) -> bool:
       """Check if received token matches configured AUTH_TOKEN"""
       return received_token == AUTH_TOKEN
   ```
3. In cyrus2/cyrus_brain.py socket accept loops:
   - On new connection, read first line as JSON
   - Extract `{"token": "..."}` or `{"auth": "..."}`
   - Call `validate_auth_token()` — disconnect if invalid
   - Continue only if valid
4. In cyrus2/cyrus_hook.py `_send()`:
   ```python
   msg["token"] = AUTH_TOKEN
   ```
5. In cyrus2/cyrus_voice.py socket connections to brain:
   ```python
   # First message includes token
   {"token": AUTH_TOKEN, "event": "..."}
   ```
6. Add .env.example entry:
   ```
   # Authentication token for all TCP ports. Generate with: python -c "import secrets; print(secrets.token_hex(16))"
   CYRUS_AUTH_TOKEN=abc123def456...
   ```

## Files to Create/Modify
- Modify: `cyrus2/cyrus_config.py` (add AUTH_TOKEN, validate_auth_token helper)
- Modify: `cyrus2/cyrus_brain.py` (validate token on all server sockets)
- Modify: `cyrus2/cyrus_hook.py` (include token in _send)
- Modify: `cyrus2/cyrus_voice.py` (include token in brain connections)
- Update: `.env.example` (add CYRUS_AUTH_TOKEN)

## Testing
1. Start brain with CYRUS_AUTH_TOKEN=secret123
2. Attempt hook connection without token — verify disconnected
3. Attempt hook connection with wrong token — verify disconnected
4. Attempt hook connection with correct token — verify accepted
5. Test voice client with/without token
6. Test mobile client with/without token
7. Verify token mismatch logged in brain but not exposed to client

