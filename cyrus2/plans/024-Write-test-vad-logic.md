# Plan: Issue 024 — Write test_vad_logic.py (Tier 3)

## Status: COMPLETE ✅

## Gap Analysis

**What existed:**
- `cyrus2/cyrus_voice.py` — procedural `vad_loop()` with inline VAD state machine
  (ring deque, `recording` flag, `silence_count`, `speech_frames`)
- `cyrus2/tests/conftest.py` — shared fixtures (mock_logger, mock_config, mock_send)
- No test file for VAD logic

**What was needed:**
- `cyrus2/tests/test_vad_logic.py` — 15 test cases covering all acceptance criteria
- `mock_silero_model` fixture added to `conftest.py`

## Prioritized Tasks

- [x] Understand `vad_loop()` structure (procedural, not class-based)
- [x] Design mock strategy for hardware deps (torch, sounddevice, numpy, etc.)
- [x] Write `_make_model_mock()` helper — controls per-frame probabilities + sets _shutdown
- [x] Write `_make_stream_mock()` helper — returns silent frames indefinitely
- [x] Write `_run_vad()` helper — runs `vad_loop()` in thread with live asyncio loop
- [x] Write `_run_vad_with_delayed_shutdown()` — for muted-mic tests
- [x] Implement `TestRingBufferManagement` (3 tests)
- [x] Implement `TestVADStateTransitions` (5 tests)
- [x] Implement `TestSilenceDetection` (3 tests)
- [x] Implement `TestTimeoutBehavior` (2 tests)
- [x] Implement `TestEdgeCases` (2 tests)
- [x] Add `mock_silero_model` fixture to `conftest.py`
- [x] Fix all ruff lint errors (E501, F841)
- [x] Verify all 620 suite tests pass

## Acceptance-Driven Tests

| Acceptance Criterion | Test(s) | Status |
|---|---|---|
| 15+ test cases | 15 tests across 5 classes | ✅ |
| VAD state transitions (~5) | `TestVADStateTransitions` × 5 | ✅ |
| Ring buffer management (~3) | `TestRingBufferManagement` × 3 | ✅ |
| Silence detection (~3) | `TestSilenceDetection` × 3 | ✅ |
| Timeout behavior (~2) | `TestTimeoutBehavior` × 2 | ✅ |
| Edge cases (~2) | `TestEdgeCases` × 2 | ✅ |
| `pytest tests/test_vad_logic.py -v` passes | All 15 PASSED | ✅ |

## Implementation Notes

### Key design decisions

1. **Write tests against existing `vad_loop()` — no refactoring.** The issue's
   interview answers (Q1/Q2) both point to working with the procedural
   implementation rather than introducing a class-based state machine.

2. **Mock all hardware at `sys.modules` level before import.** `cyrus_voice.py`
   imports `torch`, `sounddevice`, `keyboard`, `pygame`, `numpy`,
   `faster_whisper`, and `silero_vad` at module level. These are not available
   in the dev venv, so they are inserted into `sys.modules` as `MagicMock()`
   before the import.

3. **`torch.cuda.is_available()` forced to `False`.** The module-level
   `_CUDA = torch.cuda.is_available()` line runs at import time. A
   default `MagicMock()` is truthy, which would cause unexpected branches.
   The torch mock is configured so `cuda.is_available()` returns `False`.

4. **Path fix: two directories on `sys.path`.** `cyrus_voice.py` does
   `from cyrus2.cyrus_log import setup_logging`, which requires the PARENT
   of `cyrus2/` to be on `sys.path` (i.e. `.../cyrus/`). The tests also
   need `.../cyrus/cyrus2/` for `import cyrus_voice` to succeed.

5. **Live asyncio event loop in a daemon thread.** `vad_loop()` calls
   `loop.call_soon_threadsafe(on_utterance, audio)`. The loop must be
   running for the callback to execute. A dedicated daemon thread runs
   `loop.run_forever()`, and a threading.Event barrier ensures callbacks
   are flushed before the test collects results.

6. **`_RAISE` sentinel for exception injection.** `_make_model_mock()`
   accepts a mix of floats and the `_RAISE` sentinel. When `_RAISE` is
   encountered, the mock's `side_effect` raises `RuntimeError`, which
   `vad_loop()`'s `except Exception: continue` swallows gracefully.

7. **Muted-mic tests use delayed shutdown.** When `_mic_muted` is set,
   the model is never called so the normal shutdown path (exhausting
   probabilities) never fires. A daemon timer thread sets `_shutdown`
   after 0.3 s to terminate the loop cleanly.

### Files created / modified

- **Created**: `cyrus2/tests/test_vad_logic.py` (15 tests, 633 lines)
- **Modified**: `cyrus2/tests/conftest.py` (added `mock_silero_model` fixture)

## Verification Checklist

- [x] `uv run ruff check tests/test_vad_logic.py tests/conftest.py` — clean
- [x] `uv run pytest tests/test_vad_logic.py -v` — 15 passed
- [x] `uv run pytest -q` — 620 passed (full suite, no regressions)
