# Plan: Issue 027 — Create Centralized Config Module

## Status: COMPLETE ✅

## Gap Analysis

**What existed before:**
- Hardcoded port constants in each service file (`BRAIN_PORT = 8766` in brain/voice/hook, `8765` in server)
- Hardcoded timeouts (`timeout=25.0` in cyrus_voice.py)
- Hardcoded VAD thresholds (`SPEECH_THRESHOLD = 0.5`, `SILENCE_WINDOW_MS = 1000`)
- No central place to change these values without editing each file separately
- No documentation of what env vars are accepted

**What was needed:**
- A single `cyrus_config.py` module that reads all tuneable constants from env vars with defaults
- Each service file imports from cyrus_config instead of defining its own hardcoded values
- A `.env.example` documenting every configurable option

## Prioritized Tasks

- [x] **T1**: Create `cyrus2/cyrus_config.py` with all port, timeout, and VAD constants backed by env vars
- [x] **T2**: Write acceptance-driven tests first (`test_027_cyrus_config.py`)
- [x] **T3**: Update `cyrus2/cyrus_brain.py` — import BRAIN_PORT, HOOK_PORT, MOBILE_PORT
- [x] **T4**: Update `cyrus2/cyrus_voice.py` — import BRAIN_PORT, SPEECH_THRESHOLD, SILENCE_WINDOW, TTS_TIMEOUT
- [x] **T5**: Update `cyrus2/cyrus_hook.py` — import HOOK_PORT (with fallback for standalone invocation)
- [x] **T6**: Update `cyrus2/cyrus_server.py` — import SERVER_PORT
- [x] **T7**: Create `cyrus2/.env.example` documenting all 13 CYRUS_* variables
- [x] **T8**: Fix all ruff lint violations, run full test suite

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `cyrus2/cyrus_config.py` | CREATE | Central config module with 13 env-var-backed constants |
| `cyrus2/.env.example` | CREATE | Documents all CYRUS_* environment variables |
| `cyrus2/tests/test_027_cyrus_config.py` | CREATE | 36 acceptance-driven tests (defaults, overrides, errors, edge cases) |
| `cyrus2/cyrus_brain.py` | MODIFY | Import BRAIN_PORT, HOOK_PORT, MOBILE_PORT from cyrus_config |
| `cyrus2/cyrus_voice.py` | MODIFY | Import BRAIN_PORT, SPEECH_THRESHOLD, SILENCE_WINDOW, TTS_TIMEOUT from cyrus_config |
| `cyrus2/cyrus_hook.py` | MODIFY | Import HOOK_PORT with fallback for standalone invocation |
| `cyrus2/cyrus_server.py` | MODIFY | Import SERVER_PORT; use as default in argparse |

## Constants in cyrus_config.py

| Constant | Env Var | Default | Type | Used In |
|----------|---------|---------|------|---------|
| `BRAIN_PORT` | `CYRUS_BRAIN_PORT` | 8766 | int | brain, voice |
| `HOOK_PORT` | `CYRUS_HOOK_PORT` | 8767 | int | brain, hook |
| `MOBILE_PORT` | `CYRUS_MOBILE_PORT` | 8769 | int | brain |
| `COMPANION_PORT` | `CYRUS_COMPANION_PORT` | 8770 | int | (future) |
| `SERVER_PORT` | `CYRUS_SERVER_PORT` | 8765 | int | server |
| `TTS_TIMEOUT` | `CYRUS_TTS_TIMEOUT` | 25.0 | float | voice |
| `SOCKET_TIMEOUT` | `CYRUS_SOCKET_TIMEOUT` | 10 | int | hook |
| `SPEECH_THRESHOLD` | `CYRUS_SPEECH_THRESHOLD` | 0.6 | float | voice |
| `SILENCE_WINDOW` | `CYRUS_SILENCE_WINDOW` | 1500 | int | voice |
| `MIN_SPEECH_DURATION` | `CYRUS_MIN_SPEECH_DURATION` | 500 | int | (future) |
| `CHAT_WATCHER_POLL_INTERVAL` | `CYRUS_CHAT_POLL_MS` | 0.5 | float | (future) |
| `PERMISSION_WATCHER_POLL_INTERVAL` | `CYRUS_PERMISSION_POLL_MS` | 0.3 | float | (future) |
| `MAX_SPEECH_WORDS` | `CYRUS_MAX_SPEECH_WORDS` | 200 | int | (future) |

## Acceptance-Driven Tests

| AC | Test Class | Status |
|----|-----------|--------|
| cyrus_config.py created | `TestModuleInterface.test_module_imports_without_error` | ✅ |
| Ports have correct defaults | `TestConfigDefaults.test_*_port_default` (5 tests) | ✅ |
| Timeouts have correct defaults | `TestConfigDefaults.test_tts_timeout_default`, `test_socket_timeout_default` | ✅ |
| All values read from env vars | `TestConfigEnvOverrides` (8 tests) | ✅ |
| Imported and used in brain/voice/hook/server | Verified by lint + test pass | ✅ |
| .env.example exists with all keys | `TestEnvExample` (3 tests) | ✅ |

## Validation Results

- ✅ `ruff check .` — 0 violations
- ✅ `pytest tests/` — 684 passed (36 new tests for this issue)
- ✅ Coverage: config module is 100% covered by tests

## Design Notes

**cyrus_hook.py fallback**: The hook is invoked as a subprocess by Claude Code from any working directory, so we use `_SCRIPT_DIR` path injection + a `try/except ImportError` fallback to ensure the hook never crashes even if the sys.path setup fails.

**Default value divergence**: `SPEECH_THRESHOLD` was previously 0.5 in cyrus_voice.py; the issue spec raises it to 0.6. `SILENCE_WINDOW` was 1000ms; spec raises to 1500ms. All existing VAD tests use dynamic references to module constants (`cyrus_voice.SPEECH_RING`, etc.) so they adapt automatically.

**Import style consistency**: voice.py and server.py use `from cyrus2.xxx import ...` (package-style, requires parent of cyrus2 on sys.path); brain.py uses `from xxx import ...` (flat-style, requires cyrus2 itself on sys.path). This inconsistency pre-existed; we matched each file's own style.

## Open Questions

None — all requirements satisfied.
