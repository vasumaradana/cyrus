# 12 — Code Audit

Full code audit of the Cyrus codebase (7 Python files, ~4,620 LOC). Findings organized by severity with exact file paths, line numbers, and actionable fixes.

**Date:** 2026-03-11
**Scope:** All `.py` files in project root

---

## Critical

### C1. God Functions — `_execute_cyrus_command()`

| File | Lines | Length |
|------|-------|--------|
| `main.py` | 374–1052 | 678 lines |
| `cyrus_brain.py` | 331–1107 | 776 lines |

Single functions handling 6+ command types with deeply nested if/elif chains. Impossible to test or reason about in isolation.

**Fix:** Create a command dispatch dict mapping command names to small handler functions:
```python
_COMMANDS = {
    "switch_project": _handle_switch_project,
    "unlock": _handle_unlock,
    "which_project": _handle_which_project,
    # ...
}
```

### C2. Massive `main()` Functions

| File | Lines | Length |
|------|-------|--------|
| `main.py` | 1435–1755 | 320 lines |
| `cyrus_brain.py` | 1416–1549 | 133 lines |

Core routing, permission handling, wake word processing, and initialization all in one place.

**Fix:** Extract subsystems (VAD init, TTS init, routing loop, permission handling) into separate functions called from a slim `main()`.

### C3. 90% Code Duplication — main.py vs cyrus_brain.py

Nearly identical implementations exist in both files for:

| Function/Class | main.py | cyrus_brain.py |
|----------------|---------|----------------|
| `_execute_cyrus_command()` | 374–451 | 331–398 |
| `_extract_project()` | 146–150 | 113–116 |
| `_make_alias()` | 153–155 | 119–120 |
| `_resolve_project()` | 158–166 | 123–137 |
| `_vs_code_windows()` | 169–180 | 140–150 |
| `clean_for_speech()` | 1311–1325 | 167–183 |
| `_strip_fillers()` | 1150–1156 | 192–197 |
| `_is_answer_request()` | 275–291 | 276–287 |
| `_fast_command()` | 322–371 | 290–328 |
| `ChatWatcher` class | ~460–700 | ~400–640 |
| `PermissionWatcher` class | ~730–960 | ~720–960 |
| `SessionManager` class | ~970–1050 | ~970–1110 |
| `play_chime()` | 207–218 | 263–266 |
| `play_listen_chime()` | 221–238 | 269–271 |

Additionally, `_FILLER_RE` is defined identically in three files (main.py:1144, cyrus_brain.py:186, cyrus_voice.py:107) and `_HALLUCINATIONS` in two (main.py:1129, cyrus_voice.py:96).

**Fix:** Extract all shared logic into `cyrus_common.py`. Both entry points import from it. This eliminates ~2,000 lines of duplication and makes every other fix easier.

### C4. Unprotected Shared Mutable State — Race Conditions

| Variable | File:Line | Protection | Issue |
|----------|-----------|------------|-------|
| `_chat_input_cache` | main.py:118, cyrus_brain.py:83 | None | Modified from polling threads |
| `_vscode_win_cache` | main.py:119, cyrus_brain.py:85 | None | Modified from polling threads |
| `_chat_input_coords` | cyrus_brain.py:84 | None | Modified at lines 547–559 |
| `_conversation_active` | main.py:121, cyrus_brain.py:90 | None | Read/written from multiple threads |
| `_mobile_clients` | cyrus_brain.py:224,1390,1409 | None | `.copy()` on read but unprotected writes |
| `_whisper_prompt` | main.py:129, cyrus_brain.py:91 | None | Modified in SessionManager, read during transcription |

**Fix:** Add a `threading.Lock` for each mutable cache/state variable. Wrap all reads and writes in `with lock:`. For `_conversation_active`, use `threading.Event` instead of a bare bool.

---

## High

### H1. 81 Broad `except Exception` Handlers

| File | Count |
|------|-------|
| cyrus_brain.py | 35 |
| main.py | 33 |
| cyrus_voice.py | 12 |
| probe_uia.py | 7 |
| test_permission_scan.py | 4 |

Many silently swallow errors with `pass`, hiding bugs and race conditions.

**Worst offenders:**
- `main.py:200` — `except Exception: pass` hides race condition in window tracking
- `main.py:1033–1034` — hidden errors in session scan
- `main.py:1082` — `except Exception: continue` in VAD loop
- `cyrus_brain.py:455, 462` — silent failures in UIA tree walks

**Fix:** Replace with specific exception types where possible. Where broad catch is needed for resilience (e.g., UIA walks), add `logging.exception()` before `pass`/`continue`. Create a `log_exception()` helper.

### H2. Security — Clipboard Manipulation Without Focus Verification

- `main.py:1295,1302` and `cyrus_brain.py:928`: Read/write clipboard blindly.
- `pyautogui` sends keystrokes (Escape, Ctrl+A, Ctrl+V) to foreground window. If focus changes mid-operation, input goes to the wrong application.

**Fix:** Verify VS Code has focus immediately before each keystroke sequence. Add a `_assert_vscode_focus()` guard that aborts if focus has shifted.

### H3. Security — PermissionWatcher Auto-Clicks "Allow"

`cyrus_brain.py:876–914`: Clicks "Allow" button in permission dialogs without user confirmation. A "yes" utterance during an unrelated dialog could approve dangerous operations.

**Fix:** Log which permission is being auto-approved. Consider requiring a specific confirmation phrase like "approve that" rather than just "yes".

### H4. File Handle Leak

`cyrus_brain.py:1181`:
```python
port = int(open(port_file).read().strip())
```
No `with` statement — file handle leaks if `int()` raises. No exception handling for missing file.

**Fix:** `with open(port_file) as f: port = int(f.read().strip())`

### H5. All Dependencies Unpinned

`requirements.txt` (17 packages), `requirements-voice.txt` (10), `requirements-brain.txt` (8) — none have version pins. Torch, onnxruntime-gpu, and faster-whisper are especially fragile across versions.

**Fix:** Pin all dependencies to exact versions. Run `pip freeze` in a working environment and update the requirements files. Consider `pip-compile` or `uv` for lockfile generation.

### H6. No Test Suite

Single file `test_permission_scan.py` (114 lines) is a manual diagnostic, not a proper test. No pytest/unittest framework. No CI/CD pipeline.

**Fix:** Add pytest. Start with unit tests for pure functions that can be extracted to `cyrus_common.py`: `_extract_project()`, `_make_alias()`, `_resolve_project()`, `clean_for_speech()`, `_strip_fillers()`, `_fast_command()`.

---

## Medium

### M1. Hardcoded Ports Across 5 Files

| Port | Usage | Locations |
|------|-------|-----------|
| 8766 | Brain | cyrus_brain.py:65, cyrus_voice.py:60 |
| 8767 | Hook | cyrus_brain.py:66, cyrus_hook.py:16 |
| 8769 | Mobile | cyrus_brain.py:67 |
| 8765 | Server | cyrus_server.py:159 |

**Fix:** Define ports in one constants module or read from env vars. Import everywhere.

### M2. Hardcoded Timeouts and Speech Parameters

- TTS timeout: 25.0s (cyrus_voice.py:174, main.py:1336)
- Socket timeout: 10s (cyrus_brain.py:1183, 1190)
- VAD thresholds: SPEECH_THRESHOLD, SILENCE_WINDOW, etc. (main.py:70–88)

**Fix:** Move to a config dict or env vars for tuning without code changes.

### M3. Polling Architecture (CPU Waste)

ChatWatcher polls every 0.5s, PermissionWatcher every 0.3s — busy-waiting via UIAutomation tree walks.

**Fix:** Consider longer poll intervals or an event-driven approach. At minimum, make poll intervals configurable.

### M4. Deep Nesting (Up to 10 Levels)

- `main.py` ~line 1165: 10 levels deep in Whisper transcribe path
- `cyrus_brain.py` ~line 730: 10 levels deep in Chrome widget PaneControl search

**Fix:** Extract inner logic into helper functions. Use early returns to reduce nesting.

### M5. No Logging Framework

Uses bare `print()` throughout. No log levels, no log rotation, no structured output.

**Fix:** Replace `print()` with the `logging` module. Use `logging.getLogger(__name__)` per file.

### M6. No Graceful Degradation

- No fallback if `keyboard` module fails to hook (cyrus_voice.py:525–527).
- No handling when VS Code is not running.

**Fix:** Wrap optional subsystems in try/except with clear user-facing error messages.

---

## Low

### L1. Unencrypted Localhost Sockets

`cyrus_brain.py:1182–1184`: Plain TCP to localhost. Acceptable for localhost-only use but undocumented.

**Fix:** Add comment documenting localhost-only assumption. Assert connections originate from 127.0.0.1.

### L2. No Rate Limiting on Hotkeys

`cyrus_voice.py:525–527`: Hotkey callbacks fire without debounce.

**Fix:** Add timestamp-based debounce — ignore triggers within 200ms of the last one.

### L3. Missing Input Validation on submit_to_vscode

`main.py:1222`: Accepts arbitrary text, passes to clipboard then pyautogui.

**Fix:** Strip control characters and escape sequences before clipboard write.

### L4. No Modern Python Packaging

Only `requirements.txt` files exist. No `pyproject.toml` or `setup.py`.

**Fix:** Add `pyproject.toml` with project metadata when ready to formalize distribution.

---

## Prioritized Implementation Checklist

| # | Action | Severity | Effort | Impact |
|---|--------|----------|--------|--------|
| 1 | Extract shared code into `cyrus_common.py` (C3) | Critical | Large | Eliminates ~2,000 lines of duplication |
| 2 | Add locks to all shared mutable state (C4) | Critical | Medium | Prevents race conditions |
| 3 | Break up `_execute_cyrus_command()` into dispatch table (C1) | Critical | Medium | Readability, testability |
| 4 | Break up `main()` functions (C2) | Critical | Medium | Maintainability |
| 5 | Replace silent `except Exception: pass` with logging (H1) | High | Medium | Bug visibility |
| 6 | Pin all dependencies (H5) | High | Small | Reproducible builds |
| 7 | Add focus-check guard before pyautogui keystrokes (H2) | High | Small | Prevent misdirected input |
| 8 | Fix file handle leak (H4) | High | Trivial | Resource leak |
| 9 | Add pytest + unit tests for pure functions (H6) | High | Medium | Regression safety |
| 10 | Centralize port/timeout constants (M1, M2) | Medium | Small | Single source of truth |
| 11 | Replace `print()` with `logging` (M5) | Medium | Medium | Debuggability |
| 12 | Add PermissionWatcher confirmation logging (H3) | High | Small | Security visibility |
| 13 | Reduce nesting depth in UIA walks (M4) | Medium | Small | Readability |
| 14 | Add hotkey debounce (L2) | Low | Trivial | Prevent double-triggers |
| 15 | Add input sanitization to submit (L3) | Low | Small | Defense in depth |

Items 1–4 should be done first as a group — extracting shared code makes every subsequent fix a single-location change instead of a multi-file change.
