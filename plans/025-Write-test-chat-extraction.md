# Plan 025: Write test_chat_extraction.py (Tier 4)

## Summary

Create `cyrus2/tests/test_chat_extraction.py` with 15 test cases covering `ChatWatcher._walk()` (3 cases — mock UIA element trees) and `ChatWatcher._extract_response()` (12 cases — anchor detection, backtrack logic, text extraction, missing elements, deduplication/cache). Uses `unittest.mock.MagicMock` for UIA controls and crafted tuple lists for extraction logic.

## Prerequisites

- **Issue 018** (PLANNED) — creates `cyrus2/tests/` directory, `conftest.py`, and pytest config with `pythonpath = [".."]` so `import cyrus_brain` works from test files.
- **Issue 005** (PLANNED) — extracts ChatWatcher into `cyrus_common.py`. Currently ChatWatcher lives in `cyrus_brain.py:403-633`.

If the builder runs before 018 is complete, it must create the minimal directory structure (`cyrus2/tests/__init__.py`) and ensure `pythonpath` is configured. If 005 is not complete, import ChatWatcher from `cyrus_brain` directly.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/tests/test_chat_extraction.py` | Does not exist | Create with 15 test cases |
| `cyrus2/tests/` directory | Does not exist (created by issue 018) | Verify exists; create if missing |
| `conftest.py` `mock_uia_element` fixture | Does not exist | Add to conftest.py (create file if missing) |
| pytest `pythonpath = [".."]` | Defined in plan 018's pyproject.toml config | Verify; add if missing |
| ChatWatcher importable | Source at `cyrus_brain.py:403-633` (project root) | Import via `pythonpath` config |

## Source Code Under Test

### `ChatWatcher._walk(ctrl, depth=0, max_depth=12, out=None)` — cyrus_brain.py:470-489

Recursively traverses a UIA element tree depth-first. Produces a flat list of `(depth: int, control_type: str, name: str)` tuples.

Key behaviors:
- Skips elements with `Name` shorter than 4 characters
- Stops recursion at `max_depth` (default 12)
- Navigates via `ctrl.GetFirstChildControl()` → `ctrl.GetNextSiblingControl()` linked-list pattern
- Gracefully catches exceptions at every access (Name, ControlTypeName, GetFirstChildControl, GetNextSiblingControl) — never crashes on a broken UIA node

```python
def _walk(self, ctrl, depth=0, max_depth=12, out=None):
    if out is None:
        out = []
    if depth > max_depth:
        return out
    try:
        name  = (ctrl.Name or "").strip()
        ctype = ctrl.ControlTypeName or ""
        if len(name) >= 4:
            out.append((depth, ctype, name))
    except Exception:
        pass
    try:
        child = ctrl.GetFirstChildControl()
        while child:
            self._walk(child, depth + 1, max_depth, out)
            child = child.GetNextSiblingControl()
    except Exception:
        pass
    return out
```

### `ChatWatcher._extract_response(results)` — cyrus_brain.py:491-531

Takes the flat list from `_walk` and extracts the most recent chat response text.

**Algorithm:**

1. **Find backstop** (`msg_input_pos`): index of first tuple where `ctype == "EditControl"` and `name == "Message input"` (the `_CHAT_INPUT_HINT` constant). If not found → return `""`.

2. **Find start anchor** (`start`): scan `results[:msg_input_pos]` for the **last** `ButtonControl` containing `"Thinking"` in its name. If none found, fall back to the **last** `ButtonControl` with name `== "Message actions"`. If neither found → return `""`.

3. **Extract text** from `results[start + 1 : msg_input_pos]`:
   - **Stop** on any text in `_STOP` set: `{"Edit automatically", "Show command menu (/)", "ctrl esc to focus or unfocus Claude", "Message input"}`
   - **Stop** on `("ButtonControl", "Message actions")` — marks the boundary of the next conversation turn
   - **Skip** text in `_SKIP` set: `{"Thinking", "Message actions", "Copy code to clipboard", "Stop", "Regenerate", "tasks", "New session", "Ask before edits"}`
   - **Skip** names shorter than 4 characters
   - **Type filter**: only keep `"TextControl"` or `"ListItemControl"` — all other control types are ignored
   - **Deduplication**: skip if exact match already in `seen` set, or if text is a substring of any longer already-seen string

4. **Return** `" ".join(parts)` — space-joined extracted text fragments.

```python
def _extract_response(self, results):
    msg_input_pos = next(
        (i for i, (_, ct, tx) in enumerate(results)
         if ct == "EditControl" and tx == _CHAT_INPUT_HINT),
        -1
    )
    if msg_input_pos == -1:
        return ""

    start = -1
    for i, (_, ctype, text) in enumerate(results[:msg_input_pos]):
        if ctype == "ButtonControl" and "Thinking" in text:
            start = i

    if start == -1:
        for i, (_, ctype, text) in enumerate(results[:msg_input_pos]):
            if ctype == "ButtonControl" and text == "Message actions":
                start = i

    if start == -1:
        return ""

    parts: list[str] = []
    seen:  set[str]  = set()

    for _, ctype, text in results[start + 1: msg_input_pos]:
        if text in self._STOP:
            break
        if ctype == "ButtonControl" and text == "Message actions":
            break
        if text in self._SKIP or len(text) < 4:
            continue
        if ctype not in ("TextControl", "ListItemControl"):
            continue
        if text not in seen and not any(text in s for s in seen if len(s) > len(text)):
            seen.add(text)
            parts.append(text)

    return " ".join(parts)
```

### Key Constants

```python
_CHAT_INPUT_HINT = "Message input"          # cyrus_brain.py:69

# Class-level sets on ChatWatcher
_STOP = {"Edit automatically", "Show command menu (/)",
         "ctrl esc to focus or unfocus Claude", "Message input"}
_SKIP = {"Thinking", "Message actions", "Copy code to clipboard",
         "Stop", "Regenerate", "tasks", "New session", "Ask before edits"}
```

## Design Decisions

### 1. Two test layers: `_walk` (mock UIA) + `_extract_response` (crafted tuples)

`_walk` is the UIA-interacting method — it needs `MagicMock` controls simulating the `GetFirstChildControl()`/`GetNextSiblingControl()` linked-list pattern. `_extract_response` is a pure function on the flattened tuple list — no mocking needed, just crafted input data. Testing both layers separately gives maximum coverage with minimum mock complexity.

### 2. Helper function `make_ctrl()` for UIA mock construction

Building linked-list mock trees by hand is error-prone. A shared helper constructs properly linked mock controls:

```python
def make_ctrl(name: str, ctype: str, children: list | None = None) -> MagicMock:
    ctrl = MagicMock()
    ctrl.Name = name
    ctrl.ControlTypeName = ctype
    if children:
        ctrl.GetFirstChildControl.return_value = children[0]
        for i, child in enumerate(children):
            child.GetNextSiblingControl.return_value = (
                children[i + 1] if i + 1 < len(children) else None
            )
    else:
        ctrl.GetFirstChildControl.return_value = None
    return ctrl
```

This goes in the test file as a module-level utility, not in conftest — it's specific to UIA mocking and not useful to other test modules.

### 3. `mock_uia_element` fixture in conftest.py

The issue specifies adding a `mock_uia_element` fixture to conftest.py. This provides a reusable single-element mock:

```python
@pytest.fixture
def mock_uia_element():
    elem = MagicMock()
    elem.Name = "Mock Element"
    elem.ControlTypeName = "TextControl"
    elem.GetFirstChildControl.return_value = None
    elem.GetNextSiblingControl.return_value = None
    return elem
```

Note: the fixture uses the **actual UIA property names** (`Name`, `ControlTypeName`, `GetFirstChildControl`, `GetNextSiblingControl`) matching the real `uiautomation` API — not the Python-style names from the issue template (`name`, `element_type`, `get_children`).

### 4. Import strategy

```python
from cyrus_brain import ChatWatcher
```

If issue 005 has been completed: `from cyrus_common import ChatWatcher`. The builder should check which module exports ChatWatcher at build time.

Importing `cyrus_brain` triggers heavy module-level imports (comtypes, uiautomation, sounddevice, etc.). If these are unavailable in the test environment, the builder must handle import errors — see Import Risk section.

### 5. `@pytest.mark.parametrize` for `_extract_response` tests

Most `_extract_response` tests follow the pattern `(results_list, expected_string)` — ideal for parametrize. The `_walk` tests use individual functions since each requires a different mock tree structure.

### 6. Cache test approach

The actual "cache" in ChatWatcher is comparison-based in the poll loop (`if response != self._last_text`). There is no memoization inside `_extract_response` itself. The cache test verifies that `_extract_response` is **deterministic** — same input always produces the same output — which is the property the poll loop relies on for its cache comparison.

## Acceptance Criteria → Test Mapping

| AC | Requirement | Tests | Count |
|---|---|---|---|
| AC1 | `cyrus2/tests/test_chat_extraction.py` exists with 10+ test cases | File exists, `pytest --collect-only` shows ≥15 items | 15 |
| AC2 | Anchor element detection (~2 cases) | `thinking_anchor`, `message_actions_fallback` | 2 |
| AC3 | Backtrack logic (~3 cases) | `last_thinking_wins`, `stops_at_message_actions_boundary`, `stops_at_stop_word` | 3 |
| AC4 | Response text extraction (~2 cases) | `concatenates_text_controls`, `includes_list_item_controls` | 2 |
| AC5 | Missing element handling (~2 cases) | `no_message_input`, `no_anchor` | 2 |
| AC6 | Cache behavior (~1 case) | `deterministic_same_input` | 1 |
| AC7 | All tests pass: `pytest tests/test_chat_extraction.py -v` | Exit code 0 | — |

Bonus coverage (5 additional cases): `dedup_exact`, `dedup_substring`, `walk_flat_tree`, `walk_nested_hierarchy`, `walk_skips_short_names`

## Test Case Inventory

### `_walk` method — 3 cases (individual test functions)

| # | Test Name | Setup | Expected | Rationale |
|---|---|---|---|---|
| 1 | `test_walk_flat_tree` | Root with 3 children: `("TextControl", "Hello world")`, `("ButtonControl", "Click me here")`, `("TextControl", "Another text")` | `[(0, "PaneControl", root.Name), (1, "TextControl", "Hello world"), (1, "ButtonControl", "Click me here"), (1, "TextControl", "Another text")]` | Verifies depth-first traversal of direct children and correct depth tagging |
| 2 | `test_walk_nested_hierarchy` | Root → child ("TextControl", "Level one text") → grandchild ("ListItemControl", "Deep item here") | Includes `(1, "TextControl", "Level one text")` and `(2, "ListItemControl", "Deep item here")` | Verifies multi-level depth-first recursion |
| 3 | `test_walk_skips_short_names` | Root with children: `("TextControl", "Hi")` (2 chars), `("TextControl", "Good morning")` | Only `"Good morning"` appears in output (root too if name ≥ 4) | Verifies the `len(name) >= 4` filter |

### `_extract_response` method — 12 cases (parametrized + individual)

**Anchor detection (2 cases):**

| # | ID | Results List | Expected | Rationale |
|---|---|---|---|---|
| 4 | `thinking_anchor` | `[(0, "ButtonControl", "Thinking"), (0, "TextControl", "Hello from Claude"), (0, "EditControl", "Message input")]` | `"Hello from Claude"` | Primary anchor: "Thinking" button found, text after it extracted |
| 5 | `message_actions_fallback` | `[(0, "ButtonControl", "Message actions"), (0, "TextControl", "Fallback response"), (0, "EditControl", "Message input")]` | `"Fallback response"` | Secondary anchor: no "Thinking", falls back to "Message actions" |

**Backtrack logic (3 cases):**

| # | ID | Results List | Expected | Rationale |
|---|---|---|---|---|
| 6 | `last_thinking_wins` | `[(0, "ButtonControl", "Thinking (1s)"), (0, "TextControl", "Old response"), (0, "ButtonControl", "Thinking (3s)"), (0, "TextControl", "New response"), (0, "EditControl", "Message input")]` | `"New response"` | Multiple "Thinking" buttons → last one is the most recent response anchor |
| 7 | `stops_at_message_actions_boundary` | `[(0, "ButtonControl", "Thinking"), (0, "TextControl", "Current response"), (0, "ButtonControl", "Message actions"), (0, "TextControl", "Previous response"), (0, "EditControl", "Message input")]` | `"Current response"` | "Message actions" in extraction zone marks boundary of next turn — stops extraction |
| 8 | `stops_at_stop_word` | `[(0, "ButtonControl", "Thinking"), (0, "TextControl", "Some response"), (0, "TextControl", "Edit automatically"), (0, "TextControl", "Should not appear"), (0, "EditControl", "Message input")]` | `"Some response"` | _STOP word terminates extraction immediately |

**Response text extraction (2 cases):**

| # | ID | Results List | Expected | Rationale |
|---|---|---|---|---|
| 9 | `concatenates_text_controls` | `[(0, "ButtonControl", "Thinking"), (0, "TextControl", "First paragraph"), (0, "TextControl", "Second paragraph"), (0, "TextControl", "Third paragraph"), (0, "EditControl", "Message input")]` | `"First paragraph Second paragraph Third paragraph"` | Multiple TextControls space-joined into single response |
| 10 | `includes_list_item_controls` | `[(0, "ButtonControl", "Thinking"), (0, "TextControl", "Here is a list"), (0, "ListItemControl", "Item number one"), (0, "ListItemControl", "Item number two"), (0, "EditControl", "Message input")]` | `"Here is a list Item number one Item number two"` | ListItemControl accepted alongside TextControl |

**Missing element handling (2 cases):**

| # | ID | Results List | Expected | Rationale |
|---|---|---|---|---|
| 11 | `no_message_input` | `[(0, "ButtonControl", "Thinking"), (0, "TextControl", "Orphaned text")]` | `""` | No EditControl backstop → no way to bound extraction → empty string |
| 12 | `no_anchor` | `[(0, "TextControl", "Just some text"), (0, "EditControl", "Message input")]` | `""` | Backstop present but no Thinking/Message actions anchor → empty string |

**Deduplication and filtering (2 cases):**

| # | ID | Results List | Expected | Rationale |
|---|---|---|---|---|
| 13 | `dedup_exact` | `[(0, "ButtonControl", "Thinking"), (0, "TextControl", "Same text here"), (0, "TextControl", "Same text here"), (0, "EditControl", "Message input")]` | `"Same text here"` | Exact duplicate → only first occurrence kept |
| 14 | `dedup_substring` | `[(0, "ButtonControl", "Thinking"), (0, "TextControl", "The full sentence here"), (0, "TextControl", "full sentence"), (0, "EditControl", "Message input")]` | `"The full sentence here"` | "full sentence" is a substring of already-seen "The full sentence here" → skipped |

**Cache/determinism (1 case):**

| # | ID | Setup | Expected | Rationale |
|---|---|---|---|---|
| 15 | `deterministic_same_input` | Call `_extract_response` twice with identical results list | Both calls return identical string | Verifies the pure-function property that the poll loop's cache comparison depends on |

**Total: 15 test cases** (3 walk + 12 extract)

## Implementation Steps

### Step 1: Verify test infrastructure exists

```bash
cd /home/daniel/Projects/barf/cyrus

# Check issue 018 artifacts
test -d cyrus2/tests/ && echo "OK: tests dir" || echo "MISSING: tests dir"
test -f cyrus2/tests/__init__.py && echo "OK: __init__" || echo "MISSING: __init__"
test -f cyrus2/tests/conftest.py && echo "OK: conftest" || echo "MISSING: conftest"
```

If `cyrus2/tests/` doesn't exist, create the minimal structure:

```bash
mkdir -p cyrus2/tests
touch cyrus2/tests/__init__.py
```

If `pythonpath` isn't configured in `pyproject.toml`, ensure it's set so `import cyrus_brain` resolves to the cyrus root.

### Step 2: Add `mock_uia_element` fixture to conftest.py

If `cyrus2/tests/conftest.py` exists (from issue 018), append the fixture. If it doesn't exist, create a minimal conftest:

```python
"""Shared fixtures for cyrus2 test suite."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_uia_element() -> MagicMock:
    """Single mock UIA element with standard properties.

    Properties match the real uiautomation API:
    - Name: element display text
    - ControlTypeName: UIA control type string
    - GetFirstChildControl(): returns None (leaf node)
    - GetNextSiblingControl(): returns None (no siblings)
    """
    elem = MagicMock()
    elem.Name = "Mock Element"
    elem.ControlTypeName = "TextControl"
    elem.GetFirstChildControl.return_value = None
    elem.GetNextSiblingControl.return_value = None
    return elem
```

### Step 3: Create `cyrus2/tests/test_chat_extraction.py`

Write all 15 test cases. Structure:

```python
"""Tier 4 integration tests for ChatWatcher chat extraction.

Tests cover:
    _walk              — UIA tree traversal with mock controls (3 cases)
    _extract_response  — anchor detection, backtrack logic, text extraction,
                         missing elements, deduplication (12 cases)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cyrus_brain import ChatWatcher


# ── Helpers ────────────────────────────────────────────────────────────────────


def make_ctrl(
    name: str, ctype: str, children: list[MagicMock] | None = None,
) -> MagicMock:
    """Build a mock UIA control with linked-list child navigation."""
    ctrl = MagicMock()
    ctrl.Name = name
    ctrl.ControlTypeName = ctype
    if children:
        ctrl.GetFirstChildControl.return_value = children[0]
        for i, child in enumerate(children):
            child.GetNextSiblingControl.return_value = (
                children[i + 1] if i + 1 < len(children) else None
            )
    else:
        ctrl.GetFirstChildControl.return_value = None
    return ctrl


@pytest.fixture
def watcher() -> ChatWatcher:
    """Minimal ChatWatcher instance for calling extraction methods."""
    return ChatWatcher()


# ── _walk tests ────────────────────────────────────────────────────────────────


class TestWalk:
    def test_walk_flat_tree(self, watcher): ...
    def test_walk_nested_hierarchy(self, watcher): ...
    def test_walk_skips_short_names(self, watcher): ...


# ── _extract_response tests ───────────────────────────────────────────────────


class TestExtractResponse:
    # Parametrized tests for the 12 cases from test inventory
    ...
    def test_deterministic_same_input(self, watcher): ...
```

**Key notes for the builder:**

- Import `ChatWatcher` from `cyrus_brain`. If issue 005 is done, import from `cyrus_common` instead.
- `ChatWatcher()` can be constructed with no args — the constructor only initializes polling state, not UIA connections.
- `_walk` is called as `watcher._walk(mock_ctrl)` — it's an instance method but only uses `self` for recursion.
- `_extract_response` is called as `watcher._extract_response(results)` — it accesses `self._STOP` and `self._SKIP` (class-level sets).
- The `_CHAT_INPUT_HINT` constant is module-level in `cyrus_brain.py`, not on the class — it's already in scope when `_extract_response` runs.
- All test expected values must match exact space-joining: `" ".join(parts)`.
- For the deduplication substring test: the algorithm checks `text in s for s in seen if len(s) > len(text)` — it skips the new text if it's a substring of any **longer** string already seen. The condition `len(s) > len(text)` means equal-length strings that contain each other are NOT deduplicated.

### Step 4: Run tests and iterate

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_chat_extraction.py -v
```

Expected: 15 tests pass. If any fail, trace the input through the function step by step and adjust expected values.

### Step 5: Verify test count

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_chat_extraction.py --collect-only -q | tail -1
```

Expected: `15 tests collected` (or more if builder adds bonus cases)

### Step 6: Run subset commands from acceptance criteria

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_chat_extraction.py::TestExtractResponse -v
pytest tests/test_chat_extraction.py -k "anchor or fallback" -v
pytest tests/test_chat_extraction.py -k "backtrack or stop" -v
pytest tests/test_chat_extraction.py -k "missing or no_" -v
pytest tests/test_chat_extraction.py::TestWalk -v
```

All subsets should pass independently.

## Import Risk

`cyrus_brain.py` has heavy module-level imports: `comtypes`, `uiautomation`, `sounddevice`, `numpy`, `torch`, `pygetwindow`. If any are missing in the test environment, the import will fail.

**Mitigation:** The project runs on the dev machine (Windows) with all deps installed. If imports fail, the builder should:
1. First try `pip install -r requirements.txt` to ensure production deps are present.
2. If specific modules are unavailable (e.g., Linux CI without `comtypes`), the builder can either:
   - Add `try/except` guards around the module-level imports in `cyrus_brain.py` (acceptable — the functions under test don't use those modules)
   - Or mock the problematic imports at test time with `unittest.mock.patch.dict('sys.modules', ...)`
3. If neither approach works, flag as STUCK.

## Files Created/Modified

| File | Action | Description |
|---|---|---|
| `cyrus2/tests/test_chat_extraction.py` | **Create** | 15 test cases: 3 `_walk` + 12 `_extract_response` |
| `cyrus2/tests/conftest.py` | **Create/Modify** | Add `mock_uia_element` fixture |
| `cyrus2/tests/` directory | **Verify** | Must exist (from issue 018) |
| `cyrus2/tests/__init__.py` | **Verify** | Must exist (from issue 018) |
