---
id=027-Create-centralized-config-module
title=Issue 027: Create Centralized Config Module
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=54455
total_output_tokens=7
total_duration_seconds=92
total_iterations=1
run_count=1
---

# Issue 027: Create Centralized Config Module

## Sprint
Sprint 4 — Configuration & Auth

## Priority
High

## References
- docs/12-code-audit.md — M1 (hardcoded ports), M2 (hardcoded timeouts)
- docs/15-recommendations.md — #5 (Configuration file)

## Description
Consolidate all hardcoded configuration values (ports, timeouts, thresholds, wake words) into a single `cyrus_config.py` module. Read from environment variables with sensible defaults. Replace hardcoded port definitions across 5+ files (8766, 8767, 8769, 8765) and timeout constants (TTS 25.0s, socket 10s, VAD thresholds).

## Blocked By
- None

## Acceptance Criteria
- [ ] `cyrus2/cyrus_config.py` created with ConfigManager class
- [ ] Ports defined: BRAIN_PORT=8766, HOOK_PORT=8767, MOBILE_PORT=8769, COMPANION_PORT=8770, SERVER_PORT=8765
- [ ] Timeouts defined: TTS_TIMEOUT=25.0, SOCKET_TIMEOUT=10, VAD poll intervals
- [ ] All values read from env vars with fallback defaults
- [ ] Imported and used in cyrus2/cyrus_brain.py, cyrus2/cyrus_voice.py, cyrus2/cyrus_hook.py, cyrus2/cyrus_server.py
- [ ] .env.example file created documenting all configurable options

## Implementation Steps
1. Create `cyrus2/cyrus_config.py` as a module-level config dict or ConfigManager class
2. Define all port constants with env var lookups:
   ```python
   BRAIN_PORT = int(os.environ.get("CYRUS_BRAIN_PORT", "8766"))
   HOOK_PORT = int(os.environ.get("CYRUS_HOOK_PORT", "8767"))
   MOBILE_PORT = int(os.environ.get("CYRUS_MOBILE_PORT", "8769"))
   COMPANION_PORT = int(os.environ.get("CYRUS_COMPANION_PORT", "8770"))
   SERVER_PORT = int(os.environ.get("CYRUS_SERVER_PORT", "8765"))
   ```
3. Define timeout and threshold constants:
   ```python
   TTS_TIMEOUT = float(os.environ.get("CYRUS_TTS_TIMEOUT", "25.0"))
   SOCKET_TIMEOUT = int(os.environ.get("CYRUS_SOCKET_TIMEOUT", "10"))
   CHAT_WATCHER_POLL_INTERVAL = float(os.environ.get("CYRUS_CHAT_POLL_MS", "0.5"))
   PERMISSION_WATCHER_POLL_INTERVAL = float(os.environ.get("CYRUS_PERMISSION_POLL_MS", "0.3"))
   MAX_SPEECH_WORDS = int(os.environ.get("CYRUS_MAX_SPEECH_WORDS", "200"))
   ```
4. Add VAD thresholds from current main.py:70–88:
   ```python
   SPEECH_THRESHOLD = float(os.environ.get("CYRUS_SPEECH_THRESHOLD", "0.6"))
   SILENCE_WINDOW = int(os.environ.get("CYRUS_SILENCE_WINDOW", "1500"))
   MIN_SPEECH_DURATION = int(os.environ.get("CYRUS_MIN_SPEECH_DURATION", "500"))
   ```
5. Replace all hardcoded values in cyrus2/ files with imports from cyrus_config
6. Create .env.example with all keys and defaults documented
7. Update cyrus2/__init__.py to expose config module

## Files to Create/Modify
- Create: `cyrus2/cyrus_config.py`
- Modify: `cyrus2/cyrus_brain.py` (replace hardcoded 8766, 8767, 8769 with config)
- Modify: `cyrus2/cyrus_voice.py` (replace hardcoded 8766, TTS timeout)
- Modify: `cyrus2/cyrus_hook.py` (replace hardcoded 8767)
- Modify: `cyrus2/cyrus_server.py` (replace hardcoded 8765)
- Create: `.env.example`

## Testing
1. Run `cyrus2/cyrus_brain.py` with defaults — verify ports 8766 bound
2. Run `CYRUS_BRAIN_PORT=9000 python cyrus2/cyrus_brain.py` — verify binds to 9000
3. Run `CYRUS_TTS_TIMEOUT=30.0 python cyrus2/cyrus_voice.py` — verify timeout respected
4. Verify .env.example matches all config keys
5. Verify config module loads without errors in headless and full modes

## Interview Questions

1. This issue references cyrus2/cyrus_brain.py, cyrus2/cyrus_voice.py, cyrus2/cyrus_hook.py, and cyrus2/cyrus_server.py, but these files don't exist yet. The current files are in the root directory. Should this issue: (a) assume that issues 005+ (cyrus2 refactoring) are already complete and work with the cyrus2/ files, or (b) work with the current root-level files and create cyrus/cyrus_config.py in the root instead?
   - Work with cyrus2/ files (assume 005+ complete)
   - Work with root-level files first

## Stage Log

### NEW — 2026-03-11 18:56:22Z

- **From:** NEW
- **Duration in stage:** 92s
- **Input tokens:** 54,455 (final context: 54,455)
- **Output tokens:** 7
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
