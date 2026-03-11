---
id=014-Replace-broad-exception-handlers
title=Issue 014: Replace broad exception handlers
state=SPLIT
parent=
children=040,041,042,043,044
split_count=0
force_split=false
verify_count=0
total_input_tokens=47728
total_output_tokens=7
total_duration_seconds=137
total_iterations=1
run_count=1
---

# Issue 014: Replace broad exception handlers

## Sprint
Sprint 2 — Quality & Safety

## Priority
High

## References
- docs/12-code-audit.md — H1 81 Broad except Exception Handlers section

## Description
Replace 81 silent `except Exception: pass` handlers with specific exception types and logging. Start with 4 worst offenders identified in the audit. Replace broad catches with specific types where possible; where broad catches are necessary for resilience (e.g., UIA tree walks), add `log.debug(..., exc_info=True)` before `pass`/`continue` to preserve debugging visibility.

## Blocked By
- Issue 010, 011, 012 (logging must be in place)

## Acceptance Criteria
- [ ] `cyrus_brain.py:455, 462` — silent UIA tree walk failures → `log.debug(..., exc_info=True)`
- [ ] `main.py:200` — race condition in window tracking → specific exception types or logging
- [ ] `main.py:1033–1034` — hidden session scan errors → `log.debug()` with context
- [ ] `main.py:1082` — VAD loop silent failures → `log.debug(..., exc_info=True)`
- [ ] All 4 worst offenders fixed with logging added
- [ ] Other broad `except Exception` handlers (77 remaining) have logging added where appropriate
- [ ] No new silent failures introduced
- [ ] All exception handlers preserve intended control flow

## Implementation Steps
1. Identify 4 worst offenders (per H1 audit):
   - `cyrus_brain.py:455` — UIA tree walk
   - `cyrus_brain.py:462` — UIA tree walk
   - `main.py:200` — window tracking
   - `main.py:1033–1034` — session scan
2. For each worst offender:
   a. Analyze what exceptions could be raised
   b. If specific types can be caught, use them (e.g., `except UIAutomationError:`)
   c. If broad catch is necessary, add `log.debug("operation context", exc_info=True)` before pass/continue
   d. If it's error path, use `log.error()` instead of `log.debug()`
3. For remaining 77 broad handlers:
   a. Review context and determine severity
   b. Silent critical operations → `log.error(..., exc_info=True)`
   c. Silent tolerant operations (polling, UI scans) → `log.debug(..., exc_info=True)`
   d. Silent pass-through operations → `log.debug(...)` (without exc_info)
4. Run linter to ensure consistency
5. Test that all exception logging appears at correct level

## Files to Create/Modify
- `cyrus2/cyrus_brain.py` — fix broad exception handlers (35 instances)
- `cyrus2/main.py` — fix broad exception handlers (33 instances) [if not deprecated]
- Other files with 12, 7, 4 broad handlers as appropriate

## Testing
```bash
# Verify 4 worst offenders have logging
grep -A2 "except Exception" cyrus2/cyrus_brain.py | grep -E "(455|462):"
# Expected: lines 455 and 462 have log.debug() calls

# Verify no silent pass statements remain in critical paths
grep -B2 "except Exception:" cyrus2/cyrus_brain.py | grep -c "pass"
# Should be significantly lower than before

# Run with DEBUG logging and trigger errors
CYRUS_LOG_LEVEL=DEBUG python cyrus2/cyrus_brain.py 2>&1 | grep "exc_info"
# Expected: exception details appear in log when errors occur
```

## Auto-Split by Triage

This issue was deemed too complex for a single session and has been split into 5 children:
- 040
- 041
- 042
- 043
- 044

## Stage Log

### SPLIT — 2026-03-11 18:17:53Z

- **From:** NEW
- **Duration in stage:** 137s
- **Input tokens:** 47,728 (final context: 47,728)
- **Output tokens:** 7
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
