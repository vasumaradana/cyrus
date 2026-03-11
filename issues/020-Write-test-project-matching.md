---
id=020-Write-test-project-matching
title=Issue 020: Write test_project_matching.py (Tier 1)
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=44255
total_output_tokens=9
total_duration_seconds=90
total_iterations=1
run_count=1
---

# Issue 020: Write test_project_matching.py (Tier 1)

## Sprint
Sprint 3 — Test Suite

## Priority
Critical

## References
- [docs/14-test-suite.md — Tier 1: Pure Function Tests](../docs/14-test-suite.md#tier-1-pure-function-tests-zero-mocking)
- `cyrus2/cyrus_brain.py:130-138` (_extract_project, _make_alias)
- Fuzzy matching logic for _resolve_project

## Description
Tier 1 pure function tests for project matching: _extract_project() for VS Code title parsing, _make_alias() for kebab/snake to spaces conversion, and _resolve_project() for fuzzy project name matching. Approximately 26 test cases covering common patterns and edge cases. Zero mocking required.

## Blocked By
- Issue 005 (cyrus_common.py foundation)
- Issue 018 (conftest.py fixtures)

## Acceptance Criteria
- [ ] `cyrus2/tests/test_project_matching.py` exists with 26+ test cases
- [ ] `test_extract_project()` covers ~10 cases: VS Code title parsing with various formats
- [ ] `test_make_alias()` covers ~6 cases: kebab-case, snake_case, mixed case conversions
- [ ] `test_resolve_project()` covers ~10 cases: fuzzy matching, ambiguity, no-match scenarios
- [ ] All tests pass: `pytest tests/test_project_matching.py -v`
- [ ] Test names describe the title format or alias transformation

## Implementation Steps
1. Create `cyrus2/tests/test_project_matching.py`
2. Import functions from `cyrus_brain.py`:
   ```python
   from cyrus_brain import _extract_project, _make_alias, _resolve_project
   ```
3. Write test_extract_project() with cases:
   - "myproject - Visual Studio Code" → "myproject"
   - "path/to/project - VSCode" → "project"
   - "ProjectName [folder] - VS Code" → "ProjectName"
   - Single-word titles
   - Unicode in project names
   - Empty/minimal titles
4. Write test_make_alias() with cases:
   - "my-project" → "my project"
   - "my_project" → "my project"
   - "myProject" → "my project"
   - "MY-PROJECT" → "my project"
   - Already spaced "my project" → unchanged
   - Mixed: "my-_-Project" → "my project"
5. Write test_resolve_project() with cases:
   - Exact match in aliases dict
   - Fuzzy match (1-2 char difference)
   - No match returns None
   - Case-insensitive matching
   - Empty aliases dict
   - Special chars in aliases
6. Use parametrize for comprehensive input/output pairs

## Files to Create/Modify
- `cyrus2/tests/test_project_matching.py` (new)

## Testing
```bash
pytest cyrus2/tests/test_project_matching.py -v
pytest cyrus2/tests/test_project_matching.py::test_extract_project -v
pytest cyrus2/tests/test_project_matching.py -k "alias" -v
```

## Stage Log

### GROOMED — 2026-03-11 18:26:33Z

- **From:** NEW
- **Duration in stage:** 90s
- **Input tokens:** 44,255 (final context: 44,255)
- **Output tokens:** 9
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
