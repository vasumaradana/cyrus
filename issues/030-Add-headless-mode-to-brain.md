---
id=030-Add-headless-mode-to-brain
title=Issue 030: Add Headless Mode to Brain
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=44815
total_output_tokens=5
total_duration_seconds=101
total_iterations=1
run_count=1
---

# Issue 030: Add Headless Mode to Brain

## Sprint
Sprint 5 — Docker & Extension

## Priority
Critical

## References
- docs/13-docker-containerization.md — Phase 1 (Add HEADLESS Mode)

## Description
Add `CYRUS_HEADLESS=1` environment variable guard in `cyrus2/cyrus_brain.py` to skip all Windows-specific GUI imports (comtypes, pyautogui, pyperclip, pygetwindow, uiautomation). In headless mode, all UIA-based paths (session discovery, active window tracking, permission detection) are skipped; companion extension provides these via TCP messages on port 8770.

## Blocked By
- Issue 031 (companion extension registration)
- Issue 034 (brain registration listener)

## Acceptance Criteria
- [ ] `HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1"` at top of cyrus2/cyrus_brain.py
- [ ] All Windows imports guarded: `if not HEADLESS: import comtypes, pyautogui, ...`
- [ ] `_vs_code_windows()` returns companion-registered sessions when HEADLESS (skips pygetwindow)
- [ ] `_start_active_tracker()` disabled in HEADLESS mode
- [ ] ChatWatcher uses hook-only path (Stop event from :8767) in HEADLESS
- [ ] PermissionWatcher uses companion messages instead of UIA polling in HEADLESS
- [ ] `_submit_to_vscode_impl()` uses companion extension only in HEADLESS
- [ ] Brain starts without errors when CYRUS_HEADLESS=1

## Implementation Steps
1. Add at top of `cyrus2/cyrus_brain.py` (after imports of os, sys, json, etc.):
   ```python
   HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1"

   if not HEADLESS:
       import comtypes
       from comtypes.client import CreateObject
       import pyautogui
       import pygetwindow as gw
       import pyperclip
       from uiautomation import InitializeUIAutomation, Engine
       # ... rest of UIA imports
   ```
2. Refactor `_vs_code_windows()`:
   ```python
   def _vs_code_windows():
       if HEADLESS:
           # Return companion-registered sessions (from _registered_sessions)
           return list(_registered_sessions.keys())
       else:
           # Original UIA path: use pygetwindow
           ...
   ```
3. Refactor `_start_active_tracker()`:
   ```python
   def _start_active_tracker():
       if HEADLESS:
           # Skip — companion sends focus/blur messages
           return
       else:
           # Original gw.getActiveWindow() polling
           ...
   ```
4. Refactor ChatWatcher to use hook-only path in HEADLESS:
   - In HEADLESS mode, ignore UIA tree polling
   - Rely on Stop event from hook (already implemented on :8767)
5. Refactor PermissionWatcher in HEADLESS:
   - Skip UIA tree polling for permission dialogs
   - Wait for `permission_respond` messages from companion extension
   - Do NOT auto-click buttons; companion handles clicks
6. Refactor `_submit_to_vscode_impl()`:
   - In HEADLESS mode, use only companion extension path
   - Skip UIA fallback and pyautogui paths
7. Add a startup check:
   ```python
   if HEADLESS:
       print("Brain running in HEADLESS mode — Windows GUI paths disabled")
       print("Companion extension registration required for full functionality")
   ```

## Files to Create/Modify
- Modify: `cyrus2/cyrus_brain.py` (add HEADLESS guard, refactor 5 components)

## Testing
1. Run `python cyrus2/cyrus_brain.py` — verify starts normally (Windows imports succeed on Windows)
2. Run `CYRUS_HEADLESS=1 python cyrus2/cyrus_brain.py` on Windows — verify starts without Windows import errors
3. Run `CYRUS_HEADLESS=1 python cyrus2/cyrus_brain.py` on Linux — verify starts (no Windows imports attempted)
4. In HEADLESS mode, verify _vs_code_windows() returns empty list (before companion registers)
5. In HEADLESS mode, verify active tracker thread doesn't start
6. In HEADLESS mode, attempt to trigger permission via hook — verify ChatWatcher responds via Stop event

## Stage Log

### GROOMED — 2026-03-11 18:47:46Z

- **From:** NEW
- **Duration in stage:** 101s
- **Input tokens:** 44,815 (final context: 44,815)
- **Output tokens:** 5
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
