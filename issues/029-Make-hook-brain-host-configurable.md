---
id=029-Make-hook-brain-host-configurable
title=Issue 029: Make Hook Brain Host Configurable
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=37588
total_output_tokens=4
total_duration_seconds=64
total_iterations=1
run_count=1
---

# Issue 029: Make Hook Brain Host Configurable

## Sprint
Sprint 4 — Configuration & Auth

## Priority
Medium

## References
- docs/13-docker-containerization.md — Phase 5

## Description
Allow `cyrus_hook.py` to connect to a brain running on a different host via `CYRUS_BRAIN_HOST` environment variable. Default to `localhost` for backward compatibility. Enables Docker deployment where brain runs in container and hook runs on host.

## Blocked By
- None

## Acceptance Criteria
- [ ] `CYRUS_BRAIN_HOST` env var read in cyrus2/cyrus_hook.py
- [ ] Defaults to `localhost` if not set
- [ ] Hook connects to `{CYRUS_BRAIN_HOST}:8767` (or CYRUS_HOOK_PORT)
- [ ] Socket timeout respected during connection
- [ ] Documented in .env.example

## Implementation Steps
1. Modify `cyrus2/cyrus_hook.py`:
   ```python
   BRAIN_HOST = os.environ.get("CYRUS_BRAIN_HOST", "localhost")
   BRAIN_PORT = int(os.environ.get("CYRUS_HOOK_PORT", "8767"))  # From config module

   def _send(msg: dict) -> None:
       try:
           with socket.create_connection((BRAIN_HOST, BRAIN_PORT), timeout=2) as s:
               s.sendall((json.dumps(msg) + "\n").encode())
       except Exception:
           pass
   ```
2. Update .env.example:
   ```
   # Brain host for hook connections. Set to Docker container hostname/IP for remote brain.
   CYRUS_BRAIN_HOST=localhost
   ```
3. Verify hook still works when brain is on same host (default case)

## Files to Create/Modify
- Modify: `cyrus2/cyrus_hook.py` (add CYRUS_BRAIN_HOST env var read)
- Update: `.env.example` (document CYRUS_BRAIN_HOST)

## Testing
1. Start brain on localhost, hook with default CYRUS_BRAIN_HOST — verify connection works
2. Start brain on 127.0.0.1, set CYRUS_BRAIN_HOST=127.0.0.1 — verify connection works
3. Set CYRUS_BRAIN_HOST=invalid.host — verify graceful failure (silent, doesn't block Claude Code)
4. With Docker, set CYRUS_BRAIN_HOST=host.docker.internal — verify hook on host connects to container brain

## Stage Log

### GROOMED — 2026-03-11 18:46:04Z

- **From:** NEW
- **Duration in stage:** 64s
- **Input tokens:** 37,588 (final context: 37,588)
- **Output tokens:** 4
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
