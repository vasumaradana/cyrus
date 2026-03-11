---
id=023-Write-test-permission-keywords
title=Issue 023: Write test_permission_keywords.py (Tier 3)
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=45629
total_output_tokens=5
total_duration_seconds=90
total_iterations=1
run_count=1
---

# Issue 023: Write test_permission_keywords.py (Tier 3)

## Sprint
Sprint 3 — Test Suite

## Priority
High

## References
- [docs/14-test-suite.md — Tier 3: Keyword & State Machine Tests](../docs/14-test-suite.md#tier-3-keyword--state-machine-tests)
- `cyrus2/cyrus_permission.py` (PermissionWatcher.handle_response() or equivalent)
- ALLOW_WORDS and DENY_WORDS constants

## Description
Tier 3 tests for permission keyword matching. Test ALLOW_WORDS and DENY_WORDS matching in PermissionWatcher.handle_response(). Approximately 12 test cases covering affirmative responses (yes, sure, okay), negative responses (no, never, don't), edge cases, and ambiguous input.

## Blocked By
- Issue 005 (cyrus_common.py foundation)
- Issue 018 (conftest.py fixtures)

## Acceptance Criteria
- [ ] `cyrus2/tests/test_permission_keywords.py` exists with 12+ test cases
- [ ] Tests verify ALLOW_WORDS matching (~5 cases): yes, sure, okay, affirmative variations
- [ ] Tests verify DENY_WORDS matching (~5 cases): no, never, refuse, deny variations
- [ ] Edge cases handled (~2 cases): ambiguous, no keywords, mixed
- [ ] Case-insensitive matching verified
- [ ] All tests pass: `pytest tests/test_permission_keywords.py -v`

## Implementation Steps
1. Create `cyrus2/tests/test_permission_keywords.py`
2. Import permission check functions from cyrus_permission.py:
   ```python
   from cyrus_permission import PermissionWatcher, ALLOW_WORDS, DENY_WORDS
   # or equivalent functions
   ```
3. Write test cases for ALLOW_WORDS (~5 cases):
   - "yes" → allow=True
   - "sure thing" → allow=True
   - "okay go ahead" → allow=True
   - "absolutely" → allow=True
   - "yep" / "yeah" → allow=True
4. Write test cases for DENY_WORDS (~5 cases):
   - "no" → allow=False
   - "never" → allow=False
   - "don't do that" → allow=False
   - "refuse" → allow=False
   - "nope" → allow=False
5. Write edge case tests (~2 cases):
   - Empty response → ambiguous (None or default)
   - "maybe" or "I don't know" → ambiguous
   - Response with both keywords → determine priority
6. Verify case-insensitive matching:
   - "YES" → allow=True
   - "No" → allow=False
7. Use parametrize with (input, expected_allow_value) pairs

## Files to Create/Modify
- `cyrus2/tests/test_permission_keywords.py` (new)

## Testing
```bash
pytest cyrus2/tests/test_permission_keywords.py -v
pytest cyrus2/tests/test_permission_keywords.py::test_allow_words -v
pytest cyrus2/tests/test_permission_keywords.py -k "deny" -v
pytest cyrus2/tests/test_permission_keywords.py -k "edge or ambiguous" -v
```

## Stage Log

### GROOMED — 2026-03-11 18:31:20Z

- **From:** NEW
- **Duration in stage:** 90s
- **Input tokens:** 45,629 (final context: 45,629)
- **Output tokens:** 5
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
