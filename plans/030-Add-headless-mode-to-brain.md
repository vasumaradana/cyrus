---
id=030-Add-headless-mode-to-brain
title=Plan: Issue 030 — Add Headless Mode to Brain
state=COMPLETE
issue=030-Add-headless-mode-to-brain
---

# Plan: Issue 030 — Add Headless Mode to Brain

## Gap Analysis

| Component | Existed | Needed |
|-----------|---------|--------|
| `cyrus_config.HEADLESS` constant | ✅ Already present | — |
| `cyrus_common.HEADLESS` re-export | ❌ Missing | Added import from cyrus_config |
| `_registered_sessions` dict in cyrus_common | ❌ Missing | Added module-level dict |
| `_vs_code_windows()` HEADLESS path | ❌ Not implemented | Returns `_registered_sessions.items()` |
| Windows imports guarded in cyrus_brain | ❌ Unconditional | Wrapped in `if not HEADLESS:` |
| `_start_active_tracker()` HEADLESS guard | ❌ Missing | Early return in HEADLESS |
| `ChatWatcher.start()` HEADLESS guard | ❌ Missing | Early return in HEADLESS poll() |
| `PermissionWatcher.start()` HEADLESS guard | ❌ Missing | Early return in HEADLESS poll() |
| `_submit_to_vscode_impl()` HEADLESS guard | ❌ Missing | Skip UIA fallback in HEADLESS |
| `_submit_worker()` HEADLESS guard | ❌ Missing | Skip CoInitializeEx in HEADLESS |
| `.env.example` documentation | ❌ Missing | Added CYRUS_HEADLESS=0 to root .env.example |

## Prioritized Tasks

- [x] **T1** — Document `CYRUS_HEADLESS` in root `.env.example`
- [x] **T2** — Add `HEADLESS` import and `_registered_sessions` to `cyrus_common.py`
- [x] **T3** — Update `_vs_code_windows()` to use `_registered_sessions` in HEADLESS mode
- [x] **T4** — Guard `ChatWatcher.start()` poll() thread against UIA in HEADLESS
- [x] **T5** — Guard `PermissionWatcher.start()` poll() thread against UIA in HEADLESS
- [x] **T6** — Move `cyrus_config` import before Windows imports in `cyrus_brain.py`
- [x] **T7** — Guard `comtypes`, `pyautogui`, `pygetwindow`, `pyperclip` imports with `if not HEADLESS:`
- [x] **T8** — Guard `uiautomation` import with `if not HEADLESS:`
- [x] **T9** — Guard module-level `auto.uiautomation.SetGlobalSearchTimeout(2)` and `pyautogui.FAILSAFE = False`
- [x] **T10** — Modify `_start_active_tracker()` to return immediately in HEADLESS
- [x] **T11** — Modify `_submit_to_vscode_impl()` to skip UIA fallback in HEADLESS
- [x] **T12** — Modify `_submit_worker()` to skip `comtypes.CoInitializeEx()` in HEADLESS
- [x] **T13** — Add startup log message when HEADLESS=True

## Acceptance-Driven Tests

All tests in `cyrus2/tests/test_030_headless_mode.py` (29 tests total).

| Test Class | Tests | Status |
|------------|-------|--------|
| `TestHeadlessConstantInConfig` | 6 | ✅ Pass |
| `TestCommonHeadlessConstant` | 2 | ✅ Pass |
| `TestVsCodeWindowsHeadless` | 5 (1 skip on Linux) | ✅ Pass |
| `TestChatWatcherHeadless` | 2 | ✅ Pass |
| `TestPermissionWatcherHeadless` | 3 | ✅ Pass |
| `TestStartActiveTrackerHeadless` | 2 | ✅ Pass |
| `TestSubmitToVscodeHeadless` | 4 | ✅ Pass |
| `TestBrainHeadlessImport` | 3 | ✅ Pass |
| `TestEnvExampleDocumentation` | 2 | ✅ Pass |

## Verification Checklist

- [x] `HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1"` in cyrus_config
- [x] `HEADLESS` re-exported from cyrus_common (imported from cyrus_config)
- [x] `_registered_sessions: dict[str, str] = {}` added to cyrus_common
- [x] `_vs_code_windows()` returns registered sessions in HEADLESS mode
- [x] Windows imports guarded in cyrus_brain: `if not HEADLESS: import comtypes...`
- [x] `_start_active_tracker()` returns immediately in HEADLESS
- [x] `ChatWatcher.start()` poll() returns immediately in HEADLESS
- [x] `PermissionWatcher.start()` poll() returns immediately in HEADLESS
- [x] `_submit_to_vscode_impl()` skips UIA fallback in HEADLESS
- [x] `_submit_worker()` skips `comtypes.CoInitializeEx()` in HEADLESS
- [x] Startup log message printed in HEADLESS mode
- [x] `.env.example` documents `CYRUS_HEADLESS=0`
- [x] Full test suite passes (761 tests, 0 failures)
- [x] `websockets` installed in test venv (required for `cyrus_brain` import tests)
- [x] Lint errors fixed (E501 in cyrus_common.py:148, E501/F841 in test_030_headless_mode.py)

## Files Modified

- `cyrus2/cyrus_common.py` — HEADLESS import, `_registered_sessions`, `_vs_code_windows()`, ChatWatcher, PermissionWatcher
- `cyrus2/cyrus_brain.py` — HEADLESS guards on imports, functions, and module-level calls
- `.env.example` — Added `CYRUS_HEADLESS=0` documentation

## Open Questions / Discoveries

- The test isolation issue (running `test_030` standalone fails due to `websockets` not mocked) is a pre-existing pattern in the test suite — all other tests that import `cyrus_brain` also rely on the conftest mock setup. This is not a regression.
- `_registered_sessions` is the interface point for the future Issue 031 (companion extension registration) and Issue 034 (brain registration listener), which will populate this dict via TCP messages.
- `arm_from_hook()` in `PermissionWatcher` continues to work in HEADLESS mode (keyboard-press path is skipped by companion extension handling the clicks).
