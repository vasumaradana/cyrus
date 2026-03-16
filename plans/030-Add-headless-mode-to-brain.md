# Plan: 030-Add-headless-mode-to-brain

## Summary

Add `CYRUS_HEADLESS=1` environment variable guard to `cyrus_brain.py` so the brain can start cleanly on non-Windows systems (Linux/macOS/Docker) without any Windows-specific GUI dependencies. In headless mode, all UIA/pyautogui/pygetwindow paths are disabled; the brain relies solely on companion extension messages (issue 034) and hooks (port 8767, already working).

## File Path Correction

The issue references `cyrus2/cyrus_brain.py` but the actual file is at the project root: **`cyrus_brain.py`**. The `cyrus2/` directory exists but is empty. All modifications target `cyrus_brain.py`.

## Key Design Decisions

1. **Guard at import level, not call level**: Windows imports (`comtypes`, `pyautogui`, `pyperclip`, `pygetwindow`, `uiautomation`) are wrapped in `if not HEADLESS:` at the top of the file. This prevents `ImportError` on systems where these packages aren't installed (Linux, macOS, Docker containers).

2. **Stub `_registered_sessions`**: Declare the empty dict now so `_vs_code_windows()` can reference it in HEADLESS mode. Issue 034 will populate it when companion extensions register.

3. **ChatWatcher: no-op in HEADLESS**: The UIA polling thread is the only thing ChatWatcher does. In HEADLESS, `start()` returns immediately. Response delivery already works via the hook path (Stop events on port 8767 → `handle_hook_connection`), which is independent of ChatWatcher.

4. **PermissionWatcher: arm_from_hook still works, polling skipped**: `arm_from_hook()` uses no Windows APIs — it just sets state and sends voice prompts. The UIA polling thread in `start()` is skipped. `handle_response()` gets a HEADLESS branch that logs + sends to companion (when available via 034), instead of calling `pyautogui.press()`.

5. **_submit_to_vscode_impl: companion-only in HEADLESS**: Skip all UIA/pyautogui fallback. If companion extension isn't running, return False with a log message.

6. **_submit_worker: guard comtypes.CoInitializeEx()**: In HEADLESS, comtypes isn't imported, so the COM initialization call is skipped.

## Acceptance Criteria → Implementation Map

| Criterion | Implementation |
|-----------|---------------|
| `HEADLESS` flag at top | Add after stdlib imports, before Windows imports |
| Windows imports guarded | `if not HEADLESS:` block around all 5 Windows imports |
| `_vs_code_windows()` returns companion sessions | HEADLESS branch returns `list(_registered_sessions.keys())` (empty until 034) |
| `_start_active_tracker()` disabled | Early return when HEADLESS |
| ChatWatcher uses hook-only path | `ChatWatcher.start()` returns immediately in HEADLESS |
| PermissionWatcher uses companion messages | `start()` skips polling; `handle_response()` routes to companion |
| `_submit_to_vscode_impl()` companion-only | Skip UIA fallback path entirely in HEADLESS |
| Brain starts without errors | All Windows refs guarded; startup message printed |

## Implementation Steps

### Step 1: Add HEADLESS flag and guard Windows imports

**File:** `cyrus_brain.py`, lines 24-60 and 108-109

Insert `HEADLESS` flag after the stdlib imports (line 33), then wrap all Windows imports in `if not HEADLESS:`. Also guard the module-level config calls (`auto.uiautomation.SetGlobalSearchTimeout(2)` and `pyautogui.FAILSAFE = False`).

```python
# After line 33 (import socket):
HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1"

if not HEADLESS:
    import comtypes
    import pyautogui
    import pyperclip
    import pygetwindow as gw
    try:
        import uiautomation as auto
    except Exception:
        # comtypes cache recovery block (existing code)
        ...
```

Move `auto.uiautomation.SetGlobalSearchTimeout(2)` and `pyautogui.FAILSAFE = False` inside the `if not HEADLESS:` block.

**Test:** `CYRUS_HEADLESS=1 python -c "exec(open('cyrus_brain.py').read().split('async def main')[0])"` — no ImportError on Linux.

### Step 2: Add `_registered_sessions` stub and update `_vs_code_windows()`

**File:** `cyrus_brain.py`

Add at module level (shared state section):
```python
_registered_sessions: dict[str, object] = {}   # populated by issue 034
```

Refactor `_vs_code_windows()`:
```python
def _vs_code_windows() -> list[tuple[str, str]]:
    if HEADLESS:
        return [(ws, f"{ws} - Visual Studio Code")
                for ws in _registered_sessions]
    # ... existing gw.getAllWindows() code unchanged ...
```

**Test:** In HEADLESS mode, `_vs_code_windows()` returns `[]` (empty until companion registers).

### Step 3: Disable `_start_active_tracker()` in HEADLESS

**File:** `cyrus_brain.py`, function `_start_active_tracker`

Add early return:
```python
def _start_active_tracker(session_mgr, loop):
    if HEADLESS:
        return  # companion sends focus/blur messages (issue 034)
    global _active_project
    while True:
        # ... existing polling code ...
```

Also guard the thread launch in `main()` — don't start the thread at all when HEADLESS.

**Test:** In HEADLESS, verify no active-tracker thread is spawned.

### Step 4: Make ChatWatcher HEADLESS-aware

**File:** `cyrus_brain.py`, class `ChatWatcher`

In `start()`, add early return:
```python
def start(self, loop, is_active_fn=None):
    if HEADLESS:
        return  # hooks deliver responses via port 8767
    # ... existing polling thread code ...
```

The hook path (`handle_hook_connection` → `"stop"` event → `_speak_queue.put`) already works independently and is unaffected.

**Test:** In HEADLESS, ChatWatcher.start() returns immediately; no UIA thread spawned.

### Step 5: Make PermissionWatcher HEADLESS-aware

**File:** `cyrus_brain.py`, class `PermissionWatcher`

**5a.** In `start()`, skip UIA polling:
```python
def start(self, loop):
    if HEADLESS:
        return  # permissions via companion messages (issue 034)
    # ... existing polling thread code ...
```

**5b.** In `handle_response()`, add HEADLESS branch (no pyautogui):
```python
def handle_response(self, text: str) -> bool:
    if not self._pending or not self._allow_btn:
        return False
    words = set(text.lower().strip().split())
    if words & self.ALLOW_WORDS:
        print(f"[Brain] -> Allowing command ({self.project_name or 'session'})")
        if HEADLESS:
            # Route to companion extension (issue 034 will populate _registered_sessions)
            print(f"[Brain] HEADLESS: permission allow — awaiting companion routing (034)")
        elif self._allow_btn == "keyboard":
            # ... existing keyboard path ...
        else:
            # ... existing UIA click path ...
        self._pending = False
        self._allow_btn = None
        return True
    if words & self.DENY_WORDS:
        print(f"[Brain] -> Cancelling command ({self.project_name or 'session'})")
        if HEADLESS:
            print(f"[Brain] HEADLESS: permission deny — awaiting companion routing (034)")
        else:
            # ... existing escape path ...
        self._pending = False
        self._allow_btn = None
        return True
    return False
```

**5c.** In `handle_prompt_response()`, add HEADLESS branch (no pyautogui/pyperclip):
```python
def handle_prompt_response(self, text: str) -> bool:
    if not self._prompt_pending or not self._prompt_input_ctrl:
        return False
    cancel = {"cancel", "escape", "never mind", "nevermind", "stop", "dismiss", "close"}
    if text.lower().strip() in cancel:
        if HEADLESS:
            print(f"[Brain] HEADLESS: prompt dismissed — awaiting companion routing (034)")
        else:
            pyautogui.press("escape")
            print(f"[Brain] -> Dismissed prompt ({self.project_name or 'session'})")
    else:
        if HEADLESS:
            print(f"[Brain] HEADLESS: prompt response '{text}' — awaiting companion routing (034)")
        else:
            # ... existing pyperclip/pyautogui path ...
    self._prompt_pending = False
    self._prompt_input_ctrl = None
    return True
```

`arm_from_hook()` requires no changes — it uses no Windows APIs.

**Test:** In HEADLESS, `arm_from_hook()` still announces permissions via voice; `handle_response()` logs without crashing.

### Step 6: Make `_submit_to_vscode_impl()` companion-only in HEADLESS

**File:** `cyrus_brain.py`, function `_submit_to_vscode_impl`

Add HEADLESS guard after the companion extension attempt:
```python
def _submit_to_vscode_impl(text: str) -> bool:
    # 0. Try companion extension (cross-platform)
    if _submit_via_extension(text):
        return True
    if HEADLESS:
        print("[Brain] HEADLESS: companion extension unavailable — cannot submit (no UIA fallback)")
        return False
    # ... rest of existing UIA fallback code unchanged ...
```

**Test:** In HEADLESS, submit attempts companion only, no UIA fallback.

### Step 7: Guard `_submit_worker()` COM initialization

**File:** `cyrus_brain.py`, function `_submit_worker`

```python
def _submit_worker() -> None:
    if not HEADLESS:
        comtypes.CoInitializeEx()
    while True:
        # ... rest unchanged ...
```

### Step 8: Add startup banner and guard main() thread launches

**File:** `cyrus_brain.py`, function `main()`

Add startup message and conditional thread launch:
```python
async def main() -> None:
    # ... argument parsing ...

    if HEADLESS:
        print("[Brain] Running in HEADLESS mode — Windows GUI paths disabled")
        print("[Brain] Companion extension registration required for full functionality")

    # ... queue setup, session manager ...

    # Window focus tracker — skip in HEADLESS
    if not HEADLESS:
        threading.Thread(
            target=_start_active_tracker,
            args=(session_mgr, loop),
            daemon=True,
        ).start()

    # ... rest of main unchanged ...
```

**Test:** `CYRUS_HEADLESS=1 python cyrus_brain.py` — prints banner, starts cleanly, listens on ports 8766/8767/8769.

### Step 9: Verify and manual test

Run through the testing checklist from the issue:

1. `python cyrus_brain.py` — verify starts normally on Windows (no HEADLESS)
2. `CYRUS_HEADLESS=1 python cyrus_brain.py` on Windows — starts without import errors
3. `CYRUS_HEADLESS=1 python cyrus_brain.py` on Linux — starts (no Windows imports attempted)
4. In HEADLESS, `_vs_code_windows()` returns empty list
5. In HEADLESS, active tracker thread doesn't start
6. In HEADLESS, hook Stop event still delivers to voice (existing path)

## Risk Notes

- **Circular dependency in issues**: Issue 030 lists "Blocked By: 031, 034" but 034 lists "Blocked By: 030". The resolution: 030 lays the HEADLESS foundation (guards + stubs), then 034 adds the registration server, then 031 adds the extension registration. The "Blocked By" on 030 means full companion integration depends on 031/034, but the guard work itself has no blockers.
- **No automated tests**: The cyrus project has no test framework. All testing is manual. Future issues could add pytest-based smoke tests.
- **Module-level side effects**: The `comtypes` error recovery try/except block (lines 40-59) imports modules and does filesystem operations. This entire block must be inside the `if not HEADLESS:` guard.
