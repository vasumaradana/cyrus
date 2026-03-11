---
id=022-Write-test-hook
title=Issue 022: Write test_hook.py (Tier 2)
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=49580
total_output_tokens=5
total_duration_seconds=142
total_iterations=1
run_count=1
---

# Issue 022: Write test_hook.py (Tier 2)

## Sprint
Sprint 3 — Test Suite

## Priority
High

## References
- [docs/14-test-suite.md — Tier 2: Hook Parsing Tests](../docs/14-test-suite.md#tier-2-hook-parsing-tests)
- `cyrus2/cyrus_hook.py:27-93` (hook parsing logic)

## Description
Tier 2 tests for cyrus_hook.py event parsing. Mock stdin and _send() to verify correct dispatch of Stop, PreToolUse, PostToolUse, Notification, PreCompact events. Approximately 12 test cases covering valid and invalid JSON, unknown event types, and edge cases.

## Blocked By
- Issue 018 (conftest.py fixtures)

## Acceptance Criteria
- [ ] `cyrus2/tests/test_hook.py` exists with 12+ test cases
- [ ] Tests cover event types: Stop, PreToolUse, PostToolUse, Notification, PreCompact
- [ ] Tests verify _send() called with correct arguments for each event
- [ ] Invalid JSON handling (malformed, missing fields)
- [ ] Unknown event type handling
- [ ] Empty/whitespace-only input handling
- [ ] All tests pass: `pytest tests/test_hook.py -v`

## Implementation Steps
1. Create `cyrus2/tests/test_hook.py`
2. Import hook processing functions and mock tools:
   ```python
   import json
   from unittest.mock import Mock, patch, call
   from cyrus_hook import process_event  # or equivalent main entry point
   ```
3. Use pytest-mock and conftest's mock_send fixture
4. Write test cases for each event type (~2 cases per type):
   - **Stop event** (~2 cases):
     - Valid Stop JSON → _send called with correct payload
     - Stop with extra fields → still valid
   - **PreToolUse** (~2 cases):
     - Valid PreToolUse JSON → _send dispatched correctly
     - Missing required fields → error/skip
   - **PostToolUse** (~2 cases):
     - Valid PostToolUse JSON → _send dispatched correctly
     - With tool output included
   - **Notification** (~2 cases):
     - Valid Notification JSON → _send dispatched correctly
     - Various notification types (info, warning, error)
   - **PreCompact** (~1 case):
     - Valid PreCompact JSON → _send dispatched correctly
   - **Error cases** (~3 cases):
     - Malformed JSON (not valid JSON) → logged/skipped
     - Unknown event type → logged/skipped
     - Empty input → handled gracefully
5. Mock stdin with StringIO for input simulation:
   ```python
   from io import StringIO
   with patch('sys.stdin', StringIO(json_line)):
       result = process_event()
   ```
6. Verify _send() calls with assert_called_with()

## Files to Create/Modify
- `cyrus2/tests/test_hook.py` (new)
- Update `cyrus2/tests/conftest.py` to add mock_send fixture if not present

## Testing
```bash
pytest cyrus2/tests/test_hook.py -v
pytest cyrus2/tests/test_hook.py::test_stop_event -v
pytest cyrus2/tests/test_hook.py -k "error or invalid" -v
```

## Stage Log

### GROOMED — 2026-03-11 18:29:49Z

- **From:** NEW
- **Duration in stage:** 142s
- **Input tokens:** 49,580 (final context: 49,580)
- **Output tokens:** 5
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
