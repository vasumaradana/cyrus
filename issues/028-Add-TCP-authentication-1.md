---
id=028-Add-TCP-authentication-1
title=Add AUTH_TOKEN infrastructure to cyrus_config.py
state=NEW
parent=028-Add-TCP-authentication
children=
split_count=0
---

# Add AUTH_TOKEN infrastructure to cyrus_config.py

## Parent
Issue 028: Add TCP Authentication

## Description
Add the shared-secret token infrastructure that all other 028 child issues depend on.
This is the foundational piece: the `AUTH_TOKEN` constant, the `validate_auth_token()`
helper, and the `.env.example` documentation entry.

## Acceptance Criteria
- [ ] `AUTH_TOKEN` constant in `cyrus2/cyrus_config.py` reads from `CYRUS_AUTH_TOKEN` env var
- [ ] If `CYRUS_AUTH_TOKEN` not set, auto-generate with `secrets.token_hex(16)` and print a WARN to stderr suggesting the user set it
- [ ] `validate_auth_token(received: str) -> bool` helper uses `hmac.compare_digest` for constant-time comparison
- [ ] Token never logged verbatim (masked in any log output)
- [ ] `cyrus2/.env.example` has `CYRUS_AUTH_TOKEN=` entry with generation instructions
- [ ] Existing `tests/test_027_cyrus_config.py` still passes (no regression)
- [ ] `uv run ruff check .` passes

## Implementation Steps

1. Edit `cyrus2/cyrus_config.py` — after existing config constants, add:
   ```python
   import hmac
   import secrets
   import sys

   # --- Authentication ---
   AUTH_TOKEN: str = os.environ.get("CYRUS_AUTH_TOKEN", "")
   if not AUTH_TOKEN:
       AUTH_TOKEN = secrets.token_hex(16)
       print(
           f"WARN: No CYRUS_AUTH_TOKEN set. Generated a temporary token.\n"
           f"      Set CYRUS_AUTH_TOKEN={AUTH_TOKEN} in .env or your shell to persist it.",
           file=sys.stderr,
       )


   def validate_auth_token(received: str) -> bool:
       """Constant-time comparison to prevent timing attacks."""
       return hmac.compare_digest(received, AUTH_TOKEN)
   ```

2. Edit `cyrus2/.env.example` — add:
   ```
   # Shared-secret token for all TCP ports (8766, 8767, 8769, 8770).
   # Generate with: python -c "import secrets; print(secrets.token_hex(16))"
   CYRUS_AUTH_TOKEN=
   ```

## Files to Modify
- `cyrus2/cyrus_config.py` — add AUTH_TOKEN constant + validate_auth_token() helper
- `cyrus2/.env.example` — add CYRUS_AUTH_TOKEN documentation entry

## Testing
Run `uv run pytest cyrus2/tests/test_027_cyrus_config.py` to confirm no regression.
Full auth tests are in child issue 028-3.
