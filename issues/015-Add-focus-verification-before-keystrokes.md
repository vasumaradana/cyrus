---
id=015-Add-focus-verification-before-keystrokes
title=Issue 015: Add focus verification before keystrokes
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=45927
total_output_tokens=8
total_duration_seconds=70
total_iterations=1
run_count=1
---

# Issue 015: Add focus verification before keystrokes

## Sprint
Sprint 2 — Quality & Safety

## Priority
High

## References
- docs/12-code-audit.md — H2 Security Clipboard Manipulation Without Focus Verification

## Description
Create a `_assert_vscode_focus()` guard function that verifies VS Code has window focus immediately before keystroke sequences. This prevents misdirected input if focus changes mid-operation. Function will be called before Ctrl+A, Ctrl+V, Escape and other pyautogui keyboard operations.

## Blocked By
- None

## Acceptance Criteria
- [ ] Function `_assert_vscode_focus()` created in `cyrus2/cyrus_brain.py`
- [ ] Uses UIAutomation to get currently focused window
- [ ] Verifies focus window title contains "Visual Studio Code" or similar
- [ ] Raises `RuntimeError` if focus is not VS Code
- [ ] Called before every pyautogui keystroke sequence
- [ ] Called in locations: `cyrus_brain.py:928` (clipboard read/write) and main.py equivalents
- [ ] Logs which window had focus if assertion fails
- [ ] All clipboard manipulation operations preceded by focus check
- [ ] No misdirected input can occur due to focus change
- [ ] Existing functionality preserved (only adds safety gate)

## Implementation Steps
1. Add `_assert_vscode_focus()` function to `cyrus2/cyrus_brain.py`:
   ```python
   def _assert_vscode_focus():
       """Verify VS Code has window focus. Raise RuntimeError if not."""
       try:
           # Get focused window from UIAutomation
           focused_window = ...  # UIAutomation call
           if "Visual Studio Code" not in focused_window.name:
               log.error("Focus mismatch: %s (not VS Code)", focused_window.name)
               raise RuntimeError(f"VS Code not focused, got {focused_window.name}")
       except Exception as e:
           log.warning("Could not verify focus: %s", e)
           raise
   ```
2. Locate clipboard/keystroke operations in `cyrus_brain.py:928` (and main.py if used)
3. Add call to `_assert_vscode_focus()` immediately before first pyautogui keystroke
4. Catch `RuntimeError` and log/abort gracefully
5. Add logging statement showing which window had focus on failure
6. Test focus verification works correctly

## Files to Create/Modify
- `cyrus2/cyrus_brain.py` — add `_assert_vscode_focus()` function and call it

## Testing
```bash
# Focus VS Code and run operation
python cyrus2/cyrus_brain.py &
# Send text command while VS Code is focused
# Expected: operation succeeds without logs

# Blur VS Code to different window and run operation
# Switch focus away from VS Code before operation completes
# Expected: RuntimeError logged, operation aborted gracefully

# Verify log shows which window was focused
CYRUS_LOG_LEVEL=DEBUG python cyrus2/cyrus_brain.py 2>&1 | grep "Focus mismatch"
# Expected: message identifies wrong window
```

## Stage Log

### GROOMED — 2026-03-11 18:19:03Z

- **From:** NEW
- **Duration in stage:** 70s
- **Input tokens:** 45,927 (final context: 45,927)
- **Output tokens:** 8
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
