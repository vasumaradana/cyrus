# Plan 023: Write test_permission_keywords.py (Tier 3)

## Summary

Create `cyrus2/tests/test_permission_keywords.py` with 14 parametrized test cases covering `PermissionWatcher.handle_response()` keyword matching logic. Mock `pyautogui` and `uiautomation` to isolate keyword matching from UI automation side effects. Test all 9 ALLOW_WORDS, all 6 DENY_WORDS, edge cases (empty input, ambiguous input, mixed keywords), case-insensitive matching, and state transitions (`_pending` cleared after match).

## Prerequisites

- **Issue 018** (state: PLANNED) — creates `cyrus2/tests/` directory, `conftest.py`, `pytest.ini` with `pythonpath = ..`. If not yet built, the builder must create the minimal directory structure and pytest config.
- **Issue 005** (state: PLANNED) — cyrus_common.py foundation. `PermissionWatcher` has no dependency on it. The issue reference to `cyrus_permission.py` is aspirational — the class lives in `cyrus_brain.py` today.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/tests/test_permission_keywords.py` | Does not exist | Create with 14 test cases |
| `cyrus2/tests/` directory | Does not exist (created by issue 018) | Verify exists; create if missing |
| `cyrus2/tests/conftest.py` | Does not exist (created by issue 018) | Verify exists; not needed for this test file (no fixtures used) |
| `pytest.ini` with `pythonpath = ..` | Does not exist (created by issue 018) | Verify exists; create if missing |
| `cyrus_brain.py` importable | Source at cyrus root | Import via `pythonpath = ..` in pytest config |
| `pyautogui` + `uiautomation` mockable | Module-level imports in `cyrus_brain.py` | Patch before import or mock at test level |

## Source Code Under Test

### `PermissionWatcher` class — cyrus_brain.py:638-915

#### Constants (lines 643-644)

```python
ALLOW_WORDS = {"yes", "allow", "sure", "ok", "okay", "proceed", "yep", "yeah", "go"}
DENY_WORDS  = {"no", "deny", "cancel", "stop", "nope", "reject"}
```

#### `handle_response(self, text: str) -> bool` — lines 876-915

```python
def handle_response(self, text: str) -> bool:
    if not self._pending or not self._allow_btn:
        return False
    words = set(text.lower().strip().split())
    if words & self.ALLOW_WORDS:
        # ... approve action (click button or press "1") ...
        self._pending   = False
        self._allow_btn = None
        return True
    if words & self.DENY_WORDS:
        # ... deny action (press Escape) ...
        self._pending   = False
        self._allow_btn = None
        return True
    return False
```

**Key behaviors:**

1. **Guard clause**: Returns `False` immediately if `_pending` is `False` or `_allow_btn` is falsy
2. **Word splitting**: `text.lower().strip().split()` — case-insensitive, whitespace-tokenized
3. **ALLOW priority**: ALLOW_WORDS checked **before** DENY_WORDS — if both present, allow wins
4. **State reset**: After any match (allow or deny), sets `_pending = False` and `_allow_btn = None`
5. **Return value**: `True` if a keyword matched (action taken), `False` otherwise

**Side effects to mock:**
- `pyautogui.press("1")` or `pyautogui.press("enter")` — allow path
- `pyautogui.press("escape")` — deny path
- `auto.WindowControl(...)` — UIA window lookup for focus management
- `self._allow_btn.Click()` — button-click path (when `_allow_btn` is not `"keyboard"`)

## Design Decisions

### 1. Mock strategy: patch `pyautogui` and `auto.WindowControl`

The test focuses on **keyword matching correctness** and **state transitions**, not UI automation. Side effects are mocked away:

- `pyautogui.press` → patched to no-op (or `MagicMock`)
- `auto.WindowControl` → patched to return a mock with `Exists()` returning `False`

Using `_allow_btn = "keyboard"` for all tests takes the simplest code path (no `.Click()` needed). This keeps tests focused on keyword logic.

### 2. Import strategy

```python
from cyrus_brain import PermissionWatcher
```

The issue references `from cyrus_permission import ...` but no such module exists. `PermissionWatcher`, `ALLOW_WORDS`, and `DENY_WORDS` all live in `cyrus_brain.py`. Import from there. Access constants via `PermissionWatcher.ALLOW_WORDS` and `PermissionWatcher.DENY_WORDS` (class attributes).

**Import risk:** `cyrus_brain.py` has heavy module-level imports (`comtypes`, `uiautomation`, `pyautogui`, `pygetwindow`, etc.). These are Windows-only dependencies. On the dev machine (where Cyrus runs), all deps should be installed. If imports fail, flag as STUCK — the fix belongs in a separate issue.

### 3. Test helper: `_make_watcher()` factory

Create a helper that returns a `PermissionWatcher` instance pre-configured for testing:

```python
def _make_watcher(pending: bool = True, allow_btn: str = "keyboard") -> PermissionWatcher:
    pw = PermissionWatcher(project_name="test-project")
    pw._pending = pending
    pw._allow_btn = allow_btn
    return pw
```

This sets `_pending = True` and `_allow_btn = "keyboard"` (truthy) so the guard clause passes and the keyboard code path is taken. Tests that need `_pending = False` override explicitly.

### 4. Parametrize by category

Three test functions, matching the issue's groupings:
- `test_allow_words` — 5 cases for affirmative responses
- `test_deny_words` — 5 cases for negative responses
- `test_edge_cases` — 4 cases for edge/ambiguous scenarios

Plus a separate non-parametrized test for case-insensitive verification across both sets, as the case-insensitivity is a cross-cutting concern.

### 5. Assertion pattern

- **Return value**: `assert pw.handle_response(text) is expected_result`
- **State cleared on match**: `assert pw._pending is False` and `assert pw._allow_btn is None` after True result
- **State preserved on no-match**: `assert pw._pending is True` after False result
- **Side effects called**: `mock_press.assert_called()` on match, `mock_press.assert_not_called()` on no-match

### 6. No conftest fixtures needed

Tier 3 keyword tests need no shared fixtures. All setup is local — creating `PermissionWatcher` instances and patching modules. This is the same pattern as Tier 1 tests.

## Acceptance Criteria → Test Mapping

| AC | Requirement | Verification |
|---|---|---|
| AC1 | `cyrus2/tests/test_permission_keywords.py` exists with 12+ test cases | File exists, `pytest --collect-only` shows 14 items |
| AC2 | Tests verify ALLOW_WORDS matching (~5 cases) | `test_allow_words` — 5 parametrized cases |
| AC3 | Tests verify DENY_WORDS matching (~5 cases) | `test_deny_words` — 5 parametrized cases |
| AC4 | Edge cases handled (~2 cases) | `test_edge_cases` — 4 parametrized cases (exceeds requirement) |
| AC5 | Case-insensitive matching verified | `test_case_insensitive` — dedicated test with multiple assertions |
| AC6 | All tests pass: `pytest tests/test_permission_keywords.py -v` | Exit code 0, 14+ passed |

## Test Case Inventory

### `test_allow_words` — 5 cases

| ID | Input | Expected return | Rationale |
|---|---|---|---|
| `yes` | `"yes"` | `True` | Basic affirmative — single exact match |
| `sure_in_phrase` | `"sure thing"` | `True` | "sure" is in ALLOW_WORDS, "thing" is noise |
| `okay_in_phrase` | `"okay go ahead"` | `True` | "okay" and "go" both match — multiple allow words |
| `yep` | `"yep"` | `True` | Informal affirmative variation |
| `proceed` | `"please proceed"` | `True` | "proceed" matches, "please" is noise |

**State assertions:** After each True return, verify `pw._pending is False` and `pw._allow_btn is None`.
**Side effect assertion:** `pyautogui.press` called (keyboard path: called with `"1"`).

### `test_deny_words` — 5 cases

| ID | Input | Expected return | Rationale |
|---|---|---|---|
| `no` | `"no"` | `True` | Basic negative — single exact match |
| `nope` | `"nope"` | `True` | Informal negative |
| `cancel` | `"cancel that"` | `True` | "cancel" matches, "that" is noise |
| `stop` | `"stop"` | `True` | Direct deny word |
| `reject` | `"reject it"` | `True` | "reject" matches, "it" is noise |

**State assertions:** After each True return, verify `pw._pending is False` and `pw._allow_btn is None`.
**Side effect assertion:** `pyautogui.press` called with `"escape"`.

### `test_edge_cases` — 4 cases

| ID | Input | Expected return | Rationale |
|---|---|---|---|
| `empty_string` | `""` | `False` | No words to match |
| `ambiguous_maybe` | `"maybe later"` | `False` | No allow/deny keywords present |
| `mixed_allow_deny` | `"yes no"` | `True` (allow) | Both keywords present — ALLOW checked first wins |
| `not_pending` | `"yes"` (with `_pending=False`) | `False` | Guard clause: not pending → immediate False |

**State assertions for False cases:** `pw._pending` unchanged (True for empty/ambiguous, False for not_pending).
**State assertions for mixed case:** `pw._pending is False` (allow matched first).

### `test_case_insensitive` — 1 test function (non-parametrized, multiple assertions)

Tests case-insensitivity for both allow and deny:
- `"YES"` → `True` (uppercase allow)
- `"No"` → `True` (title-case deny)
- `"SuRe"` → `True` (mixed-case allow)
- `"REJECT"` → `True` (uppercase deny)

Each assertion uses a fresh `_make_watcher()` instance.

**Total: 14 test cases** (5 + 5 + 4 parametrized cases + 1 multi-assert test = 15 `pytest` items if case_insensitive counts as 1, or 14 if counted by test function invocations)

## Implementation Steps

### Step 1: Verify test infrastructure exists

```bash
cd /home/daniel/Projects/barf/cyrus

# Check issue 018 artifacts
test -d cyrus2/tests/ && echo "OK: tests dir" || echo "MISSING: tests dir"
test -f cyrus2/tests/__init__.py && echo "OK: __init__" || echo "MISSING: __init__"
test -f cyrus2/pytest.ini && echo "OK: pytest.ini" || echo "MISSING: pytest.ini"
```

If `cyrus2/tests/` doesn't exist, create the minimal structure:

```bash
mkdir -p cyrus2/tests
touch cyrus2/tests/__init__.py
```

If `pytest.ini` doesn't exist, create it:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
pythonpath = ..
```

**Critical:** `pythonpath = ..` adds the cyrus root to `sys.path` so `from cyrus_brain import PermissionWatcher` resolves correctly from inside `cyrus2/tests/`.

### Step 2: Create `cyrus2/tests/test_permission_keywords.py`

Write all 14+ test cases. Complete file structure:

```python
"""Tier 3 keyword matching tests for PermissionWatcher.handle_response().

Tests cover:
    ALLOW_WORDS  — affirmative responses: yes, sure, okay, yep, proceed
    DENY_WORDS   — negative responses: no, nope, cancel, stop, reject
    Edge cases   — empty, ambiguous, mixed keywords, not-pending guard
    Case         — case-insensitive matching across both word sets

Mocking strategy:
    - pyautogui.press → MagicMock (prevents actual keystrokes)
    - uiautomation.WindowControl → MagicMock (prevents UIA window lookups)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cyrus_brain import PermissionWatcher


def _make_watcher(pending: bool = True, allow_btn: str = "keyboard") -> PermissionWatcher:
    """Create a PermissionWatcher pre-configured for keyword testing."""
    pw = PermissionWatcher(project_name="test-project")
    pw._pending = pending
    pw._allow_btn = allow_btn
    return pw


# --- ALLOW_WORDS matching ---

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("yes", True, id="yes"),
        pytest.param("sure thing", True, id="sure_in_phrase"),
        pytest.param("okay go ahead", True, id="okay_in_phrase"),
        pytest.param("yep", True, id="yep"),
        pytest.param("please proceed", True, id="proceed"),
    ],
)
def test_allow_words(text: str, expected: bool) -> None:
    pw = _make_watcher()
    with patch("cyrus_brain.pyautogui") as mock_pyautogui, \
         patch("cyrus_brain.auto.WindowControl", return_value=MagicMock(Exists=MagicMock(return_value=False))):
        result = pw.handle_response(text)
    assert result is expected
    assert pw._pending is False
    assert pw._allow_btn is None


# --- DENY_WORDS matching ---

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("no", True, id="no"),
        pytest.param("nope", True, id="nope"),
        pytest.param("cancel that", True, id="cancel"),
        pytest.param("stop", True, id="stop"),
        pytest.param("reject it", True, id="reject"),
    ],
)
def test_deny_words(text: str, expected: bool) -> None:
    pw = _make_watcher()
    with patch("cyrus_brain.pyautogui") as mock_pyautogui, \
         patch("cyrus_brain.auto.WindowControl", return_value=MagicMock(Exists=MagicMock(return_value=False))):
        result = pw.handle_response(text)
    assert result is expected
    assert pw._pending is False
    assert pw._allow_btn is None
    mock_pyautogui.press.assert_called_with("escape")


# --- Edge cases ---

@pytest.mark.parametrize(
    ("text", "pending", "expected"),
    [
        pytest.param("", True, False, id="empty_string"),
        pytest.param("maybe later", True, False, id="ambiguous_maybe"),
        pytest.param("yes no", True, True, id="mixed_allow_deny"),
        pytest.param("yes", False, False, id="not_pending"),
    ],
)
def test_edge_cases(text: str, pending: bool, expected: bool) -> None:
    pw = _make_watcher(pending=pending)
    with patch("cyrus_brain.pyautogui") as mock_pyautogui, \
         patch("cyrus_brain.auto.WindowControl", return_value=MagicMock(Exists=MagicMock(return_value=False))):
        result = pw.handle_response(text)
    assert result is expected
    if not expected:
        # State unchanged when no match
        assert pw._pending is pending
    else:
        # State cleared on match
        assert pw._pending is False
        assert pw._allow_btn is None


# --- Case-insensitive matching ---

def test_case_insensitive() -> None:
    cases = [
        ("YES", True),     # uppercase allow
        ("No", True),      # title-case deny
        ("SuRe", True),    # mixed-case allow
        ("REJECT", True),  # uppercase deny
    ]
    for text, expected in cases:
        pw = _make_watcher()
        with patch("cyrus_brain.pyautogui"), \
             patch("cyrus_brain.auto.WindowControl", return_value=MagicMock(Exists=MagicMock(return_value=False))):
            result = pw.handle_response(text)
        assert result is expected, f"Failed for input {text!r}"
        assert pw._pending is False
```

**Key implementation notes for the builder:**

- Patch `cyrus_brain.pyautogui` (not `pyautogui` directly) — the module is imported at the top of `cyrus_brain.py`, so patch where it's looked up.
- Patch `cyrus_brain.auto.WindowControl` — same principle, `auto` is the `uiautomation` module imported in `cyrus_brain.py`.
- Use `_allow_btn = "keyboard"` to exercise the simpler keyboard code path. The button-click path is not the focus of keyword tests.
- For `mixed_allow_deny` case: verify that ALLOW wins when both keyword sets are present (ALLOW is checked first in the source).
- For `not_pending` case: `_pending = False` but `_allow_btn = "keyboard"` (truthy) — the guard clause checks `not self._pending` first.
- The `_make_watcher(pending=False)` case should keep `_allow_btn = "keyboard"` (truthy) so the False return is due to `_pending`, not `_allow_btn`.

### Step 3: Run tests and iterate

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_permission_keywords.py -v
```

Expected: 15 test items pass (5 allow + 5 deny + 4 edge + 1 case_insensitive). If any fail, trace the input through `handle_response()` step by step. Common issues:
- Patching the wrong module path for pyautogui or auto
- `_allow_btn` being falsy when it shouldn't be
- Word splitting behavior with whitespace

### Step 4: Verify test count

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_permission_keywords.py --collect-only -q | tail -1
```

Expected: `15 tests collected` (exceeds the 12+ requirement).

### Step 5: Run subset commands from acceptance criteria

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_permission_keywords.py::test_allow_words -v
pytest tests/test_permission_keywords.py -k "deny" -v
pytest tests/test_permission_keywords.py -k "edge or ambiguous" -v
pytest tests/test_permission_keywords.py -k "case" -v
```

All should pass independently.

## Import Risk

**High risk.** `cyrus_brain.py` imports Windows-only modules at module level:

```python
import comtypes                       # Windows COM
import uiautomation as auto           # Windows UI Automation
import pyautogui                      # Cross-platform but needs display
import pygetwindow                    # Windows-only
```

If any of these fail to import, `from cyrus_brain import PermissionWatcher` will raise `ModuleNotFoundError` before any test runs.

**Mitigation options (in order of preference):**

1. **Run on dev machine** — Cyrus is a Windows app; the dev machine has all deps. This is the expected test environment per plan 019's precedent.
2. **If imports fail** — flag as STUCK. The fix (conditional imports or module extraction) is a separate issue, not in scope for this test ticket.

## Files Created/Modified

| File | Action | Description |
|---|---|---|
| `cyrus2/tests/test_permission_keywords.py` | **Create** | 15 test items across 4 test functions (5 allow + 5 deny + 4 edge + 1 case_insensitive) |
| `cyrus2/tests/` directory | **Verify** | Must exist (from issue 018); create if missing |
| `cyrus2/tests/__init__.py` | **Verify** | Must exist (from issue 018); create if missing |
| `cyrus2/pytest.ini` | **Verify** | Must have `pythonpath = ..`; create if missing |
