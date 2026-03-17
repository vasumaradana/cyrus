# Plan: Issue 020 — Write test_project_matching.py (Tier 1)

## Gap Analysis

**What exists:**
- `cyrus_common.py` contains three pure functions to test:
  - `_extract_project(title: str) -> str` (lines 180-189)
  - `_make_alias(proj: str) -> str` (lines 192-199)
  - `_resolve_project(query: str, aliases: dict) -> str | None` (lines 202-221)
- `cyrus2/tests/` directory exists with pytest framework (conftest.py, __init__.py)
- Pattern established in `test_text_processing.py` — import from `cyrus_common` directly

**What was missing:**
- `cyrus2/tests/test_project_matching.py` — not present

## Prioritized Tasks

- [x] Read `_extract_project`, `_make_alias`, `_resolve_project` implementations in `cyrus_common.py`
- [x] Study existing `test_text_processing.py` for test patterns and import conventions
- [x] Create `cyrus2/tests/test_project_matching.py` with 37 test cases (26+ required)
- [x] Verify all tests pass: `pytest tests/test_project_matching.py -v`

## Acceptance-Driven Tests

| Acceptance Criterion | Test Class | Count |
|---|---|---|
| test_extract_project() covers ~10 cases | TestExtractProject | 12 |
| test_make_alias() covers ~6 cases | TestMakeAlias | 12 |
| test_resolve_project() covers ~10 cases | TestResolveProject | 13 |
| 26+ total test cases | All classes | 37 |
| All tests pass | All | 37/37 |
| Test names describe the format/transformation | All | ✓ |

## Validation

```
pytest cyrus2/tests/test_project_matching.py -v
37 passed in 0.03s
```

## Files Created

- `cyrus2/tests/test_project_matching.py` (new — 37 test cases)

## Key Implementation Notes

- Import from `cyrus_common` directly (not `cyrus_brain`) to avoid Windows-only platform deps
- `_make_alias` does NOT split CamelCase — it only replaces `-` and `_` with spaces and lowercases
- `_resolve_project` with empty query `""` matches ALL aliases (empty string is substring of everything) — longest wins
- All three functions are pure (no I/O, no global state) — zero mocking required
