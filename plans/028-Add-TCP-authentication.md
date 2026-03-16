# Plan 028: Add TCP Authentication

## Summary

Add shared-secret token authentication to all active TCP/WebSocket server ports in cyrus_brain.py (8766, 8767, 8769). Token is read from `CYRUS_AUTH_TOKEN` env var. When set, every inbound connection must present the token before the server processes any messages. When unset, auth is disabled (backward compatible). A new `cyrus2/cyrus_auth.py` module centralizes token loading and validation. Client files (`cyrus_hook.py`, `cyrus_voice.py`) include the token in outgoing connections.

## Dependencies

- **Issue 027 (centralized config)** — PLANNED, not yet BUILT. `cyrus2/cyrus_config.py` does not exist. This plan creates a **separate** `cyrus2/cyrus_auth.py` module that does not conflict with 027. When 027 lands, AUTH_TOKEN can be absorbed into ConfigManager.
- **Plan 018 (pytest framework)** — not yet BUILT. No test framework exists. This plan includes a standalone verification test script (`cyrus2/test_cyrus_auth.py`) that runs without pytest.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| Token from CYRUS_AUTH_TOKEN env var | Not read anywhere | Create `cyrus2/cyrus_auth.py` |
| Token generation helper | Does not exist | Add `generate_token()` + startup warning |
| Brain validates token on port 8766 | No auth in `handle_voice_connection()` | Add auth handshake read |
| Brain validates token on port 8767 | No auth in `handle_hook_connection()` | Extract + validate token field |
| Brain validates token on port 8769 | No auth in `handle_mobile_ws()` | First-message auth |
| Hook sends token | `_send()` sends bare message | Add token field to message dict |
| Voice sends token | Sends utterances immediately | Send auth message first after connect |
| Companion port 8770 | Not implemented (Brain is client, not server) | Document requirement only — no code |
| Token mismatch logged | No logging | Add `print()` on mismatch (logging framework not yet available) |
| Token not exposed in error | N/A | Error message says "unauthorized" only |
| `.env.example` documents token | Only has `ANTHROPIC_API_KEY=` | Add `CYRUS_AUTH_TOKEN=` entry |

## Key Findings from Codebase Exploration

### Port inventory (5 ports, 4 active)

| Port | Server | Protocol | Handler | Auth Scope |
|---|---|---|---|---|
| 8766 | `cyrus_brain.py` | TCP, line-delimited JSON | `handle_voice_connection()` :1655 | **In scope** — long-lived, first-message auth |
| 8767 | `cyrus_brain.py` | TCP, single-message JSON | `handle_hook_connection()` :1563 | **In scope** — one-shot, token-in-message |
| 8769 | `cyrus_brain.py` | WebSocket, JSON | `handle_mobile_ws()` :1388 | **In scope** — persistent, first-message auth |
| 8765 | `cyrus_server.py` | WebSocket, JSON | `handle_client()` :102 | **Not in issue scope** (separate service) |
| 8770 | — | Not implemented | — | **Documented only** — Brain connects *to* companion extension as client; no server exists |

### Protocol details

**Hook (8767)**: Each connection sends exactly one JSON line, then disconnects. Message format: `{"event": "...", ...}\n`. Adding `"token"` as a field requires zero protocol changes — it's just an additional key in the same dict.

**Voice (8766)**: Long-lived TCP connection. Voice → Brain messages: `{"type": "utterance|tts_start|tts_end", ...}\n`. Brain → Voice messages: `{"type": "speak|chime|...", ...}\n`. Auth is a new first message `{"type": "auth", "token": "..."}\n` sent by voice immediately after `open_connection()`. Brain reads this before entering the normal `voice_reader()` loop.

**Mobile (8769)**: WebSocket. Mobile → Brain messages: `{"type": "utterance|ping", ...}`. Auth is a new first message `{"type": "auth", "token": "..."}` sent by mobile client immediately after connect. Brain validates before entering the normal `async for` loop.

### Hook import constraints

`cyrus_hook.py` runs from Claude Code's working directory (the project being edited, NOT the cyrus repo), so `sys.path` does not include the cyrus directory. It **cannot** import from `cyrus2/`. The hook must read `CYRUS_AUTH_TOKEN` directly from `os.environ` — no new dependencies, no new imports beyond stdlib.

### python-dotenv convention

Following Plan 027's decision: auth module does NOT call `load_dotenv()`. Entry-point scripts that want `.env` support call it themselves. `cyrus_hook.py` must remain dependency-free (a crashing hook blocks Claude Code).

## Design Decisions

### D1. Separate `cyrus2/cyrus_auth.py` — does not conflict with Plan 027

Plan 027 owns `cyrus2/cyrus_config.py` with port/timeout/threshold config. Auth is a distinct concern (secrets, validation, token generation). Creating `cyrus_auth.py` avoids merge conflicts. When 027 lands, the AUTH_TOKEN constant can optionally migrate to ConfigManager, or the config module can re-export it.

### D2. Auth disabled when CYRUS_AUTH_TOKEN unset (backward compatible)

If the env var is empty or missing, all connections are accepted with a startup warning. This prevents breaking existing deployments. The token generation helper prints a suggested command and the generated value, but does not auto-enforce it.

**Rationale**: The issue's step 1 shows auto-generating a token at runtime, but this creates a chicken-and-egg problem — clients (hook, voice) wouldn't know the generated token. Disabling auth when unset + printing a warning is more practical.

### D3. Constant-time comparison via `hmac.compare_digest`

Prevents timing side-channel attacks. Even on localhost, this is good security practice and costs nothing.

### D4. Token-in-message for hooks, first-message auth for persistent connections

- **Hook (8767)**: Token added as field in the existing single-message dict. No protocol change, no extra round-trip.
- **Voice (8766)**: Dedicated `{"type": "auth", "token": "..."}` first message. Clean separation from application protocol.
- **Mobile (8769)**: Same first-message auth pattern as voice.

### D5. Hook reads from os.environ directly (no imports from cyrus2/)

The hook runs in a foreign CWD. It can only rely on stdlib + environment variables. `os.environ.get("CYRUS_AUTH_TOKEN", "")` is the only safe approach.

### D6. Port 8770 (companion) documented but not implemented

The companion feature doesn't exist in code. The Brain acts as a TCP *client* connecting to the VS Code extension — there is no server listening on 8770. The auth requirement is documented for when the companion feature lands.

### D7. Port 8765 (cyrus_server.py) not in scope

The issue specifies ports 8766, 8767, 8769, 8770. Port 8765 is a separate remote brain service. Noted here for future work.

## Acceptance Criteria → Test Mapping

| AC | Test |
|---|---|
| Token read from CYRUS_AUTH_TOKEN env var | Unit: `test_token_loaded_from_env` |
| Token generation helper | Unit: `test_generate_token_format` |
| All server ports require token on connect | Integration: connect without token → rejected |
| Hook sends token in first message | Unit: verify token field in message dict |
| Voice sends token in first message | Integration: voice connects, first line is auth |
| Mobile port validates token | Integration: WebSocket auth handshake |
| Unauthorized clients disconnected | Integration: wrong token → connection closed |
| Token mismatch logged (not exposed) | Unit: `test_validation_rejects_wrong_token`; Integration: verify log output |

## Implementation Steps

### Step 1 — RED: Write auth module tests

**File**: `cyrus2/test_cyrus_auth.py` (standalone, no pytest required)

Tests to write (all use `assert` + `os.environ` manipulation):
1. `test_token_loaded_from_env` — set env var, reimport module, assert AUTH_TOKEN matches
2. `test_auth_disabled_when_unset` — unset env var, assert `auth_enabled()` returns False
3. `test_auth_enabled_when_set` — set env var, assert `auth_enabled()` returns True
4. `test_validate_correct_token` — assert `validate_auth_token("secret")` returns True when AUTH_TOKEN="secret"
5. `test_validate_wrong_token` — assert returns False
6. `test_validate_empty_token` — assert returns False when auth enabled
7. `test_validate_when_disabled` — assert returns True for any input when auth disabled
8. `test_generate_token_format` — assert `generate_token()` returns 32-char hex string
9. `test_generate_token_unique` — assert two calls produce different tokens

**Run**: `python cyrus2/test_cyrus_auth.py` → expect ImportError (module doesn't exist yet)

### Step 2 — GREEN: Create auth module

**File**: `cyrus2/cyrus_auth.py`

```python
"""
cyrus_auth.py — Shared-secret token authentication for TCP/WebSocket ports.

Token is read from CYRUS_AUTH_TOKEN environment variable.
When unset, authentication is disabled (all connections accepted).
"""
import hmac
import os
import secrets

AUTH_TOKEN: str = os.environ.get("CYRUS_AUTH_TOKEN", "")


def auth_enabled() -> bool:
    """True when a non-empty auth token is configured."""
    return bool(AUTH_TOKEN)


def validate_auth_token(received: str) -> bool:
    """Constant-time comparison of received token against configured token.
    Returns True if auth is disabled (no token set) or token matches."""
    if not AUTH_TOKEN:
        return True
    if not received:
        return False
    return hmac.compare_digest(received, AUTH_TOKEN)


def generate_token() -> str:
    """Generate a random 32-character hex token (128 bits)."""
    return secrets.token_hex(16)


def print_auth_status(service: str) -> None:
    """Print auth status at service startup."""
    if AUTH_TOKEN:
        print(f"[{service}] Auth enabled — CYRUS_AUTH_TOKEN loaded")
    else:
        print(f"[{service}] WARNING: CYRUS_AUTH_TOKEN not set — auth disabled")
        print(f"[{service}]   Generate one: python -c \"import secrets; print(secrets.token_hex(16))\"")
        print(f"[{service}]   Then set: CYRUS_AUTH_TOKEN=<token> in .env or shell")
```

**Run**: `python cyrus2/test_cyrus_auth.py` → all tests pass

### Step 3 — Modify `cyrus_brain.py`: import auth module + startup message

**File**: `cyrus_brain.py`

**Changes**:
1. Add import at top (after existing imports, in the Configuration section):
   ```python
   from cyrus2.cyrus_auth import AUTH_TOKEN, auth_enabled, validate_auth_token, print_auth_status
   ```
2. In `main()`, after argument parsing (~line 1702), add:
   ```python
   print_auth_status("Brain")
   ```

### Step 4 — Modify `cyrus_brain.py`: auth in `handle_hook_connection()`

**File**: `cyrus_brain.py`, function `handle_hook_connection()` (line 1563)

**Change**: After parsing the JSON message (line 1574), before processing the event, extract and validate the token:

```python
# After: msg = json.loads(raw.decode().strip())
# Before: event = msg.get("event", "stop")

# ── Auth check ──
if auth_enabled():
    token = msg.get("token", "")
    if not validate_auth_token(token):
        addr = writer.get_extra_info("peername")
        print(f"[Brain] Hook connection rejected — invalid token from {addr}")
        return
```

The `finally` block already closes the writer, so returning is safe.

### Step 5 — Modify `cyrus_brain.py`: auth in `handle_voice_connection()`

**File**: `cyrus_brain.py`, function `handle_voice_connection()` (line 1655)

**Change**: After setting `_voice_writer` and printing the connection message, before the greeting, read and validate the auth handshake:

```python
# After: print(f"[Brain] Voice service connected from {addr}")
# Before: _voice_writer = writer

# ── Auth handshake ──
if auth_enabled():
    try:
        auth_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not auth_line:
            print(f"[Brain] Voice connection rejected — no auth message from {addr}")
            return
        auth_msg = json.loads(auth_line.decode().strip())
        token = auth_msg.get("token", "")
        if not validate_auth_token(token):
            print(f"[Brain] Voice connection rejected — invalid token from {addr}")
            return
    except (asyncio.TimeoutError, json.JSONDecodeError) as e:
        print(f"[Brain] Voice auth failed from {addr}: {e}")
        return

_voice_writer = writer
```

**Important**: Move `_voice_writer = writer` to AFTER auth succeeds. Otherwise, a rejected connection would leave a stale writer reference. Add cleanup in the rejection paths (close writer).

### Step 6 — Modify `cyrus_brain.py`: auth in `handle_mobile_ws()`

**File**: `cyrus_brain.py`, function `handle_mobile_ws()` (line 1388)

**Change**: Before adding to `_mobile_clients` and before the `async for` loop, wait for and validate the auth message:

```python
async def handle_mobile_ws(ws) -> None:
    """Handle a single mobile WebSocket client."""
    addr = ws.remote_address

    # ── Auth handshake ──
    if auth_enabled():
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            auth_msg = json.loads(raw)
            token = auth_msg.get("token", "")
            if not validate_auth_token(token):
                print(f"[Brain] Mobile client rejected — invalid token from {addr}")
                await ws.close(4001, "Unauthorized")
                return
        except (asyncio.TimeoutError, json.JSONDecodeError) as e:
            print(f"[Brain] Mobile auth failed from {addr}: {e}")
            await ws.close(4001, "Unauthorized")
            return

    _mobile_clients.add(ws)
    print(f"[Brain] Mobile client connected: {addr}")
    # ... rest unchanged
```

**Note**: Move `_mobile_clients.add(ws)` to after auth succeeds. Update the `finally` block to only `discard` if ws was added.

### Step 7 — Modify `cyrus_hook.py`: include token in messages

**File**: `cyrus_hook.py`

**Changes**:
1. At module level (after `BRAIN_PORT = 8767`), add:
   ```python
   _AUTH_TOKEN = os.environ.get("CYRUS_AUTH_TOKEN", "")
   ```
   Note: uses `os` which is already imported. No new imports needed.

2. In `_send()`, add token to message dict before sending:
   ```python
   def _send(msg: dict) -> None:
       try:
           if _AUTH_TOKEN:
               msg["token"] = _AUTH_TOKEN
           with socket.create_connection((BRAIN_HOST, BRAIN_PORT), timeout=2) as s:
               s.sendall((json.dumps(msg) + "\n").encode())
       except Exception:
           pass   # Brain not running — silent, never block Claude
   ```

**Design note**: Token is only added when non-empty, keeping messages clean when auth is disabled. The `os` import already exists at line 11.

### Step 8 — Modify `cyrus_voice.py`: send auth on connect

**File**: `cyrus_voice.py`

**Changes**:
1. At module level (after existing imports), add:
   ```python
   _AUTH_TOKEN = os.environ.get("CYRUS_AUTH_TOKEN", "")
   ```
   Note: `os` is already imported at line 23.

2. In `main()`, in the connect loop (after `reader, writer = await asyncio.open_connection(...)` at line 534), send auth message before entering `voice_loop`:
   ```python
   reader, writer = await asyncio.open_connection(args.host, args.port)
   print("[Voice] Connected to brain.")

   # ── Auth handshake ──
   if _AUTH_TOKEN:
       auth_msg = json.dumps({"type": "auth", "token": _AUTH_TOKEN}) + "\n"
       writer.write(auth_msg.encode())
       await writer.drain()

   try:
       await voice_loop(whisper_model, reader, writer, loop)
   ```

3. In `main()`, after argument parsing, add auth status print:
   ```python
   if _AUTH_TOKEN:
       print("[Voice] Auth token loaded")
   else:
       print("[Voice] WARNING: No CYRUS_AUTH_TOKEN — connections will not be authenticated")
   ```

### Step 9 — Update `.env.example`

**File**: `.env.example`

Append:
```
# Authentication token for all TCP/WebSocket ports.
# Generate: python -c "import secrets; print(secrets.token_hex(16))"
# When unset, auth is disabled and all connections are accepted.
CYRUS_AUTH_TOKEN=
```

### Step 10 — Manual integration test

Run the following manual verification sequence:

1. **Auth disabled (default)**:
   - Start brain WITHOUT `CYRUS_AUTH_TOKEN` → verify warning printed
   - Start voice → verify connects normally
   - Run hook event → verify processed normally

2. **Auth enabled, correct token**:
   - `export CYRUS_AUTH_TOKEN=test_secret_123`
   - Start brain → verify "Auth enabled" printed
   - Start voice → verify auth handshake succeeds, connects normally
   - Run hook event → verify processed normally

3. **Auth enabled, wrong token on hook**:
   - Brain: `CYRUS_AUTH_TOKEN=correct_token`
   - Hook: `CYRUS_AUTH_TOKEN=wrong_token`
   - Run hook event → verify Brain logs "rejected — invalid token", event NOT processed

4. **Auth enabled, no token on client**:
   - Brain: `CYRUS_AUTH_TOKEN=correct_token`
   - Voice/Hook: unset `CYRUS_AUTH_TOKEN`
   - Connect → verify rejected/disconnected

5. **Token mismatch not exposed**:
   - Verify rejected connection error message says "Unauthorized" only, not the expected token

## Files to Create/Modify

| File | Action | What Changes |
|---|---|---|
| `cyrus2/cyrus_auth.py` | **Create** | Auth token loading, validation, generation helper |
| `cyrus2/test_cyrus_auth.py` | **Create** | Standalone unit tests for auth module |
| `cyrus_brain.py` | **Modify** | Import auth, validate on all 3 handlers, startup message |
| `cyrus_hook.py` | **Modify** | Read token from env, add to message dict |
| `cyrus_voice.py` | **Modify** | Read token from env, send auth first message |
| `.env.example` | **Modify** | Add CYRUS_AUTH_TOKEN entry |

## Notes for Future Work

- **Port 8770 (companion)**: When companion registration server is implemented, apply the same first-message auth pattern used for voice (port 8766).
- **Port 8765 (cyrus_server.py)**: Not in this issue's scope but should get the same treatment. Recommend a follow-up issue.
- **Migration to Plan 027**: When `cyrus2/cyrus_config.py` lands, AUTH_TOKEN can optionally move to ConfigManager. The `cyrus_auth.py` module can then re-export from config, or remain as a thin wrapper with the validation logic.
- **TLS**: Authentication without encryption protects against accidental connections but not eavesdropping. The code audit (docs/12-code-audit.md, L1) notes this as acceptable for localhost. If brain is ever exposed beyond localhost, TLS should be added.
