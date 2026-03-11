---
id=008-Break-up-main-functions-into-subsystems
title=Issue 008: Break up main() functions into subsystems
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=80775
total_output_tokens=4
total_duration_seconds=51
total_iterations=1
run_count=1
---

# Issue 008: Break up main() functions into subsystems

## Sprint
Cyrus 2.0 Rewrite — Sprint 1

## Priority
Critical

## References
- docs/12-code-audit.md — C2 (massive main() functions, 133–320 lines)

## Description
Both `main.py` and `cyrus_brain.py` have massive `main()` functions (320 and 133 lines) that handle VAD initialization, TTS setup, routing loop startup, and permission handling all in one place. Extract subsystems into separate `_init_*()` functions for clarity and testability.

## Blocked By
None (but benefits from Issue 005 extraction)

## Acceptance Criteria
- [ ] `main()` in `cyrus2/cyrus_brain.py` reduced to < 50 lines
- [ ] `main()` in `cyrus2/main.py` reduced to < 50 lines (if kept)
- [ ] Each subsystem initialization in a separate function: `_init_vad()`, `_init_tts()`, etc.
- [ ] Subsystem functions return initialized objects/state
- [ ] All original initialization behavior preserved (no logic changes)
- [ ] Error handling improved: specific exceptions caught and logged
- [ ] Startup sequence clear and documented

## Implementation Steps

1. **Identify all subsystems** initialized in current `main()` functions:
   - VAD (Voice Activity Detection): Silero VAD model loading, audio stream setup
   - TTS (Text-to-Speech): Kokoro model loading, voice selection
   - Routing loop: asyncio loop setup, listen/respond cycle
   - Permission handling: PermissionWatcher thread startup
   - Session management: SessionManager initialization
   - Network: Port/socket setup for inter-process communication
   - Hotkey hooks: keyboard listener registration

2. **Extract VAD initialization** → `_init_vad()` in `cyrus2/cyrus_brain.py`:
   ```python
   def _init_vad():
       """Load Silero VAD model and configure audio stream."""
       global _vad_model
       logging.info("Initializing VAD...")
       try:
           _vad_model = load_silero_vad()
           # Setup audio stream parameters
           return {
               "model": _vad_model,
               "sample_rate": SAMPLE_RATE,
               "frame_size": FRAME_SIZE,
           }
       except Exception as e:
           logging.exception("Failed to initialize VAD")
           raise
   ```

3. **Extract TTS initialization** → `_init_tts()` in `cyrus2/cyrus_brain.py`:
   ```python
   def _init_tts():
       """Load Kokoro TTS model and verify voices."""
       global _kokoro
       logging.info("Initializing TTS...")
       try:
           # Load Kokoro model, validate voice selection
           _kokoro = load_kokoro_model(KOKORO_MODEL, KOKORO_VOICES)
           return {"model": _kokoro, "voice": TTS_VOICE}
       except Exception as e:
           logging.exception("Failed to initialize TTS")
           raise
   ```

4. **Extract routing loop initialization** → `_init_routing_loop()`:
   ```python
   def _init_routing_loop(vad_config, tts_config, session_mgr):
       """Set up asyncio event loop and routing task."""
       logging.info("Starting routing loop...")
       loop = asyncio.new_event_loop()
       asyncio.set_event_loop(loop)
       # Create routing task
       return loop
   ```

5. **Extract permission handling** → `_init_permission_handling()`:
   ```python
   def _init_permission_handling():
       """Start PermissionWatcher thread."""
       logging.info("Starting permission watcher...")
       watcher = PermissionWatcher()
       thread = threading.Thread(target=watcher.run, daemon=True)
       thread.start()
       return watcher, thread
   ```

6. **Extract network setup** → `_init_network()`:
   ```python
   def _init_network(host, port):
       """Set up TCP/WebSocket listeners."""
       logging.info(f"Listening on {host}:{port}...")
       server = asyncio.run(asyncio.start_server(...))
       return server
   ```

7. **Extract hotkey setup** → `_init_hotkeys()`:
   ```python
   def _init_hotkeys():
       """Register keyboard hotkey listeners."""
       logging.info("Registering hotkeys...")
       keyboard.add_hotkey(KEY_PAUSE, _on_pause_pressed)
       keyboard.add_hotkey(KEY_STOP, _on_stop_pressed)
       # etc.
       logging.info("Hotkeys registered")
   ```

8. **Refactor `main()` to orchestrate subsystems**:
   ```python
   def main():
       """Initialize and run Cyrus brain service."""
       logging.basicConfig(level=logging.INFO)
       logging.info("Starting Cyrus Brain...")

       # Initialize all subsystems in order
       vad_config = _init_vad()
       tts_config = _init_tts()
       session_mgr = SessionManager()
       loop = _init_routing_loop(vad_config, tts_config, session_mgr)
       perm_watcher, perm_thread = _init_permission_handling()
       server = _init_network("0.0.0.0", BRAIN_PORT)
       _init_hotkeys()

       logging.info("Cyrus Brain ready")

       # Run event loop (blocking)
       try:
           loop.run_forever()
       except KeyboardInterrupt:
           logging.info("Shutdown requested")
       finally:
           loop.close()
   ```

9. **Add error handling** around each subsystem:
   - If VAD fails: exit with clear error
   - If TTS fails: warn but continue (fallback to text?)
   - If network fails: exit with port error
   - If hotkeys fail: warn but continue

10. **Document startup sequence** in a comment:
    ```python
    # Startup sequence:
    # 1. VAD model loaded (enables audio capture)
    # 2. TTS model loaded (enables speech output)
    # 3. Routing loop created (ready to process utterances)
    # 4. Permission watcher started (monitors dialogs)
    # 5. Network server started (accepts voice connections)
    # 6. Hotkeys registered (enables F7/F8/F9)
    ```

## Files to Create/Modify
- Modify: `cyrus2/cyrus_brain.py` (extract `_init_*()` functions, slim down `main()`)
- Modify: `cyrus2/main.py` (if kept, apply same pattern)
- Create: `cyrus2/config.py` (optional: centralize configuration for easier testing)

## Testing
- Unit test each `_init_*()` with mocked dependencies: `pytest test_init_functions.py::test_init_vad`
- Integration test: run `main()` and verify all subsystems initialized
- Verify error handling: mock a failure in each subsystem and confirm graceful exit
- Check startup logs: `python cyrus_brain.py 2>&1 | grep "Initializing"`
- Measure startup time before/after refactor (should be unchanged)

## Stage Log

### GROOMED — 2026-03-11 18:33:40Z

- **From:** NEW
- **Duration in stage:** 51s
- **Input tokens:** 80,775 (final context: 80,775)
- **Output tokens:** 4
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
