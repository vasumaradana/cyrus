---
id=024-Write-test-vad-logic
title=Issue 024: Write test_vad_logic.py (Tier 3)
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=49768
total_output_tokens=5
total_duration_seconds=78
total_iterations=1
run_count=1
---

# Issue 024: Write test_vad_logic.py (Tier 3)

## Sprint
Sprint 3 — Test Suite

## Priority
High

## References
- [docs/14-test-suite.md — Tier 3: Keyword & State Machine Tests](../docs/14-test-suite.md#tier-3-keyword--state-machine-tests)
- `cyrus2/cyrus_voice.py` (VAD state machine, ring buffer, silence detection)
- Silero VAD model integration

## Description
Tier 3 tests for VAD (Voice Activity Detection) state machine. Mock the Silero model and test ring buffer management, adaptive silence thresholds, timeout logic, and state transitions. Approximately 15 test cases covering normal speech, silence, edge cases, and model failures.

## Blocked By
- Issue 005 (cyrus_common.py foundation)
- Issue 018 (conftest.py fixtures)

## Acceptance Criteria
- [ ] `cyrus2/tests/test_vad_logic.py` exists with 15+ test cases
- [ ] VAD state machine transitions tested (~5 cases): idle→listening→speaking, timeouts
- [ ] Ring buffer management tested (~3 cases): chunk queuing, size limits, FIFO behavior
- [ ] Silence detection tested (~3 cases): silence threshold, adaptive behavior, pre-speech buffer
- [ ] Timeout behavior tested (~2 cases): speech timeout, silence timeout
- [ ] Edge cases tested (~2 cases): no audio, rapid transitions, Silero model mock failures
- [ ] All tests pass: `pytest tests/test_vad_logic.py -v`

## Implementation Steps
1. Create `cyrus2/tests/test_vad_logic.py`
2. Import VAD components from cyrus_voice.py:
   ```python
   from unittest.mock import Mock, patch
   from cyrus_voice import VADStateMachine, RingBuffer  # or equivalent classes
   ```
3. Create conftest fixture for mocked Silero model:
   ```python
   @pytest.fixture
   def mock_silero_model():
       model = Mock()
       model.return_value = {"confidence": 0.8}  # or appropriate return format
       return model
   ```
4. Write state machine tests (~5 cases):
   - Transition from idle to listening on first audio chunk
   - Transition from listening to speaking on high confidence
   - Transition to silence on low confidence
   - Timeout from speaking to idle after N seconds
   - Recovery to speaking after brief silence (pre-speech buffer)
5. Write ring buffer tests (~3 cases):
   - Append chunks maintains FIFO order
   - Buffer respects max_size limit
   - get_frames() returns correct number of frames
   - Clear buffer resets to empty state
6. Write silence detection tests (~3 cases):
   - Silence threshold (e.g., confidence < 0.5) correctly detected
   - Adaptive threshold adjusts based on environment noise estimate
   - Pre-speech buffer holds N chunks before declaring speech
   - Silence counter increments correctly
7. Write timeout tests (~2 cases):
   - Speaking timeout (e.g., 5 seconds of silence ends utterance)
   - Listening timeout (e.g., 30 seconds with no audio resets)
8. Write edge cases (~2 cases):
   - All-silence audio (no speech detected)
   - Rapid on/off transitions (stutter/backtrack)
   - Silero model raises exception (graceful degradation)
9. Mock audio chunks as numpy arrays or simple lists

## Files to Create/Modify
- `cyrus2/tests/test_vad_logic.py` (new)
- Update `cyrus2/tests/conftest.py` to add mock_silero_model fixture

## Testing
```bash
pytest cyrus2/tests/test_vad_logic.py -v
pytest cyrus2/tests/test_vad_logic.py::test_state_transitions -v
pytest cyrus2/tests/test_vad_logic.py -k "buffer or silence" -v
pytest cyrus2/tests/test_vad_logic.py -k "timeout" -v
```

## Interview Questions

1. The issue references VADStateMachine and RingBuffer classes in cyrus_voice.py, but the current implementation uses a functional vad_loop() function with inline logic (ring buffer is a Python deque). Should VAD logic be refactored into classes as part of this issue, or should tests be written directly against the existing functional vad_loop() implementation?
   - Refactor VAD into classes first, then write tests (may require splitting into two issues)
   - Write tests directly against the existing vad_loop() function with mocked Silero model
   - Split this into two separate issues: one for VAD refactoring, one for tests
2. The acceptance criteria assume a VAD 'state machine' with transitions (idle→listening→speaking), but the current vad_loop() is a procedural implementation with local state variables (recording, frames, silence_count, etc.). Should the test criteria be updated to match the functional approach, or should VAD be refactored to use an explicit state machine pattern?
   - Update test criteria to work with the existing procedural implementation
   - Refactor VAD to use an explicit state machine class before writing tests
   - Write tests that treat vad_loop() as a state machine conceptually (test state transitions through behavior)

## Stage Log

### NEW — 2026-03-11 18:32:38Z

- **From:** NEW
- **Duration in stage:** 78s
- **Input tokens:** 49,768 (final context: 49,768)
- **Output tokens:** 5
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
