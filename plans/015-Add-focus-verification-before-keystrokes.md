# Implementation Plan: Add focus verification before keystrokes

**Issue**: [015-Add-focus-verification-before-keystrokes](/home/daniel/Projects/barf/cyrus/issues/015-Add-focus-verification-before-keystrokes.md)
**Created**: 2026-03-16
**PROMPT**: PROMPT_plan (barf auto/plan)

## Gap Analysis

**Already exists**:
- Inline, best-effort focus via `win.activate()` and `vscode.SetFocus()` in try/except blocks that **silently swallow failures** — no verification that focus actually landed
- Active window tracker thread (`_start_active_tracker()`) polling `gw.getActiveWindow()` every 0.5s — only for project name tracking, NOT used as a safety gate
- `uiautomation==2.0.29` imported as `auto` in both `cyrus_brain.py` and `cyrus_common.py`
- `pygetwindow` used for window enumeration/activation
- COM STA thread for UIA operations (`_submit_worker`)
- Logging infrastructure (`logging` module) in both files

**Needs building**:
1. A centralized `_assert_vscode_focus()` guard function using UIAutomation `GetFocusedControl()`
2. Guard calls at 7 pyautogui call sites across 2 files (10 total pyautogui calls, grouped by sequence)
3. Graceful error handling at each call site (catch RuntimeError, log, abort operation)
4. Unit tests with mocked UIAutomation (tests run on Linux CI — no live UIA)

## Approach

**Define `_assert_vscode_focus()` in `cyrus2/cyrus_common.py`** (not `cyrus_brain.py`) because:
- `cyrus_brain.py` imports from `cyrus_common.py`, not the reverse
- Both files need the function — defining in `cyrus_common.py` avoids circular imports
- `cyrus_common.py` is the shared utilities module (Issue 005 extracted it for this purpose)

**UIAutomation approach** (per acceptance criteria "Uses UIAutomation"):
- Use `auto.GetFocusedControl()` to get the deepest focused UI element
- Walk up the UIA tree via `GetParentControl()` to find the top-level `WindowControl`
- Check if the window name contains "Visual Studio Code"
- `log.error()` the mismatched window name, then raise `RuntimeError`

**Call granularity**: Guard before each keystroke **sequence** (group), plus re-check before Enter (commit actions). Not before every individual `pyautogui.*` call — the inter-call gaps within a sequence are small enough that excessive UIA COM calls would slow operations without meaningful safety gain.

**Root `main.py` NOT modified**: Only `cyrus2/` files modified, per the project's refactoring direction. Build/test/lint in `.barfrc` target `cyrus2/` exclusively.

## Rules to Follow

- `.claude/rules/` — Empty (no project rules currently defined)
- `docs/12-code-audit.md` H2 finding — source requirement for this issue
- Python Expert AGENTS.md — type hints, docstrings (Google style), no bare except, EAFP pattern

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Function implementation | `python-expert` skill | Type hints, docstrings, error handling patterns |
| Test writing | `python-testing` skill | Mock-based unit tests, pytest/unittest patterns |
| Lint validation | `python-linting` skill | `ruff check` and `ruff format --check` |

## Prioritized Tasks

- [x] 1. **Define `_assert_vscode_focus()` in `cyrus2/cyrus_common.py`**
  - Module-level function (not inside a class)
  - Use `auto.GetFocusedControl()` + `GetParentControl()` walk to find top-level window
  - Check window `Name` contains "Visual Studio Code"
  - `log.error("Focus mismatch: %s (not VS Code)", window_name)` before raising
  - Raise `RuntimeError(f"VS Code not focused, got {window_name}")`
  - Handle UIA exceptions: log warning, re-raise as RuntimeError
  - Added `import logging` and `log = logging.getLogger("cyrus.common")` to cyrus_common.py

- [x] 2. **Guard pyautogui calls in `cyrus2/cyrus_brain.py` — `_submit_to_vscode_impl()`**
  - Import `_assert_vscode_focus` from `cyrus_common`
  - Guard before `pyautogui.click(*coords)` — sequence start
  - Guard before `pyautogui.press("enter")` — commit action
  - Wrap in try/except RuntimeError → log (exc_info=True) and return False

- [x] 3. **Guard pyautogui calls in `cyrus2/cyrus_common.py` — `PermissionWatcher.handle_response()`**
  - Single guard at top of method (after pending check) covering all pyautogui paths
  - Aborts cleanly: clears `_pending`/`_allow_btn`, returns True (consumed)

- [x] 4. **Guard pyautogui calls in `cyrus2/cyrus_common.py` — `PermissionWatcher.handle_prompt_response()`**
  - Single guard at top of method (after pending check) covering escape and ctrl+a/v/enter paths
  - Aborts cleanly: clears `_prompt_pending`/`_prompt_input_ctrl`, returns True (consumed)

- [x] 5. **Write unit tests in `cyrus2/tests/test_015_focus_verification.py`**
  - Follow existing pattern: unittest.TestCase, AST structural analysis, mocked Windows deps
  - All 23 tests listed in Acceptance-Driven Tests table pass
  - Match naming convention: `test_015_focus_verification.py`

- [x] 6. **Run validation: ruff check, ruff format, pytest**
  - All 324 tests pass (up from ~300 before this issue)
  - New test file has 100% pass rate (23/23)
  - ruff check: all checks passed
  - ruff format: 20 files already formatted

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| Function `_assert_vscode_focus()` created | `test_function_exists_and_callable` | unit |
| Uses UIAutomation to get focused window | `test_calls_get_focused_control` | unit (mock) |
| Verifies title contains "Visual Studio Code" | `test_passes_when_vscode_focused` | unit (mock) |
| Raises RuntimeError if focus is not VS Code | `test_raises_when_wrong_window_focused` | unit (mock) |
| Logs which window had focus on failure | `test_logs_focus_mismatch_on_failure` | unit (mock+assertLogs) |
| Called before every pyautogui keystroke sequence | `test_assert_precedes_pyautogui_in_brain` + `test_assert_precedes_pyautogui_in_common` | structural (AST) |
| All clipboard ops preceded by focus check | `test_clipboard_ops_preceded_by_focus_check` | structural (AST) |
| No misdirected input due to focus change | `test_submit_aborts_on_focus_failure` + `test_permission_aborts_on_focus_failure` | unit (mock) |
| Existing functionality preserved | `test_submit_succeeds_when_focused` + all existing tests pass | unit + regression |
| Handles UIA exceptions gracefully | `test_uia_exception_reraises_as_runtime_error` | unit (mock) |

**Status**: All tests implemented and passing (23/23). ✅

## Validation (Backpressure)

- Lint: `BUILD_COMMAND`
- Format: `CHECK_COMMAND`
- Tests: `TEST_COMMAND`
- All existing tests must continue to pass
- New test file `test_015_focus_verification.py` must have 100% pass rate

## Files to Create/Modify

- `cyrus2/cyrus_common.py` — Add `_assert_vscode_focus()` function definition (module-level)
- `cyrus2/cyrus_brain.py` — Import `_assert_vscode_focus` from cyrus_common, call before keystroke sequences in `_submit_to_vscode_impl()`
- `cyrus2/tests/test_015_focus_verification.py` — **NEW** — Unit tests for focus verification

## Key Decisions

1. **Function location**: `cyrus_common.py` instead of `cyrus_brain.py` — avoids circular import since brain imports from common. Both files need the function.

2. **UIAutomation API**: `auto.GetFocusedControl()` + parent walk — standard way to identify focused top-level window via `uiautomation`. Alternative `pygetwindow.getActiveWindow()` (simpler, already used) was rejected because acceptance criteria explicitly requires UIAutomation.

3. **Call granularity**: Guard before each keystroke *sequence* start, plus re-check before Enter (commit actions). 7 guard points total across 10 pyautogui calls. The ctrl+v at brain:699 falls between guards at 688 (click) and 707 (enter) — ~200ms gap acceptable per sequence-group rationale.

4. **Error handling**: RuntimeError caught at each call site, logged, and operation aborted gracefully. No crash, no silent continuation.

5. **Root `main.py` not modified**: Only `cyrus2/` files modified. The `main.py` equivalents referenced in the issue are now in `cyrus2/cyrus_common.py` (PermissionWatcher).

6. **Test approach**: Mock-based unit tests + AST structural analysis (no live UIA — CI runs on Linux). Follows patterns from `test_007_command_handlers.py` and `test_008_init_functions.py`.

## Call Site Reference (verified 2026-03-16)

| # | File | Line | Call | Guard Before |
|---|------|------|------|-------------|
| 1 | cyrus_brain.py | 688 | `pyautogui.click(*coords)` | ✅ New guard |
| 2 | cyrus_brain.py | 699 | `pyautogui.hotkey("ctrl", "v")` | Covered by guard #1 (same sequence) |
| 3 | cyrus_brain.py | 707 | `pyautogui.press("enter")` | ✅ New guard (re-verify before commit) |
| 4 | cyrus_common.py | 996 | `pyautogui.press("1")` | ✅ New guard |
| 5 | cyrus_common.py | 1005 | `pyautogui.press("enter")` | ✅ New guard |
| 6 | cyrus_common.py | 1017 | `pyautogui.press("escape")` | ✅ New guard |
| 7 | cyrus_common.py | 1040 | `pyautogui.press("escape")` | ✅ New guard |
| 8 | cyrus_common.py | 1047 | `pyautogui.hotkey("ctrl", "a")` | ✅ New guard |
| 9 | cyrus_common.py | 1049 | `pyautogui.hotkey("ctrl", "v")` | Covered by guard #8 (same sequence) |
| 10 | cyrus_common.py | 1051 | `pyautogui.press("enter")` | Covered by guard #8 (same sequence) |
