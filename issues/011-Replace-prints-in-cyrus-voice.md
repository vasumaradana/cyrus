---
id=011-Replace-prints-in-cyrus-voice
title=Issue 011: Replace print() calls in cyrus_voice.py
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=40274
total_output_tokens=5
total_duration_seconds=63
total_iterations=1
run_count=1
---

# Issue 011: Replace print() calls in cyrus_voice.py

## Sprint
Sprint 2 — Quality & Safety

## Priority
High

## References
- docs/16-logging-system.md — Print-to-log conversion rules, Per-file changes section

## Description
Replace all 32 `print()` calls in `cyrus2/cyrus_voice.py` with logging calls. Follow the same conversion rules as Issue 010. Add `from cyrus2.cyrus_log import setup_logging` at the top and call it once in `main()`.

## Blocked By
- Issue 009 — Create cyrus_log module

## Acceptance Criteria
- [ ] All 32 `print()` calls replaced with `log.*()` equivalents
- [ ] `from cyrus2.cyrus_log import setup_logging` added at module top
- [ ] `import logging` added (if not present)
- [ ] `log = logging.getLogger("cyrus.voice")` defined after imports
- [ ] `setup_logging("cyrus")` called once in `main()` before any logging
- [ ] `[Voice]` prefix patterns → `log.info()`
- [ ] `[!]` prefix patterns → `log.error()`
- [ ] Timeout/fallback patterns → `log.warning()`
- [ ] Debug patterns (transcription flow, TTS dispatch) → `log.debug()`
- [ ] Exception handlers using broad `except` → `log.error()` or `log.debug()` with `exc_info=True`
- [ ] All f-strings converted to `%s` style logging
- [ ] File still has same functionality; only logging mechanism changed
- [ ] No new print() calls introduced

## Implementation Steps
1. Add imports at top of `cyrus2/cyrus_voice.py`:
   ```python
   import logging
   from cyrus2.cyrus_log import setup_logging
   ```
2. Add logger definition after imports:
   ```python
   log = logging.getLogger("cyrus.voice")
   ```
3. Locate `main()` function and add `setup_logging("cyrus")` as first line
4. Search for all `print(` patterns in file
5. For each print():
   - If pattern is `[Voice] ...` → `log.info(...)`
   - If pattern is `[!] ...` → `log.error(...)`
   - If pattern matches timeout/fallback → `log.warning(...)`
   - If pattern is transcription/TTS debug → `log.debug(...)`
   - Convert f-strings to logging-style
   - Add `exc_info=True` for exception context
6. Run linter/formatter to ensure consistent style
7. Verify no print() calls remain

## Files to Create/Modify
- `cyrus2/cyrus_voice.py` — replace 32 print() calls

## Testing
```bash
# Run normally, check output format
python cyrus2/cyrus_voice.py 2>&1 | head -20
# Expected: [cyrus.voice] I Connected to brain...

# Run with debug logging
CYRUS_LOG_LEVEL=DEBUG python cyrus2/cyrus_voice.py 2>&1 | head -20
# Expected: timestamps + transcription debug lines visible

# Grep for any remaining print() calls (should find 0)
grep -n "print(" cyrus2/cyrus_voice.py
# Expected: no matches
```

## Stage Log

### GROOMED — 2026-03-11 18:14:22Z

- **From:** NEW
- **Duration in stage:** 63s
- **Input tokens:** 40,274 (final context: 40,274)
- **Output tokens:** 5
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
