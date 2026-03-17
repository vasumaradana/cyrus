# Plan: Issue 023 — Write test_permission_keywords.py (Tier 3)

## Status: COMPLETE

---

## Gap Analysis

| What Exists | What Was Needed |
|---|---|
| `PermissionWatcher.ALLOW_WORDS` and `DENY_WORDS` class-level sets in `cyrus_common.py` | `cyrus2/tests/test_permission_keywords.py` with 12+ test cases |
| `PermissionWatcher.handle_response(text)` — full implementation | Parametrized tests covering ALLOW/DENY matching, case-insensitivity, edge cases |
| Pattern from `test_017_permission_logging.py` (mock Windows modules, patch focus guard) | — |

**Key discovery**: `ALLOW_WORDS` and `DENY_WORDS` are **class attributes** on `PermissionWatcher`, not module-level constants. The issue's import example (`from cyrus_permission import ALLOW_WORDS`) was incorrect — access them as `PermissionWatcher.ALLOW_WORDS`.

---

## Prioritized Tasks

- [x] Study `cyrus_common.py` — locate `PermissionWatcher`, `ALLOW_WORDS`, `DENY_WORDS`, `handle_response()`
- [x] Study `test_017_permission_logging.py` — understand Windows mock pattern and test structure
- [x] Create `cyrus2/tests/test_permission_keywords.py` with 12+ test cases
- [x] Verify all tests pass: `pytest tests/test_permission_keywords.py -v`
- [x] Verify lint passes: `ruff check tests/test_permission_keywords.py`

---

## Acceptance-Driven Tests

| Acceptance Criterion | Test(s) | Status |
|---|---|---|
| ALLOW_WORDS matching (~5 cases) | `test_allow_word_returns_true` (9 parametrized) | ✅ |
| ALLOW_WORDS clears pending state | `test_allow_word_clears_pending` (5 parametrized) | ✅ |
| DENY_WORDS matching (~5 cases) | `test_deny_word_returns_true` (9 parametrized) | ✅ |
| DENY_WORDS clears pending state | `test_deny_word_clears_pending` (5 parametrized) | ✅ |
| Case-insensitive matching | `test_uppercase_keywords_are_recognised` (7), `test_mixed_case_keywords_are_recognised` (5) | ✅ |
| Edge: empty response | `test_empty_response_returns_false` | ✅ |
| Edge: ambiguous (no keywords) | `test_ambiguous_response_returns_false`, `test_ambiguous_response_leaves_pending_unchanged` | ✅ |
| Edge: not pending | `test_no_pending_returns_false_regardless_of_keywords` | ✅ |
| Edge: mixed allow+deny | `test_mixed_allow_and_deny_keywords_prefers_allow` | ✅ |
| Constants sanity | `test_allow_words_contains_core_keywords`, `test_deny_words_contains_core_keywords`, `test_allow_and_deny_words_are_disjoint` | ✅ |

**Total test instances**: 48 (all pass)

---

## Files Created/Modified

- **Created**: `cyrus2/tests/test_permission_keywords.py` (48 tests, 0 failures)

---

## Validation

- [x] `ruff check tests/test_permission_keywords.py` — All checks passed
- [x] `pytest tests/test_permission_keywords.py -v` — 48 passed in 0.04s
- [x] 12+ test cases (48 parametrized instances)
- [x] ALLOW_WORDS matching verified (9 cases: yes, yep, yeah, ok, okay, sure thing, okay go ahead, allow it, proceed with that)
- [x] DENY_WORDS matching verified (9 cases: no, nope, cancel, stop, reject, deny it, cancel that, stop it now, no way)
- [x] Case-insensitive matching verified (uppercase + mixed case)
- [x] Edge cases: empty, ambiguous, not-pending, mixed-keywords

---

## Acceptance Criteria Check

- [x] `cyrus2/tests/test_permission_keywords.py` exists with 12+ test cases (48)
- [x] Tests verify ALLOW_WORDS matching (~5 cases): yes, sure, okay, yep, yeah, allow, ok, proceed, go
- [x] Tests verify DENY_WORDS matching (~5 cases): no, nope, cancel, stop, reject, deny, no way
- [x] Edge cases handled: empty response, ambiguous, not-pending guard, mixed keywords
- [x] Case-insensitive matching verified (YES, Sure, OKAY, No, NOPE, Cancel, etc.)
- [x] All tests pass: `pytest tests/test_permission_keywords.py -v`

---

## Open Questions / Notes

None. Implementation straightforward.

**ALLOW_WORDS** (actual): `{"yes", "allow", "sure", "ok", "okay", "proceed", "yep", "yeah", "go"}`
**DENY_WORDS** (actual): `{"no", "deny", "cancel", "stop", "nope", "reject"}`

Note: The issue's implementation steps listed "absolutely", "never", "refuse", "don't" as expected keyword matches, but these are **not** in the current implementation. Tests were written against what exists, not the issue's examples.
