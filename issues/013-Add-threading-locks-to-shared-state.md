---
id=013-Add-threading-locks-to-shared-state
title=Issue 013: Add threading locks to shared state
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=54728
total_output_tokens=3
total_duration_seconds=41
total_iterations=1
run_count=1
---

# Issue 013: Add threading locks to shared state

## Sprint
Sprint 2 — Quality & Safety

## Priority
Critical

## References
- docs/12-code-audit.md — C4 Unprotected Shared Mutable State section

## Description
Add thread synchronization primitives to 6 shared mutable variables that are read/written from multiple threads. Create individual locks for each variable (except `_conversation_active`, which will use `threading.Event`). This prevents race conditions in ChatWatcher, PermissionWatcher, and SessionManager polling threads.

## Blocked By
- None

## Acceptance Criteria
- [ ] `import threading` added at top of `cyrus2/cyrus_brain.py`
- [ ] Lock created for `_chat_input_cache`
- [ ] Lock created for `_vscode_win_cache`
- [ ] Lock created for `_chat_input_coords`
- [ ] Lock created for `_mobile_clients`
- [ ] Lock created for `_whisper_prompt`
- [ ] `_conversation_active` converted from bool to `threading.Event`
- [ ] All reads of cached variables wrapped in `with lock:`
- [ ] All writes to cached variables wrapped in `with lock:`
- [ ] `_conversation_active.set()` used instead of `= True`
- [ ] `_conversation_active.is_set()` used instead of `if _conversation_active`
- [ ] `_conversation_active.wait()` used where appropriate
- [ ] All existing functionality preserved
- [ ] No deadlocks introduced

## Implementation Steps
1. At top of `cyrus2/cyrus_brain.py`, add `import threading` (if not present)
2. Define locks as module-level globals after imports:
   ```python
   _chat_input_cache_lock = threading.Lock()
   _vscode_win_cache_lock = threading.Lock()
   _chat_input_coords_lock = threading.Lock()
   _mobile_clients_lock = threading.Lock()
   _whisper_prompt_lock = threading.Lock()
   ```
3. Convert `_conversation_active` from `bool` to `threading.Event`:
   ```python
   _conversation_active = threading.Event()
   # Set it initially if it was True before:
   _conversation_active.set()  # or .clear() if it was False
   ```
4. Locate all reads of `_chat_input_cache`:
   - Wrap in `with _chat_input_cache_lock:`
5. Locate all writes to `_chat_input_cache`:
   - Wrap in `with _chat_input_cache_lock:`
6. Repeat for `_vscode_win_cache`, `_chat_input_coords`, `_mobile_clients`, `_whisper_prompt`
7. Replace all reads of `_conversation_active`:
   ```python
   # Old: if _conversation_active:
   # New: if _conversation_active.is_set():
   ```
8. Replace all writes to `_conversation_active`:
   ```python
   # Old: _conversation_active = True
   # New: _conversation_active.set()

   # Old: _conversation_active = False
   # New: _conversation_active.clear()
   ```
9. Test that all threading operations complete without deadlocks or race conditions

## Files to Create/Modify
- `cyrus2/cyrus_brain.py` — add locks for 6 variables, convert `_conversation_active` to Event

## Testing
```bash
# Run under ThreadSanitizer or with stress testing:
CYRUS_LOG_LEVEL=DEBUG python cyrus2/cyrus_brain.py &
sleep 10
pkill -f "python cyrus2/cyrus_brain.py"
# Expected: no deadlock warnings, clean shutdown

# Verify lock coverage with code inspection:
grep -n "_chat_input_cache" cyrus2/cyrus_brain.py
# All reads/writes should be wrapped in `with _chat_input_cache_lock:`

# Test Event functionality:
python -c "from cyrus2.cyrus_brain import _conversation_active; _conversation_active.set(); print(_conversation_active.is_set())"
# Expected: True
```

## Stage Log

### GROOMED — 2026-03-11 18:15:35Z

- **From:** NEW
- **Duration in stage:** 41s
- **Input tokens:** 54,728 (final context: 54,728)
- **Output tokens:** 3
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
