---
id=021-Write-test-fast-command
title=Issue 021: Write test_fast_command.py (Tier 1)
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=63242
total_output_tokens=12
total_duration_seconds=93
total_iterations=2
run_count=2
---

# Issue 021: Write test_fast_command.py (Tier 1)

## Sprint
Sprint 3 — Test Suite

## Priority
Critical

## References
- [docs/14-test-suite.md — Tier 1: Pure Function Tests](../docs/14-test-suite.md#tier-1-pure-function-tests-zero-mocking)
- `cyrus2/cyrus_brain.py:290-330` (_fast_command function)

## Description
Tier 1 pure function tests for _fast_command() meta-command routing. Approximately 25+ test cases covering pause, unlock, which_project, last_message, switch, rename, and non-command edge cases. Zero mocking required.

## Blocked By
- Issue 005 (cyrus_common.py foundation)
- Issue 018 (conftest.py fixtures)

## Acceptance Criteria
- [ ] `cyrus2/tests/test_fast_command.py` exists with 25+ test cases
- [ ] Each command type has 2-3 test cases: happy path, edge case, invalid format
- [ ] Commands tested: pause, unlock, which_project, last_message, switch, rename
- [ ] Non-command strings return None or empty dict
- [ ] All tests pass: `pytest tests/test_fast_command.py -v`
- [ ] Test names indicate command type and scenario

## Implementation Steps
1. Create `cyrus2/tests/test_fast_command.py`
2. Import function from `cyrus_brain.py`:
   ```python
   from cyrus_brain import _fast_command
   ```
3. Write test cases organized by command type:
   - **pause** (~3 cases):
     - "pause" → {command: "pause"}
     - "pause for 10 seconds" → {command: "pause", duration: 10}
     - "pause xyz" → error/None (invalid format)
   - **unlock** (~2 cases):
     - "unlock" → {command: "unlock"}
     - "unlock password" → {command: "unlock", password: "password"}
   - **which_project** (~2 cases):
     - "which project" / "what project" → {command: "which_project"}
     - Case variations
   - **last_message** (~2 cases):
     - "last message" / "repeat that" / "what did you say" → {command: "last_message"}
   - **switch** (~4 cases):
     - "switch to myproject" → {command: "switch", project: "myproject"}
     - "switch myproject" → same
     - "switch" alone → error
   - **rename** (~4 cases):
     - "rename to newname" → {command: "rename", name: "newname"}
     - "rename project newname" → same
     - "rename" alone → error
   - **Non-commands** (~3 cases):
     - Regular conversation → None
     - Partial matches ("pausable" != "pause") → None
     - Empty string → None
4. Use parametrize for systematic coverage
5. Verify return type consistency (dict or None)

## Files to Create/Modify
- `cyrus2/tests/test_fast_command.py` (new)

## Testing
```bash
pytest cyrus2/tests/test_fast_command.py -v
pytest cyrus2/tests/test_fast_command.py::test_pause -v
pytest cyrus2/tests/test_fast_command.py -k "switch or rename" -v
```

## Stage Log

### NEW — 2026-03-11 18:27:27Z

- **From:** NEW
- **Duration in stage:** 53s
- **Input tokens:** 37,614 (final context: 37,614)
- **Output tokens:** 4
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage


### GROOMED — 2026-03-11 18:30:59Z

- **From:** NEW
- **Duration in stage:** 40s
- **Input tokens:** 25,628 (final context: 25,628)
- **Output tokens:** 8
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** interview
## Interview Q&A

1. **Q:** The issue spec describes _fast_command() returning simple command dicts like {"command": "pause"}, but the actual implementation returns {"action": "command", "spoken": "", "message": "", "command": {"type": "pause"}}. Should tests match the current implementation or the spec?
   **A:** Refactor _fast_command() to match the spec (simpler return format), then test that

2. **Q:** The issue mentions testing pause with optional "duration" parameter and unlock with optional "password" parameter, but the current implementation doesn't parse these. Should tests cover these fields?
   **A:** Yes—refactor _fast_command() to parse these parameters first, then test

3. **Q:** The issue mentions command types "switch" and "rename", but the actual implementation uses "switch_project" and "rename_session". Should tests use the names in the current code?
   **A:** No—refactor to use the simpler names first, then test
