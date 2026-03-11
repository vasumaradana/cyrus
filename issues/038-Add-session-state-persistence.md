---
id=038-Add-session-state-persistence
title=Issue 038: Add Session State Persistence
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=76845
total_output_tokens=11
total_duration_seconds=114
total_iterations=2
run_count=2
---

# Issue 038: Add Session State Persistence

## Sprint
Sprint 6 — Polish

## Priority
Medium

## References
- docs/15-recommendations.md — #10 (Session persistence)

## Description
Implement persistence of brain session state (aliases, pending queues, project mappings) to a JSON file on shutdown and restore on startup. Survives brain restarts without losing user-defined aliases or in-flight requests. State file written to `~/.cyrus/state.json` with atomic writes.

## Blocked By
- None

## Acceptance Criteria
- [ ] State saved to `~/.cyrus/state.json` on shutdown (SIGTERM, Ctrl+C)
- [ ] State includes: aliases, pending request queues, project mappings
- [ ] Atomic writes (write to .tmp, then rename to avoid corruption)
- [ ] State loaded from file at startup
- [ ] Gracefully handles missing or corrupted state file
- [ ] State file permissions restricted (0600 on Unix, equivalent on Windows)
- [ ] Configurable via `CYRUS_STATE_FILE` env var

## Implementation Steps
1. Create state management in `cyrus2/cyrus_brain.py`:
   ```python
   import signal
   from pathlib import Path

   def _get_state_file():
       custom = os.environ.get("CYRUS_STATE_FILE")
       if custom:
           return Path(custom)
       default = Path.home() / ".cyrus" / "state.json"
       default.parent.mkdir(parents=True, exist_ok=True)
       return default

   def _save_state():
       """Save session state to disk"""
       state = {
           "version": 1,
           "timestamp": time.time(),
           "aliases": _session_aliases,  # or whatever structure holds aliases
           "projects": _project_mapping,
           "pending_queues": {}  # Serialize any pending requests
       }

       state_file = _get_state_file()
       temp_file = state_file.with_suffix('.tmp')

       try:
           with open(temp_file, 'w') as f:
               json.dump(state, f, indent=2)
           # Atomic rename
           temp_file.replace(state_file)
           # Restrict permissions (Unix)
           try:
               state_file.chmod(0o600)
           except:
               pass
           print(f"[State] Saved to {state_file}")
       except Exception as e:
           print(f"[State] Failed to save: {e}")

   def _load_state():
       """Restore session state from disk"""
       state_file = _get_state_file()

       if not state_file.exists():
           print(f"[State] No state file found; starting fresh")
           return

       try:
           with open(state_file) as f:
               state = json.load(f)

           version = state.get("version", 0)
           if version != 1:
               print(f"[State] Skipping unsupported state version {version}")
               return

           # Restore aliases
           aliases = state.get("aliases", {})
           if aliases:
               global _session_aliases
               _session_aliases.update(aliases)
               print(f"[State] Loaded {len(aliases)} aliases")

           # Restore projects
           projects = state.get("projects", {})
           if projects:
               # Update project mappings
               print(f"[State] Loaded {len(projects)} projects")

       except json.JSONDecodeError:
           print(f"[State] Corrupted state file, starting fresh")
       except Exception as e:
           print(f"[State] Failed to load: {e}")

   def _on_shutdown(signum, frame):
       """Handle shutdown gracefully"""
       print("[Brain] Shutting down...")
       _save_state()
       sys.exit(0)
   ```
2. Register shutdown handlers in `main()`:
   ```python
   signal.signal(signal.SIGTERM, _on_shutdown)
   signal.signal(signal.SIGINT, _on_shutdown)

   # Load state on startup
   _load_state()
   ```
3. Update .env.example:
   ```
   # Session state persistence file (saves aliases, projects on shutdown)
   # Leave blank to use default ~/.cyrus/state.json
   CYRUS_STATE_FILE=
   ```

## Files to Create/Modify
- Modify: `cyrus2/cyrus_brain.py` (add _save_state, _load_state, shutdown handlers)
- Update: `.env.example` (document CYRUS_STATE_FILE)

## Testing
1. Start brain: `python cyrus2/cyrus_brain.py`
2. Add aliases via voice commands: "alias my_proj /path/to/project"
3. Verify alias in ~/.cyrus/state.json
4. Stop brain (Ctrl+C)
5. Verify state saved to ~/.cyrus/state.json
6. Restart brain
7. Verify alias loaded from state file
8. Test with corrupted state.json — verify graceful fallback
9. Test with missing state file — verify clean startup
10. Test CYRUS_STATE_FILE override: `CYRUS_STATE_FILE=/tmp/custom.json python cyrus2/cyrus_brain.py`

## Stage Log

### NEW — 2026-03-11 19:12:57Z

- **From:** NEW
- **Duration in stage:** 69s
- **Input tokens:** 50,158 (final context: 50,158)
- **Output tokens:** 5
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage


### GROOMED — 2026-03-11 19:16:09Z

- **From:** NEW
- **Duration in stage:** 45s
- **Input tokens:** 26,687 (final context: 26,687)
- **Output tokens:** 6
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** interview
## Interview Q&A

1. **Q:** Which file should be modified: the current /cyrus_brain.py (at project root) or should this wait for the cyrus2/ refactoring to be complete? Issue 027 has the same ambiguity and still needs clarification.
   **A:** Wait for cyrus2/ refactoring (Issues 005-008) to complete and target cyrus2/cyrus_brain.py

2. **Q:** What state should be persisted from pending queues? The issue mentions 'pending request queues', but each ChatWatcher has its own _pending_queue (list of pending speech texts). Should these be: (a) auto-replayed on startup, (b) discarded, or (c) left empty in the state file?
   **A:** Load into state file but don't auto-replay (manual recovery)

3. **Q:** The issue shows registering SIGTERM/SIGINT signal handlers directly, but asyncio.run() already handles KeyboardInterrupt. Should signal handlers be integrated using: (a) asyncio.add_signal_handler() for proper async integration, (b) thread-safe signal handlers at module level, or (c) a shutdown hook within the asyncio context?
   **A:** Use asyncio.add_signal_handler() in the event loop
