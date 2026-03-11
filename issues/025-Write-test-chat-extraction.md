# Issue 025: Write test_chat_extraction.py (Tier 4)

## Sprint
Sprint 3 — Test Suite

## Priority
Medium

## References
- [docs/14-test-suite.md — Tier 4: Integration Tests](../docs/14-test-suite.md#tier-4-integration-tests-heavier-mocking)
- `cyrus2/cyrus_watcher.py` (ChatWatcher._extract_response() or equivalent)
- UIA (UI Automation) tree structure and element navigation

## Description
Tier 4 integration tests for ChatWatcher._extract_response(). Mock UIA (UI Automation) element trees to test anchor/backtrack logic for finding and extracting chat responses from UI elements. Approximately 10 test cases covering various tree structures, missing elements, and response extraction patterns.

## Blocked By
- Issue 005 (cyrus_common.py foundation)
- Issue 018 (conftest.py fixtures)

## Acceptance Criteria
- [ ] `cyrus2/tests/test_chat_extraction.py` exists with 10+ test cases
- [ ] Tests verify anchor element detection (~2 cases): finding previous message/response marker
- [ ] Tests verify backtrack logic (~3 cases): traversing UIA tree upward/sideways to response
- [ ] Tests verify response text extraction (~2 cases): concatenating text from child elements
- [ ] Tests verify missing element handling (~2 cases): graceful fallback, None/empty return
- [ ] Tests verify cache behavior (~1 case): reusing cached response if tree unchanged
- [ ] All tests pass: `pytest tests/test_chat_extraction.py -v`

## Implementation Steps
1. Create `cyrus2/tests/test_chat_extraction.py`
2. Import UIA mocking and ChatWatcher:
   ```python
   from unittest.mock import Mock, MagicMock, patch
   from cyrus_watcher import ChatWatcher  # or extraction function
   ```
3. Create conftest fixture for mock UIA element tree:
   ```python
   @pytest.fixture
   def mock_uia_element():
       elem = MagicMock()
       elem.name = "Mock Element"
       elem.element_type = "Text"
       elem.get_children.return_value = []
       return elem
   ```
4. Write anchor detection tests (~2 cases):
   - Find "You" or username element as anchor
   - Find "Response:" or marker element as anchor
   - Return None if no anchor found
5. Write backtrack logic tests (~3 cases):
   - Traverse parent from anchor to find response container
   - Skip non-text siblings, find response element
   - Handle missing parent (already at root)
   - Extract from correct level of hierarchy
6. Write text extraction tests (~2 cases):
   - Concatenate text from nested children elements
   - Handle whitespace/newline normalization
   - Preserve paragraph breaks
7. Write missing element handling (~2 cases):
   - Missing anchor element → return None
   - Empty tree (no children) → return None or empty string
   - Graceful degradation on tree traversal error
8. Write cache behavior test (~1 case):
   - Same tree reference → cached response returned
   - Different tree reference → re-extract
9. Mock entire UIA tree hierarchies (parent→children→grandchildren)
10. Use parametrize with (tree_structure, expected_text_result) pairs

## Files to Create/Modify
- `cyrus2/tests/test_chat_extraction.py` (new)
- Update `cyrus2/tests/conftest.py` to add mock_uia_element fixture

## Testing
```bash
pytest cyrus2/tests/test_chat_extraction.py -v
pytest cyrus2/tests/test_chat_extraction.py::test_anchor_detection -v
pytest cyrus2/tests/test_chat_extraction.py -k "backtrack or extract" -v
pytest cyrus2/tests/test_chat_extraction.py -k "missing or error" -v
```
