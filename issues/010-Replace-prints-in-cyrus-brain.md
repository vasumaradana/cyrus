---
id=010-Replace-prints-in-cyrus-brain
title=Issue 010: Replace print() calls in cyrus_brain.py
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=32828
total_output_tokens=8
total_duration_seconds=38
total_iterations=1
run_count=1
---

# Issue 010: Replace print() calls in cyrus_brain.py

## Sprint
Sprint 2 — Quality & Safety

## Priority
High

## References
- docs/16-logging-system.md — Print-to-log conversion rules, Per-file changes section

## Description
Replace all 66 `print()` calls in `cyrus2/cyrus_brain.py` with logging calls. Follow the conversion rules: `[Brain]`/`[!]` prefix patterns map to `log.info()`, `log.error()`, `log.warning()`, and `log.debug()` based on context. Add `from cyrus2.cyrus_log import setup_logging` at the top and call it once in `main()`.

## Blocked By
- Issue 009 — Create cyrus_log module

## Acceptance Criteria
- [ ] All 66 `print()` calls replaced with `log.*()` equivalents
- [ ] `from cyrus2.cyrus_log import setup_logging` added at module top
- [ ] `import logging` added (if not present)
- [ ] `log = logging.getLogger("cyrus.brain")` defined after imports
- [ ] `setup_logging("cyrus")` called once in `main()` before any logging
- [ ] `[Brain]` prefix patterns → `log.info()`
- [ ] `[!]` prefix patterns → `log.error()`
- [ ] Fallback/timeout/retry patterns → `log.warning()`
- [ ] Routing/dispatch/scan patterns → `log.debug()`
- [ ] Exception handlers using broad `except` → `log.error("context", exc_info=True)` or `log.debug(..., exc_info=True)`
- [ ] All f-strings converted to `%s` style logging (e.g., `log.info("msg: %s", var)`)
- [ ] File still has same functionality; only logging mechanism changed
- [ ] No new print() calls introduced

## Implementation Steps
1. Add imports at top of `cyrus2/cyrus_brain.py`:
   ```python
   import logging
   from cyrus2.cyrus_log import setup_logging
   ```
2. Add logger definition after imports:
   ```python
   log = logging.getLogger("cyrus.brain")
   ```
3. Locate `main()` function and add `setup_logging("cyrus")` as first line
4. Search for all `print(` patterns in file
5. For each print():
   - If pattern is `[Brain] ...` → `log.info(...)`
   - If pattern is `[!] ...` → `log.error(...)`
   - If pattern matches fallback/retry/timeout → `log.warning(...)`
   - If pattern is debug info (routing, dispatch, scan) → `log.debug(...)`
   - If f-string, convert to logging-style: `log.info("msg: %s", var)`
   - If exception context, add `exc_info=True`
6. Run linter/formatter to ensure consistent style
7. Verify no print() calls remain (except in test/diagnostic code)

## Files to Create/Modify
- `cyrus2/cyrus_brain.py` — replace 66 print() calls

## Testing
```bash
# Run normally, check output format
python cyrus2/cyrus_brain.py 2>&1 | head -20
# Expected: [cyrus.brain] I Listening for wake word...

# Run with debug logging
CYRUS_LOG_LEVEL=DEBUG python cyrus2/cyrus_brain.py 2>&1 | head -20
# Expected: timestamps + debug lines visible

# Grep for any remaining print() calls (should find 0)
grep -n "print(" cyrus2/cyrus_brain.py
# Expected: no matches
```

## Stage Log

### GROOMED — 2026-03-11 18:36:17Z

- **From:** NEW
- **Duration in stage:** 38s
- **Input tokens:** 32,828 (final context: 32,828)
- **Output tokens:** 8
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
