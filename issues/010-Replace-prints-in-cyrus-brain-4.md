---
id=010-Replace-prints-in-cyrus-brain-4
title=Write acceptance tests for cyrus_brain.py logging migration and verify full suite
state=PLANNED
parent=010-Replace-prints-in-cyrus-brain
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=125792
total_output_tokens=34
total_duration_seconds=278
total_iterations=2
run_count=2
---

# Write acceptance tests for cyrus_brain.py logging migration and verify full suite

## Sprint
Sprint 2 — Quality & Safety

## Priority
High

## Parent
010-Replace-prints-in-cyrus-brain

## References
- docs/16-logging-system.md — logging spec
- cyrus2/tests/ — existing test patterns (test_007.py, test_008.py)
- plans/010-Replace-prints-in-cyrus-brain.md — acceptance-driven test table

## Description
Write `cyrus2/tests/test_010_print_replacement.py` containing AST-based static analysis tests that verify all acceptance criteria from the parent issue have been met. Follows the unittest class-based pattern used by test_007 and test_008. Run the full test suite to confirm zero regressions. Requires children 1, 2, and 3 to be complete.

## Blocked By
- 010-Replace-prints-in-cyrus-brain-3 — all conversions must be done before testing

## Acceptance Criteria
- [ ] `cyrus2/tests/test_010_print_replacement.py` created
- [ ] `test_no_print_calls_remain` — AST/grep: zero `print(` calls in cyrus_brain.py
- [ ] `test_setup_logging_import_exists` — AST: `from cyrus2.cyrus_log import setup_logging` present
- [ ] `test_logging_import_exists` — AST: `import logging` present
- [ ] `test_named_logger_defined` — source contains `logging.getLogger("cyrus.brain")`
- [ ] `test_setup_logging_called_in_main` — AST: `setup_logging("cyrus")` call present in `main()` body
- [ ] `test_no_brain_prefix_in_source` — no `[Brain]` string in log call arguments
- [ ] `test_no_error_prefix_in_source` — no `[!]` string in log call arguments
- [ ] `test_no_root_logger_calls` — zero `logging.debug/info/warning/error/exception(` in file
- [ ] `test_no_fstrings_in_log_calls` — AST walk: log.xyz() args contain no JoinedStr (f-string) nodes
- [ ] `test_except_blocks_use_exc_info` — AST: log calls inside except blocks have `exc_info=True` kwarg
- [ ] `test_module_imports_cleanly` — import cyrus_brain without errors (mock Windows-only deps)
- [ ] All tests pass: `python -m pytest cyrus2/tests/test_010_print_replacement.py -v`
- [ ] Full suite passes: `python -m pytest cyrus2/tests/ -v`

## Implementation Steps
1. Study `cyrus2/tests/test_007.py` and `test_008.py` to understand the unittest + AST patterns used
2. Create `cyrus2/tests/test_010_print_replacement.py` following the same class structure with AC docstrings
3. Implement each test listed in the acceptance criteria (see detailed table in `plans/010-Replace-prints-in-cyrus-brain.md`)
4. For `test_module_imports_cleanly`: use `unittest.mock.patch` to mock Windows-specific modules (e.g., `uiautomation`, `comtypes`) before importing `cyrus_brain`
5. Run the test file in isolation: `python -m pytest cyrus2/tests/test_010_print_replacement.py -v`
6. Fix any failures — if a test fails because the source still has issues, that is a regression in children 1-3, but fix it here anyway
7. Run full suite: `python -m pytest cyrus2/tests/ -v`
8. Run lint on the new test file: `ruff check cyrus2/tests/test_010_print_replacement.py`

## Files to Create
- `cyrus2/tests/test_010_print_replacement.py` — ~120-180 lines, unittest-based with AST static analysis

## Testing
```bash
# Run new tests
python -m pytest cyrus2/tests/test_010_print_replacement.py -v

# Run full suite
python -m pytest cyrus2/tests/ -v

# Lint new test file
ruff check cyrus2/tests/test_010_print_replacement.py

# Final verification: zero prints, zero root logger
grep -c "print(" cyrus2/cyrus_brain.py
grep -c "logging\.\(debug\|info\|warning\|error\|exception\)" cyrus2/cyrus_brain.py
# Both expected: 0
```

## Stage Log

### GROOMED — 2026-03-17 01:19:36Z

- **From:** NEW
- **Duration in stage:** 0s
- **Input tokens:** 60,395 (final context: 60,395)
- **Output tokens:** 8
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage

### PLANNED — 2026-03-17 01:33:10Z

- **From:** PLANNED
- **Duration in stage:** 198s
- **Input tokens:** 65,397 (final context: 65,397)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 33%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan
