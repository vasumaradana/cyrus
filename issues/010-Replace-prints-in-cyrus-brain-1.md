---
id=010-Replace-prints-in-cyrus-brain-1
title=Add logging boilerplate to cyrus_brain.py (imports, logger, setup_logging)
state=PLANNED
parent=010-Replace-prints-in-cyrus-brain
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=83878
total_output_tokens=30
total_duration_seconds=234
total_iterations=2
run_count=2
---

# Add logging boilerplate to cyrus_brain.py (imports, logger, setup_logging)

## Sprint
Sprint 2 — Quality & Safety

## Priority
High

## Parent
010-Replace-prints-in-cyrus-brain

## References
- docs/16-logging-system.md — Print-to-log conversion rules
- cyrus2/cyrus_brain.py — file to modify
- cyrus2/cyrus_log.py — dependency (Issue 009)

## Description
Add the logging infrastructure boilerplate to `cyrus2/cyrus_brain.py` as the prerequisite for all print() replacement work. This child covers: verifying or creating `cyrus_log.py` (Issue 009 blocker), adding the `setup_logging` import, defining the named logger, and calling `setup_logging("cyrus")` in `main()`.

## Blocked By
- Issue 009 — Create cyrus_log module (if `cyrus2/cyrus_log.py` does not yet exist, create a minimal stub per the spec below)

## Acceptance Criteria
- [ ] `from cyrus2.cyrus_log import setup_logging` added after existing imports in `cyrus2/cyrus_brain.py`
- [ ] `import logging` confirmed present (already at line 31 — verify, do not duplicate)
- [ ] `log = logging.getLogger("cyrus.brain")` defined as a module-level variable after imports
- [ ] `setup_logging("cyrus")` called as the first executable line in `main()` (before argument parsing)
- [ ] If `cyrus2/cyrus_log.py` is missing, a minimal stub is created matching the spec in `docs/16-logging-system.md`
- [ ] `ruff check cyrus2/cyrus_brain.py` passes with no errors
- [ ] `ruff format --check cyrus2/cyrus_brain.py` passes

## Implementation Steps
1. Check if `cyrus2/cyrus_log.py` exists. If missing, create a minimal stub:
   ```python
   import logging
   import os
   import sys

   def setup_logging(name: str = "cyrus") -> logging.Logger:
       level_name = os.environ.get("CYRUS_LOG_LEVEL", "INFO").upper()
       level = getattr(logging, level_name, logging.INFO)
       fmt = "[{name}] {levelname:.1s} {message}"
       if level <= logging.DEBUG:
           fmt = "{asctime} [{name}] {levelname:.1s} {message}"
       handler = logging.StreamHandler(sys.stderr)
       handler.setFormatter(logging.Formatter(fmt, style="{", datefmt="%H:%M:%S"))
       root = logging.getLogger(name)
       root.setLevel(level)
       root.addHandler(handler)
       root.propagate = False
       return root
   ```
2. In `cyrus2/cyrus_brain.py`, after the existing import block (after line 91), add:
   ```python
   from cyrus2.cyrus_log import setup_logging
   ```
3. After the imports section, add the module-level logger:
   ```python
   log = logging.getLogger("cyrus.brain")
   ```
4. Locate `main()` (around line 1239) and add as the very first line:
   ```python
   setup_logging("cyrus")
   ```
5. Run `ruff check cyrus2/cyrus_brain.py` and fix any lint errors
6. Run `ruff format cyrus2/cyrus_brain.py`

## Files to Create/Modify
- `cyrus2/cyrus_log.py` — create if missing (~15 lines stub)
- `cyrus2/cyrus_brain.py` — add 3 import/boilerplate additions

## Testing
```bash
# Verify imports resolve
python -c "from cyrus2.cyrus_brain import *" 2>&1 | head -5

# Confirm logger is defined
python -c "import cyrus2.cyrus_brain as b; print(b.log)" 2>&1

# Lint check
ruff check cyrus2/cyrus_brain.py
```

## Stage Log

### GROOMED — 2026-03-17 01:17:54Z

- **From:** NEW
- **Duration in stage:** 0s
- **Input tokens:** 44,973 (final context: 44,973)
- **Output tokens:** 4
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage

### PLANNED — 2026-03-17 01:27:16Z

- **From:** PLANNED
- **Duration in stage:** 149s
- **Input tokens:** 38,905 (final context: 38,905)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 19%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan
