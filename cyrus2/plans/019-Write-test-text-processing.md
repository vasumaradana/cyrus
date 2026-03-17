# Plan: Issue 019 — Write test_text_processing.py (Tier 1)

## Status: COMPLETE

## Gap Analysis

**What existed:**
- `cyrus_common.py` defines `clean_for_speech()`, `_sanitize_for_speech()`, and `_strip_fillers()` (the authoritative definitions)
- `cyrus_voice.py` defines an identical local copy of `_strip_fillers()`
- `cyrus_brain.py` re-exports all three from `cyrus_common`
- No test file for these functions existed

**What needed building:**
- `cyrus2/tests/test_text_processing.py` with 30+ test cases

## Prioritized Tasks

- [x] Study `cyrus_common.py` to understand exact function behavior
- [x] Study import patterns from existing test files (test_007, test_018)
- [x] Create `tests/test_text_processing.py` with 52 test cases
- [x] Verify all 52 tests pass
- [x] Verify full suite (447 tests) still passes

## Acceptance-Driven Tests

| Criterion | Test Class / Method | Status |
|-----------|---------------------|--------|
| `test_text_processing.py` exists with 30+ test cases | 52 test cases created | ✅ |
| `test_clean_for_speech()` covers ~15 cases | 19 test methods | ✅ |
| `test_sanitize_for_speech()` covers ~8 cases | 12 test cases (1 parametrize × 8) | ✅ |
| `test_strip_fillers()` covers ~8 cases | 21 test cases (1 parametrize × 14) | ✅ |
| All tests pass | `pytest tests/test_text_processing.py -v` → 52 passed | ✅ |
| Test names clearly indicate scenario | All names follow `test_X_verb_description` pattern | ✅ |

## Implementation Notes

### Import Strategy
The issue suggests importing from `cyrus_brain` and `cyrus_voice`. However:
- `cyrus_brain.py` requires Windows-only modules (comtypes, uiautomation, pyautogui)
- `cyrus_voice.py` requires heavy audio/ML deps (torch, pygame, sounddevice, faster_whisper)
- **`cyrus_common.py` defines all three functions and handles missing platform deps via `try/except`**

We import from `cyrus_common` directly — this is where the functions are authoritatively defined, and it imports cleanly on any platform.

### Issue Example Corrections
The issue lists `_strip_fillers("like really cool")` → `"really cool"` and `"uh you know what"` → `"what"`. These are **incorrect** based on the actual `_FILLER_RE`:
```python
r"^(?:uh+|um+|er+|so|okay|ok|right|hey|please|can you|could you|would you)\s+"
```
Neither "like" nor "you know" appears in the regex. Tests were written to match actual behavior.

### Test Coverage
- `TestCleanForSpeech`: 19 methods — headers, emphasis, code blocks, links, lists, truncation, edge cases
- `TestSanitizeForSpeech`: 12 test cases — all 8 Unicode replacements (parametrize), ASCII passthrough, empty, mixed, normal quotes
- `TestStripFillers`: 21 test cases — 14 filler prefixes (parametrize), no-filler, stacking, case-insensitive, non-leading, empty, multi-word, no-trailing-space corner case

## Verification Checklist

- [x] `pytest tests/test_text_processing.py -v` → 52 passed in 0.04s
- [x] Full suite `pytest tests/` → 447 passed, 1 warning (pre-existing), 0 failures
- [x] Test names clearly describe scenario
- [x] `pytest.mark.parametrize` used for data-driven tests
- [x] Zero mocking required (pure function tests)
- [x] Module docstring explains import rationale

## Files Created

- `cyrus2/tests/test_text_processing.py` (new, 52 test cases)
- `cyrus2/plans/019-Write-test-text-processing.md` (this file)
