---
id=028-Add-TCP-authentication-1
title=Add AUTH_TOKEN infrastructure to cyrus_config.py
state=COMPLETE
parent=028-Add-TCP-authentication
children=
split_count=0
force_split=false
needs_interview=false
verify_count=3
verify_exhausted=true
total_input_tokens=584436
total_output_tokens=232
total_duration_seconds=2709
total_iterations=10
run_count=10
---

# Add AUTH_TOKEN infrastructure to cyrus_config.py

## Parent
Issue 028: Add TCP Authentication

## Description
Add the shared-secret token infrastructure that all other 028 child issues depend on.
This is the foundational piece: the `AUTH_TOKEN` constant, the `validate_auth_token()`
helper, and the `.env.example` documentation entry.

## Acceptance Criteria
- [x] `AUTH_TOKEN` constant in `cyrus2/cyrus_config.py` reads from `CYRUS_AUTH_TOKEN` env var
- [x] If `CYRUS_AUTH_TOKEN` not set, auto-generate with `secrets.token_hex(16)` and print a WARN to stderr suggesting the user set it
- [x] `validate_auth_token(received: str) -> bool` helper uses `hmac.compare_digest` for constant-time comparison
- [x] Token never logged verbatim (masked in any log output)
- [x] `cyrus2/.env.example` has `CYRUS_AUTH_TOKEN=` entry with generation instructions
- [x] Existing `tests/test_027_cyrus_config.py` still passes (no regression)
- [x] `uv run ruff check .` passes

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

## Stage Log

### GROOMED — 2026-03-18 02:29:17Z

- **From:** NEW
- **Duration in stage:** 0s
- **Input tokens:** 55,778 (final context: 55,778)
- **Output tokens:** 5
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage

### PLANNED — 2026-03-18 02:31:36Z

- **From:** PLANNED
- **Duration in stage:** 170s
- **Input tokens:** 41,938 (final context: 41,938)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 21%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan

### PLANNED — 2026-03-18 02:32:32Z

- **From:** PLANNED
- **Duration in stage:** 136s
- **Input tokens:** 48,830 (final context: 48,830)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 24%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan

<!-- root-cause:069 -->

### STUCK — 2026-03-18 15:04:26Z

- **From:** STUCK
- **Duration in stage:** 110s
- **Input tokens:** 43,609 (final context: 43,609)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 22%
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

<!-- root-cause:070 -->

### STUCK — 2026-03-18 15:04:41Z

- **From:** STUCK
- **Duration in stage:** 262s
- **Input tokens:** 53,848 (final context: 53,848)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 27%
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

<!-- root-cause:071 -->

### STUCK — 2026-03-18 15:08:59Z

- **From:** STUCK
- **Duration in stage:** 176s
- **Input tokens:** 44,109 (final context: 44,109)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 22%
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

### BUILT — 2026-03-18

- **From:** STUCK
- **Trigger:** manual/build
- **Summary:** All acceptance criteria verified. Implementation complete in `cyrus_config.py` (AUTH_TOKEN + validate_auth_token), `cyrus_hook.py` (imports AUTH_TOKEN from cyrus_config), `.env.example` (CYRUS_AUTH_TOKEN documented). Fixed stale test assertion in `test_028_tcp_auth.py::test_hook_send_without_token_env` — test was expecting empty `""` token, but current implementation auto-generates via `secrets.token_hex(16)`. All 24/24 auth tests pass, 46/46 config tests pass, ruff clean.

### STUCK — 2026-03-18 15:10:12Z

- **From:** STUCK
- **Duration in stage:** 200s
- **Input tokens:** 54,212 (final context: 54,212)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 27%
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

### STUCK — 2026-03-18 15:12:41Z

- **From:** STUCK
- **Duration in stage:** 662s
- **Input tokens:** 99,608 (final context: 99,608)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 50%
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

### STUCK — 2026-03-18 15:13:33Z

- **From:** STUCK
- **Duration in stage:** 851s
- **Input tokens:** 121,048 (final context: 121,048)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 61%
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

### COMPLETE — 2026-03-18 17:37:14Z

- **From:** BUILT
- **Duration in stage:** 0s
- **Input tokens:** 0 (final context: 0)
- **Output tokens:** 0
- **Iterations:** 0
- **Model:** 
- **Trigger:** auto/verify

### COMPLETE — 2026-03-18 17:37:14Z

- **From:** COMPLETE
- **Duration in stage:** 64s
- **Input tokens:** 21,456 (final context: 21,456)
- **Output tokens:** 24
- **Iterations:** 1
- **Context used:** 11%
- **Model:** claude-sonnet-4-6
- **Trigger:** manual/build
