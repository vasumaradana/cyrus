# Test Suite Plan for Cyrus

## Context
Cyrus has zero automated tests. Many pure functions (text parsing, command routing, speech cleaning) are highly testable without mocking, plus complex stateful logic (VAD, ChatWatcher, PermissionWatcher) benefits from mocked unit tests. Prioritize high-value, low-effort tests first.

## Framework: pytest
- `pytest` + `pytest-asyncio` in `requirements-dev.txt`
- Tests in `tests/` directory

---

## Tier 1: Pure Function Tests (zero mocking)

### `tests/test_text_processing.py`
- `clean_for_speech()` — `cyrus_brain.py:167-191` — strips markdown, code blocks, truncates (~15 cases)
- `_sanitize_for_speech()` — `cyrus_brain.py:153-165` — Unicode→ASCII mapping (~8 cases)
- `_strip_fillers()` — `cyrus_voice.py:113-118` — removes leading filler words (~8 cases)

### `tests/test_project_matching.py`
- `_extract_project(title)` — `cyrus_brain.py:130-134` — VS Code title parsing (~10 cases)
- `_make_alias(proj)` — `cyrus_brain.py:136-138` — kebab/snake→spaces (~6 cases)
- `_resolve_project(query, aliases)` — fuzzy project matching (~10 cases)

### `tests/test_fast_command.py`
- `_fast_command(text)` — `cyrus_brain.py:290-330` — regex meta-command routing (~25 cases)
- Covers: pause, unlock, which_project, last_message, switch, rename, non-commands, edge cases

---

## Tier 2: Hook Parsing Tests

### `tests/test_hook.py`
- `cyrus_hook.py:27-93` — mock stdin + `_send()`, verify dispatched messages (~12 cases)
- Stop, PreToolUse, PostToolUse, Notification, PreCompact, invalid JSON, unknown events

---

## Tier 3: Keyword & State Machine Tests

### `tests/test_permission_keywords.py`
- `PermissionWatcher.handle_response()` — ALLOW_WORDS/DENY_WORDS matching (~12 cases)

### `tests/test_vad_logic.py`
- VAD state machine — mock Silero model, test ring buffer, adaptive silence, timeout (~15 cases)

---

## Tier 4: Integration Tests (heavier mocking)

### `tests/test_chat_extraction.py`
- `ChatWatcher._extract_response()` — mock UIA node trees, test anchor/backtrack logic (~10 cases)

### `tests/test_companion_protocol.py`
- Extension IPC — mock TCP socket, test JSON line protocol (~8 cases)

---

## File Structure
```
tests/
├── conftest.py
├── test_text_processing.py
├── test_project_matching.py
├── test_fast_command.py
├── test_hook.py
├── test_permission_keywords.py
├── test_vad_logic.py
├── test_chat_extraction.py
└── test_companion_protocol.py
requirements-dev.txt
```

## Verification
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
