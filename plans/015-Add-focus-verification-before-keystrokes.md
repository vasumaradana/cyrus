# Plan 015 — Add Focus Verification Before Keystrokes

## Problem

The audit (docs/12-code-audit.md §H2) identified that `pyautogui` sends keystrokes to the OS
foreground window blindly. If focus shifts mid-operation (user Alt+Tab, dialog pop-up, competing
Cyrus session), keystrokes and clipboard paste go to the wrong application. This is a security risk:
misdirected Ctrl+V could paste code into a chat window, email, or terminal.

## Design Decisions

### 1. Use `pygetwindow.getActiveWindow()` for focus verification

The issue says "Uses UIAutomation to get currently focused window". Both `pygetwindow` and
`uiautomation` are already imported. `gw.getActiveWindow()` is the simplest and is already proven
in `_start_active_tracker()` (line 1113). It checks the OS-level foreground window title — exactly
what we need. `auto.GetFocusedControl()` returns the focused *control* (e.g. a text field inside
VS Code), which requires walking up the ancestor tree to find the window — more fragile.

### 2. Function signature

```python
def _assert_vscode_focus(target_sub: str = "") -> None:
```

- `target_sub` (optional): When provided, also verifies the specific VS Code window (e.g.
  `"myproject - Visual Studio Code"`). When omitted, only checks for `VSCODE_TITLE` in the
  foreground window title.
- Raises `RuntimeError` with the actual window title on failure.
- Prints which window had focus on failure (matching acceptance criterion).

### 3. Fix both files

`main.py` and `cyrus_brain.py` have 90% duplicated code (C3 in audit). Until Issue 005 extracts
`cyrus_common.py`, we must add the guard function and its call sites to **both files**. The function
body is identical — copy-paste is the correct approach until dedup happens.

### 4. Graceful abort, not crash

Each call site wraps the focus-assert + keystroke sequence in a try/except. On `RuntimeError`,
the operation is aborted and logged — the system continues running. Permission/prompt state is
reset so a retry is possible.

---

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Verification |
|---|---------------------|--------------|
| 1 | `_assert_vscode_focus()` created in `cyrus_brain.py` | Code inspection |
| 2 | Uses UIAutomation / pygetwindow to get focused window | `gw.getActiveWindow()` call in function body |
| 3 | Verifies title contains "Visual Studio Code" | String check against `VSCODE_TITLE` constant |
| 4 | Raises `RuntimeError` if focus is not VS Code | Try calling with non-VS Code window focused |
| 5 | Called before every pyautogui keystroke sequence | Grep for `pyautogui\.` — every hit preceded by `_assert_vscode_focus()` |
| 6 | Called at `cyrus_brain.py:928` and `main.py` equivalents | Code inspection at all 7 call sites |
| 7 | Logs which window had focus on failure | Print statement includes `active.title` |
| 8 | All clipboard manipulation preceded by focus check | Grep for `pyperclip\.copy` — each preceded by guard |
| 9 | No misdirected input due to focus change | Manual test: Alt+Tab away before operation, verify abort |
| 10 | Existing functionality preserved | Manual test: normal operation with VS Code focused still works |

---

## Implementation Steps

### Step 1: Add `_assert_vscode_focus()` to `cyrus_brain.py`

**File:** `cyrus_brain.py`
**Location:** After the helpers section (after line ~110, near `_extract_project`)

```python
def _assert_vscode_focus(target_sub: str = "") -> None:
    """Verify VS Code has window focus. Raise RuntimeError if not.

    Must be called immediately before any pyautogui keystroke sequence
    to prevent misdirected input if focus changed mid-operation.
    """
    try:
        active = gw.getActiveWindow()
    except Exception as e:
        print(f"[Brain] Could not verify focus: {e}")
        raise RuntimeError(f"Focus verification failed: {e}") from e

    if active is None:
        print("[Brain] Focus mismatch: no active window detected")
        raise RuntimeError("No active window detected")

    title = active.title or ""
    if VSCODE_TITLE not in title:
        print(f"[Brain] Focus mismatch: {title!r} (not VS Code)")
        raise RuntimeError(f"VS Code not focused, got: {title!r}")

    if target_sub and target_sub not in title:
        print(f"[Brain] Focus mismatch: {title!r} (expected {target_sub!r})")
        raise RuntimeError(
            f"Wrong VS Code window: {title!r}, expected: {target_sub!r}"
        )
```

**Verify:** Read file, confirm function exists after helpers.

---

### Step 2: Guard `handle_response()` — Allow via keyboard (cyrus_brain.py)

**File:** `cyrus_brain.py`, lines 880–900
**What:** The Quick Pick keyboard path (`press("1")`) and the Click-fallback path (`press("enter")`).

Insert `_assert_vscode_focus(self._target_sub)` after `vscode.SetFocus()` succeeds, before
`pyautogui.press("1")`. Wrap the press in a try/except that catches `RuntimeError` and aborts.

Same for the Click-fallback `press("enter")` at line 899 — add focus check.

**After:**
```python
if words & self.ALLOW_WORDS:
    print(f"[Brain] → Allowing command ({self.project_name or 'session'})")
    if self._allow_btn == "keyboard":
        vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
        if vscode.Exists(1):
            try:
                vscode.SetFocus()
            except Exception:
                pass
        try:
            _assert_vscode_focus(self._target_sub)
            pyautogui.press("1")
        except RuntimeError:
            print(f"[Brain] Aborted allow — focus lost")
    else:
        clicked = False
        try:
            self._allow_btn.Click()
            clicked = True
        except Exception:
            pass
        if not clicked:
            try:
                _assert_vscode_focus(self._target_sub)
                pyautogui.press("enter")
            except RuntimeError:
                print(f"[Brain] Aborted allow (enter fallback) — focus lost")
    self._pending   = False
    self._allow_btn = None
    return True
```

**Verify:** Focus VS Code, trigger permission → "yes" → operation succeeds. Alt+Tab away, trigger → aborted message printed.

---

### Step 3: Guard `handle_response()` — Deny (cyrus_brain.py)

**File:** `cyrus_brain.py`, lines 903–914
**What:** The `press("escape")` after `SetFocus()` for deny.

```python
if words & self.DENY_WORDS:
    print(f"[Brain] → Cancelling command ({self.project_name or 'session'})")
    vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
    if vscode.Exists(1):
        try:
            vscode.SetFocus()
        except Exception:
            pass
    try:
        _assert_vscode_focus(self._target_sub)
        pyautogui.press("escape")
    except RuntimeError:
        print(f"[Brain] Aborted deny — focus lost")
    self._pending   = False
    self._allow_btn = None
    return True
```

---

### Step 4: Guard `handle_prompt_response()` — Cancel and Input (cyrus_brain.py)

**File:** `cyrus_brain.py`, lines 917–939
**What:** Both the cancel path (`press("escape")`) and the input path (clipboard + hotkeys).

For the cancel path (line 922), we need to find and focus VS Code first, then assert:

```python
def handle_prompt_response(self, text: str) -> bool:
    if not self._prompt_pending or not self._prompt_input_ctrl:
        return False
    cancel = {"cancel", "escape", "never mind", "nevermind", "stop", "dismiss", "close"}
    if text.lower().strip() in cancel:
        try:
            _assert_vscode_focus()
            pyautogui.press("escape")
            print(f"[Brain] → Dismissed prompt ({self.project_name or 'session'})")
        except RuntimeError:
            print(f"[Brain] Aborted prompt dismiss — focus lost")
    else:
        try:
            self._prompt_input_ctrl.SetFocus()
            time.sleep(0.05)
            _assert_vscode_focus()
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.02)
            _assert_vscode_focus()
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.05)
            _assert_vscode_focus()
            pyautogui.press("enter")
            print(f"[Brain] → Prompt answered: {text!r}")
        except RuntimeError:
            print(f"[Brain] Aborted prompt input — focus lost")
        except Exception as e:
            print(f"[Brain] Prompt input error: {e}")
    self._prompt_pending    = False
    self._prompt_input_ctrl = None
    return True
```

**Design note:** Three focus checks in the input path — before Ctrl+A (after clipboard write),
before Ctrl+V (after select-all), and before Enter. This is intentional: each has a `time.sleep()`
gap where focus could shift. The clipboard write (`pyperclip.copy`) itself is safe — it doesn't
go to the foreground window. Only the hotkeys do.

---

### Step 5: Guard `_submit_to_vscode_impl()` (cyrus_brain.py)

**File:** `cyrus_brain.py`, lines 1292–1326
**What:** The click + paste + enter sequence.

```python
# After win.activate() + sleep (lines 1292-1296):
try:
    _assert_vscode_focus()
except RuntimeError:
    print("[!] VS Code lost focus after activate — aborting submit.")
    return False

# ── 3. Click chat input by pixel coords ───────────────────────────
pyautogui.click(*coords)
time.sleep(0.1)

# ── 4. Paste text and submit ─────────────────────────────────────
saved = ""
try:
    saved = pyperclip.paste()
except Exception:
    pass

try:
    _assert_vscode_focus()
except RuntimeError:
    print("[!] VS Code lost focus before paste — aborting submit.")
    try:
        pyperclip.copy(saved)
    except Exception:
        pass
    return False

pyperclip.copy(text)
pyautogui.hotkey("ctrl", "v")
time.sleep(0.15)

try:
    _assert_vscode_focus()
except RuntimeError:
    print("[!] VS Code lost focus before Enter — aborting submit.")
    try:
        pyperclip.copy(saved)
    except Exception:
        pass
    return False

pyautogui.press("enter")
time.sleep(0.05)

try:
    pyperclip.copy(saved)
except Exception:
    pass
return True
```

**Design note:** Three focus gates — after activate (before click), before paste, before Enter.
If abort happens after clipboard was already modified, we restore the saved clipboard.

---

### Step 6: Mirror all changes to `main.py`

**File:** `main.py`

Apply the identical `_assert_vscode_focus()` function definition (same code, same location — near
the helpers section).

Apply equivalent guards at these call sites:

| main.py Location | Equivalent to cyrus_brain.py |
|------------------|------------------------------|
| Lines 865-876: Deny handler | Step 3 |
| Lines 880-904: `handle_prompt_response()` | Step 4 |
| Lines 1289-1306: `submit_to_vscode()` | Step 5 (simpler — no pixel coords, no companion fallback) |

**Note:** main.py's Allow handler (lines 855-863) only uses `self._allow_btn.Click()` — a UIA
click, not a pyautogui keystroke. No focus guard needed there. (Unlike cyrus_brain.py which has
a keyboard Quick Pick path.)

---

### Step 7: Manual verification

Run each test scenario from the issue:

```bash
# 1. Focus VS Code and run operation
python cyrus_brain.py &
# Send a text command while VS Code is focused
# Expected: operation succeeds without focus mismatch logs

# 2. Blur VS Code and run operation
# Switch focus away from VS Code before operation completes
# Expected: RuntimeError logged, operation aborted gracefully

# 3. Verify log shows which window was focused
CYRUS_LOG_LEVEL=DEBUG python cyrus_brain.py 2>&1 | grep "Focus mismatch"
# Expected: message identifies the wrong window's title
```

---

## Files Modified

| File | Change |
|------|--------|
| `cyrus_brain.py` | Add `_assert_vscode_focus()` function + guards at 7 pyautogui call sites |
| `main.py` | Add `_assert_vscode_focus()` function + guards at 5 pyautogui call sites |

## Files NOT Modified

- `cyrus2/cyrus_brain.py` — does not exist (cyrus2/ is empty); the issue path is stale
- `cyrus_voice.py` — no pyautogui usage
- `cyrus_hook.py` — no pyautogui usage
- `cyrus_server.py` — no pyautogui usage
