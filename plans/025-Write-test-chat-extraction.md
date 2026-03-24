# Plan: Issue 025 — Write test_chat_extraction.py (Tier 4)

## Status: COMPLETE

## Gap Analysis

**What exists:**
- `cyrus2/cyrus_common.py` — `ChatWatcher._extract_response()` implementation with anchor/text-extraction logic
- `cyrus2/tests/conftest.py` — shared fixtures (mock_logger, mock_config, mock_send, mock_silero_model)
- `cyrus2/tests/` — existing test files for other tiers

**What was needed:**
- `cyrus2/tests/test_chat_extraction.py` — 12 tier-4 integration tests for `ChatWatcher._extract_response()`
- No changes to conftest.py needed (the method takes flat results lists, no UIA element objects required)

**Key insight:** `_extract_response(results)` takes a pre-walked flat list of `(depth, ctype, name)` tuples.
No UIA element tree traversal mocking required — we construct `results` lists directly in tests.

## How `_extract_response` works

1. Finds position of `EditControl("Message input")` — the end-of-chat sentinel
2. If not found → returns `""`
3. Primary anchor: last `ButtonControl` with `"Thinking"` in text before message input
4. Secondary anchor: last `ButtonControl("Message actions")` before message input
5. If neither → returns `""`
6. Collects `TextControl` and `ListItemControl` items from `[anchor+1 : msg_input_pos]`
   - Breaks on `_STOP` words or another `"Message actions"` button
   - Skips `_SKIP` words and text < 4 chars
   - Deduplicates: skips text already in `seen`, or text subsumed by longer already-seen text
7. Returns `" ".join(parts)`

## Prioritized Tasks

- [x] Create `cyrus2/tests/test_chat_extraction.py` with 12 test cases
- [x] Anchor detection tests (2): Thinking button anchor, Message actions anchor
- [x] Backtrack logic tests (3): last anchor wins, _STOP halts, non-text controls skipped
- [x] Text extraction tests (2): multi-element join, deduplication
- [x] Missing element tests (2): no message input, no anchor
- [x] Cache behavior test (1): deterministic output
- [x] Edge case tests (2): _SKIP words filtered, short text filtered
- [x] All tests pass: `pytest tests/test_chat_extraction.py -v`
- [x] Lint passes: `ruff check tests/test_chat_extraction.py`

## Acceptance-Driven Tests

| Acceptance Criterion | Test Function | Status |
|---|---|---|
| 10+ test cases | 12 tests total | ✅ |
| Anchor detection (~2): Thinking button, Message actions | `test_thinking_button_detected_as_primary_anchor`, `test_message_actions_used_as_secondary_anchor` | ✅ |
| Backtrack logic (~3): last anchor wins, STOP word, non-text skipped | `test_last_thinking_button_wins_when_multiple_present`, `test_stop_word_halts_extraction`, `test_only_text_and_listitem_controls_included` | ✅ |
| Text extraction (~2): joining, deduplication | `test_multiple_text_elements_joined_with_spaces`, `test_duplicate_text_deduplicated` | ✅ |
| Missing element handling (~2): no input, no anchor | `test_no_message_input_returns_empty_string`, `test_no_anchor_returns_empty_string` | ✅ |
| Cache behavior (~1): deterministic | `test_same_results_returns_same_response` | ✅ |
| Edge cases: _SKIP filtering, short text | `test_skip_words_filtered_from_response`, `test_short_text_under_four_chars_filtered` | ✅ |
| `pytest tests/test_chat_extraction.py -v` passes | 12/12 PASSED in 0.02s | ✅ |

## Files Created/Modified

- `cyrus2/tests/test_chat_extraction.py` — **NEW** — 12 tests, all passing
- `cyrus2/tests/conftest.py` — **NO CHANGE NEEDED** (existing fixtures sufficient)

## Verification Checklist

- [x] `pytest tests/test_chat_extraction.py -v` — 12/12 passed
- [x] `ruff check tests/test_chat_extraction.py` — All checks passed
- [x] 10+ test cases present (exactly 12)
- [x] All test categories covered (anchor, backtrack, extraction, missing, cache, edge)
- [x] Windows-specific modules mocked at `sys.modules` level (same pattern as test_permission_keywords.py)

## Implementation Approach

Tests call `ChatWatcher._extract_response()` directly with pre-constructed `results` lists.
`results` is a list of `(depth: int, ctype: str, name: str)` tuples — the flat output of `_walk()`.

Helper functions:
- `_r(ctype, name, depth=0)` — constructs a raw results tuple
- `_msg_input()` — the mandatory end-of-chat sentinel
- `_thinking(label)` — primary-anchor Thinking button
- `_msg_actions()` — secondary-anchor Message actions button
- `_text(content)` — TextControl text element
- `_list_item(content)` — ListItemControl text element
- `_make_watcher()` — minimal ChatWatcher instance for calling _extract_response

Windows modules (`comtypes`, `uiautomation`, `pyautogui`, `pygetwindow`, `pyperclip`,
`websockets`, etc.) mocked in `sys.modules` before `cyrus_common` is imported, same
pattern as `test_permission_keywords.py`.

## Open Questions

None — all resolved. The issue is complete.
