# Plan: Issue 024 — Write test_vad_logic.py (Tier 3)

## Status: COMPLETE

## Gap Analysis

**What exists:**
- `cyrus2/tests/test_vad_logic.py` — 15 acceptance-driven tests, all passing
- `cyrus2/tests/conftest.py` — includes `mock_silero_model` fixture
- `cyrus2/cyrus_voice.py` — functional `vad_loop()` implementation with ring buffer, adaptive silence, and timeout logic

**What was needed:**
- Tests against the existing functional `vad_loop()` implementation (no refactoring to class-based design required — tested behaviorally through the function interface)

## Decision: Interview Question Resolution

The issue raised two interview questions about whether to refactor VAD into classes before testing. The chosen approach:
- **Write tests directly against the existing functional `vad_loop()` implementation**
- Tests treat the function as a state machine conceptually (observing transitions through behavior)
- No class refactoring needed — the acceptance criteria are fully met against the procedural implementation

## Prioritized Tasks

- [x] Create `cyrus2/tests/test_vad_logic.py` with 15+ test cases
- [x] Add `mock_silero_model` fixture to `cyrus2/tests/conftest.py`
- [x] Ring buffer management tests (3 cases): FIFO order, max size, speech-ratio gate
- [x] VAD state transition tests (5 cases): idle→recording, insufficient ratio, utterance emission, muted mic, state reset
- [x] Silence detection tests (3 cases): low-prob frames, silence counter, adaptive ring
- [x] Timeout tests (2 cases): silence timeout, max-duration timeout
- [x] Edge case tests (2 cases): model exception recovery, pre-speech buffer inclusion
- [x] All tests pass: `pytest tests/test_vad_logic.py -v`
- [x] Lint passes: `ruff check tests/test_vad_logic.py`

## Acceptance-Driven Tests

| Acceptance Criterion | Test Class / Method | Status |
|---|---|---|
| 15+ test cases | 15 tests total | ✅ |
| VAD state transitions (~5): idle→listening→speaking, timeouts | `TestVADStateTransitions` (5 tests) | ✅ |
| Ring buffer management (~3): FIFO, size limits, speech-ratio gate | `TestRingBufferManagement` (3 tests) | ✅ |
| Silence detection (~3): threshold, adaptive, pre-speech buffer | `TestSilenceDetection` (3 tests) | ✅ |
| Timeout behavior (~2): speech timeout, silence timeout | `TestTimeoutBehavior` (2 tests) | ✅ |
| Edge cases (~2): no audio, rapid transitions, model failures | `TestEdgeCases` (2 tests) | ✅ |
| `pytest tests/test_vad_logic.py -v` passes | 15/15 PASSED in 0.47s | ✅ |

## Files Created/Modified

- `cyrus2/tests/test_vad_logic.py` — **existed and complete**; 15 tests across 5 classes
- `cyrus2/tests/conftest.py` — **existed and complete**; `mock_silero_model` fixture present

## Verification Checklist

- [x] `pytest tests/test_vad_logic.py -v` — 15 passed
- [x] `ruff check tests/test_vad_logic.py` — All checks passed
- [x] 15+ test cases present (exactly 15)
- [x] All test categories covered (ring buffer, state transitions, silence detection, timeout, edge cases)
- [x] Hardware/GPU dependencies mocked at `sys.modules` level (no hardware required to run tests)
- [x] `mock_silero_model` fixture available in `conftest.py`

## Implementation Approach

The tests use three helper utilities:

1. **`_make_model_mock(items)`** — Drives the Silero VAD mock with a sequence of floats or `_RAISE` sentinels. Exhausting the sequence sets `_shutdown` to cleanly stop `vad_loop`.

2. **`_make_stream_mock()`** — Provides a mock `sd.RawInputStream` returning silent frames.

3. **`_run_vad(probs)`** — Runs `vad_loop()` in a thread with a live `asyncio` event loop (needed for `call_soon_threadsafe`). Collects `on_utterance` calls and returns them as a list.

4. **`_run_vad_with_delayed_shutdown(probs, delay)`** — Like `_run_vad` but terminates after a wall-clock delay, used for muted-mic scenarios where the model is never called.

Hardware dependencies (`keyboard`, `numpy`, `pygame`, `sounddevice`, `torch`, `faster_whisper`, `silero_vad`) are all injected into `sys.modules` as `MagicMock` before `cyrus_voice` is imported, so no GPU or audio hardware is required.

## Open Questions

None — all resolved. The issue is complete.
