---
id=012-Replace-prints-in-cyrus-server
title=Issue 012: Replace print() calls in cyrus_server.py
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=34451
total_output_tokens=3
total_duration_seconds=31
total_iterations=1
run_count=1
---

# Issue 012: Replace print() calls in cyrus_server.py

## Sprint
Sprint 2 — Quality & Safety

## Priority
High

## References
- docs/16-logging-system.md — Print-to-log conversion rules, Per-file changes section

## Description
Replace all 4 `print()` calls in `cyrus2/cyrus_server.py` with logging calls. Add `from cyrus2.cyrus_log import setup_logging` at the top and call it once in startup/entry code.

## Blocked By
- Issue 009 — Create cyrus_log module

## Acceptance Criteria
- [ ] All 4 `print()` calls replaced with `log.*()` equivalents
- [ ] `from cyrus2.cyrus_log import setup_logging` added at module top
- [ ] `import logging` added (if not present)
- [ ] `log = logging.getLogger("cyrus.server")` defined after imports
- [ ] `setup_logging("cyrus")` called once at startup (before any logging)
- [ ] Server lifecycle events (starting, listening) → `log.info()`
- [ ] Error/exception patterns → `log.error()`
- [ ] Debug patterns → `log.debug()`
- [ ] All f-strings converted to `%s` style logging
- [ ] File still has same functionality; only logging mechanism changed
- [ ] No new print() calls introduced

## Implementation Steps
1. Add imports at top of `cyrus2/cyrus_server.py`:
   ```python
   import logging
   from cyrus2.cyrus_log import setup_logging
   ```
2. Add logger definition after imports:
   ```python
   log = logging.getLogger("cyrus.server")
   ```
3. Identify startup/entry point (typically `main()` or module-level startup code)
4. Add `setup_logging("cyrus")` as first line of entry point
5. Replace all 4 print() calls:
   - Server startup/listening messages → `log.info()`
   - Errors/exceptions → `log.error()`
6. Convert any f-strings to logging-style
7. Verify no print() calls remain

## Files to Create/Modify
- `cyrus2/cyrus_server.py` — replace 4 print() calls

## Testing
```bash
# Run normally, check output format
python cyrus2/cyrus_server.py 2>&1 | head -10
# Expected: [cyrus.server] I Server listening on port...

# Grep for any remaining print() calls (should find 0)
grep -n "print(" cyrus2/cyrus_server.py
# Expected: no matches
```

## Stage Log

### GROOMED — 2026-03-11 18:14:54Z

- **From:** NEW
- **Duration in stage:** 31s
- **Input tokens:** 34,451 (final context: 34,451)
- **Output tokens:** 3
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
