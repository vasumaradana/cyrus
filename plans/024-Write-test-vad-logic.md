# Plan 024: Write test_vad_logic.py (Tier 3)

## Summary

Create `cyrus2/tests/test_vad_logic.py` with 16 test cases covering the VAD (Voice Activity Detection) logic in `cyrus_voice.py`. The VAD logic is a **procedural function** (`vad_loop()`) with inline state — not a class-based state machine. Tests mock the Silero model, sounddevice stream, and threading events to exercise the algorithm in isolation: speech onset detection via ring buffer, recording accumulation, adaptive silence thresholds, max-duration timeout, and graceful error handling.

## Prerequisites

- **Issue 018** (state: PLANNED) — creates `cyrus2/tests/` directory, `conftest.py`, `pyproject.toml` with `pythonpath = [".."]`. If not yet built, the builder must create the minimal directory structure and pytest config.
- **Issue 005** (state: PLANNED) — cyrus_common.py foundation. `vad_loop()` has no dependency on it. The function lives in `cyrus_voice.py` at the project root.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/tests/test_vad_logic.py` | Does not exist | Create with 16 test cases |
| `cyrus2/tests/` directory | Does not exist (created by issue 018) | Verify exists; create if missing |
| `cyrus2/tests/__init__.py` | Does not exist (created by issue 018) | Verify exists; create if missing |
| `cyrus2/pyproject.toml` with `pythonpath = [".."]` | Does not exist (created by issue 018) | Verify exists; create if missing |
| `cyrus_voice.py` importable | Source at cyrus root | Import via `pythonpath = [".."]` in pytest config |
| conftest fixture for mock Silero | Issue mentions adding to conftest.py | Keep local — VAD-specific mocks don't belong in shared fixtures |

## Interview Question Resolution

The issue contains two interview questions about the mismatch between the issue's class-based terminology (VADStateMachine, RingBuffer) and the actual procedural implementation.

**Decision: Test the existing procedural `vad_loop()` function directly.**

- No refactoring of VAD logic into classes — that belongs in a separate issue
- Acceptance criteria are reinterpreted to match the functional implementation:
  - "state machine transitions" → behavioral transitions observed through callback invocations
  - "ring buffer management" → deque behavior verified through utterance audio content
  - "idle→listening→speaking" → not-recording → ring fills → recording → callback
- Tests exercise the algorithm through its public interface: `vad_loop(on_utterance, loop)`

## Source Code Under Test

### `vad_loop(on_utterance, loop)` — cyrus_voice.py:281-348

```python
def vad_loop(on_utterance, loop: asyncio.AbstractEventLoop):
    model         = load_silero_vad()
    ring: deque   = deque(maxlen=SPEECH_RING)       # maxlen=9
    recording     = False
    frames: list  = []
    silence_count = 0
    speech_frames = 0

    with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                           dtype="int16", blocksize=FRAME_SIZE) as stream:
        while not _shutdown.is_set():
            # BRANCH A: muted/paused — drain audio, cancel recording
            if _mic_muted.is_set() or _user_paused.is_set():
                stream.read(FRAME_SIZE)
                ring.clear()
                if recording:
                    frames.clear()
                    recording     = False
                    silence_count = 0
                time.sleep(0.01)
                continue

            # BRANCH B: normal — read frame, run VAD model
            raw, _ = stream.read(FRAME_SIZE)
            frame_bytes = bytes(raw)
            try:
                chunk = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                with torch.no_grad():
                    prob = model(torch.from_numpy(chunk), SAMPLE_RATE).item()
                is_speech = prob > SPEECH_THRESHOLD
            except Exception:
                continue

            # PHASE 1: not recording — accumulate ring, check onset
            if not recording:
                ring.append((frame_bytes, is_speech))
                num_voiced = sum(1 for _, s in ring if s)
                if (len(ring) == ring.maxlen
                        and num_voiced / ring.maxlen >= SPEECH_RATIO):
                    recording     = True
                    frames        = [fb for fb, _ in ring]    # pre-speech buffer
                    silence_count = 0
                    speech_frames = 0
                    ring.clear()
            # PHASE 2: recording — accumulate frames, detect end
            else:
                frames.append(frame_bytes)
                if is_speech:
                    silence_count = 0
                    speech_frames += 1
                else:
                    silence_count += 1

                adaptive_ring = (SILENCE_RING * 2           # 62
                                 if speech_frames * FRAME_MS > 1500
                                 else SILENCE_RING)          # 31
                timed_out = len(frames) >= MAX_RECORD_FRAMES  # 375
                if silence_count >= adaptive_ring or timed_out:
                    raw_audio = b"".join(frames)
                    audio = (np.frombuffer(raw_audio, dtype=np.int16)
                               .astype(np.float32) / 32768.0)
                    recording     = False
                    frames        = []
                    silence_count = 0
                    speech_frames = 0
                    ring.clear()
                    model.reset_states()
                    loop.call_soon_threadsafe(on_utterance, audio)
```

### Key constants

| Constant | Value | Derivation |
|---|---|---|
| `SPEECH_THRESHOLD` | 0.5 | VAD confidence threshold |
| `FRAME_SIZE` | 512 | Samples per frame (int16) |
| `FRAME_MS` | 32 | Milliseconds per frame |
| `SPEECH_RING` | 9 | 300ms // 32ms — ring buffer size for onset detection |
| `SILENCE_RING` | 31 | 1000ms // 32ms — standard silence frames to end recording |
| `MAX_RECORD_FRAMES` | 375 | 12000ms // 32ms — max recording length |
| `SPEECH_RATIO` | 0.80 | 80% of ring frames must be speech for onset |

### Key behaviors

1. **Speech onset**: Ring buffer (maxlen=9) fills with `(frame_bytes, is_speech)` tuples. When ring is full AND `num_voiced / 9 >= 0.80` (at least 8/9 frames speech), recording starts. Ring contents become the pre-speech buffer.
2. **Recording**: Each frame appended. Speech frames reset `silence_count`, increment `speech_frames`. Silence frames increment `silence_count`.
3. **Adaptive silence**: If `speech_frames * 32 > 1500` (speech longer than ~1.5s), silence threshold doubles from 31 to 62 frames. This prevents cutting off mid-sentence pauses during long utterances.
4. **End conditions**: `silence_count >= adaptive_ring` OR `len(frames) >= 375`. On end: audio assembled, state reset, `model.reset_states()` called, callback fired via `loop.call_soon_threadsafe`.
5. **Muted/paused**: Ring cleared, recording cancelled (frames discarded), audio drained.
6. **Model exception**: Caught by `except Exception: continue` — frame skipped, loop continues.

## Design Decisions

### 1. Mock strategy: `MockInputStream` + mock Silero model

The test harness mocks two things:

- **`sd.RawInputStream`** → `MockInputStream` context manager that feeds pre-built frame bytes and triggers `_shutdown` when frames are exhausted
- **`load_silero_vad()`** → Mock model where each call returns a mock with `.item()` returning the next probability from a pre-defined list

The mock stream returns `bytes(FRAME_SIZE * 2)` (512 zero int16 samples = 1024 bytes) for every `read()` call. Since the model is mocked, actual audio content doesn't matter — only the probability sequence controls behavior.

### 2. Test runner helper: `_run_vad(probs)`

A shared helper function runs `vad_loop()` with controlled inputs:

```python
def _run_vad(probs: list[float]) -> tuple[list[np.ndarray], Mock]:
    """Run vad_loop with controlled VAD probabilities.

    Args:
        probs: List of VAD probabilities (one per non-muted frame).
               Values > 0.5 are speech, <= 0.5 are silence.

    Returns:
        (utterances, model_mock) — list of captured audio arrays,
        and the mock model for assertion on reset_states() calls.
    """
```

The helper:
1. Clears `_shutdown`, `_mic_muted`, `_user_paused` events
2. Creates `MockInputStream` sized to `len(probs)` frames + 1 shutdown frame
3. Creates mock model with side_effect returning controlled probabilities
4. Patches `load_silero_vad`, `sd.RawInputStream`, `time.sleep`
5. Runs `vad_loop()` synchronously
6. Returns captured utterances and model mock

### 3. Patch `time.sleep` for test speed

The muted branch calls `time.sleep(0.01)`. Patch to no-op to avoid test latency.

### 4. Use `loop.call_soon_threadsafe` as direct call

Mock the event loop so `call_soon_threadsafe(fn, arg)` calls `fn(arg)` directly, capturing utterances in a list.

### 5. Verify audio length, not content

Since all mock frames are zero bytes, we can't verify audio content meaningfully. Instead verify:
- Number of utterances (callback count)
- Audio sample count: `len(utterance) == expected_frame_count * FRAME_SIZE`
- `model.reset_states()` call count

### 6. Import strategy

```python
from cyrus_voice import (
    vad_loop, SPEECH_THRESHOLD, SPEECH_RING, SILENCE_RING,
    MAX_RECORD_FRAMES, SPEECH_RATIO, FRAME_SIZE, FRAME_MS,
    _shutdown, _mic_muted, _user_paused,
)
```

Direct import from `cyrus_voice.py` via `pythonpath = [".."]` in pytest config. The module has heavy imports (torch, sounddevice, keyboard, pygame, silero_vad, faster_whisper) — all must be installed. If imports fail, flag as STUCK.

### 7. No conftest fixtures needed

The issue suggests adding a `mock_silero_model` fixture to conftest. However, the mock setup is specific to VAD tests and tightly coupled to the `_run_vad()` helper. Keeping mocks local avoids polluting shared fixtures. The conftest fixtures from issue 018 (mock_config, mock_logger, etc.) are not used by these tests.

### 8. Update conftest.py — skip per issue instruction

The issue's "Files to Create/Modify" lists updating `cyrus2/tests/conftest.py` to add `mock_silero_model`. Since we keep mocks local (decision #7), **no conftest changes are needed**. This is a deliberate deviation from the issue's suggestion, justified by the test design.

## Acceptance Criteria → Test Mapping

| AC | Requirement | Tests | Count |
|---|---|---|---|
| AC1 | `cyrus2/tests/test_vad_logic.py` exists with 15+ test cases | File exists, `pytest --collect-only` shows 16 items | 16 |
| AC2 | VAD state machine transitions tested (~5 cases) | `test_speech_onset_emits_utterance`, `test_continued_speech_then_silence`, `test_brief_silence_no_end`, `test_two_separate_utterances`, `test_below_ratio_no_onset` | 5 |
| AC3 | Ring buffer management tested (~3 cases) | `test_pre_speech_buffer_in_utterance`, `test_ring_respects_maxlen`, `test_ring_resets_between_utterances` | 3 |
| AC4 | Silence detection tested (~3 cases) | `test_standard_silence_threshold`, `test_adaptive_silence_long_speech`, `test_silence_resets_on_speech` | 3 |
| AC5 | Timeout behavior tested (~2 cases) | `test_max_record_timeout`, `test_silence_ends_before_timeout` | 2 |
| AC6 | Edge cases tested (~2 cases) | `test_all_silence_no_utterance`, `test_model_exception_handled`, `test_muted_cancels_recording` | 3 |
| AC7 | All tests pass: `pytest tests/test_vad_logic.py -v` | Exit code 0, 16 passed | — |

## Test Case Inventory

### MockInputStream design

```python
class MockInputStream:
    """Context manager replacing sd.RawInputStream for testing.

    Feeds a fixed number of zero-filled frames, then triggers _shutdown
    to exit vad_loop cleanly.
    """

    def __init__(self, num_frames: int, *, events: dict[int, callable] | None = None):
        self._remaining = num_frames
        self._index = 0
        self._events = events or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, blocksize):
        if self._index in self._events:
            self._events[self._index]()
        if self._remaining <= 0:
            _shutdown.set()
            return bytes(blocksize * 2), False
        self._remaining -= 1
        self._index += 1
        return bytes(blocksize * 2), False
```

### Mock model design

```python
def _make_model(probs: list[float]) -> Mock:
    """Create a mock Silero model returning controlled probabilities."""
    model = Mock()
    results = [Mock(**{"item.return_value": p}) for p in probs]
    model.side_effect = results
    model.reset_states = Mock()
    return model
```

After the probs list is exhausted, `model()` raises `StopIteration`, which is caught by the `except Exception: continue` in `vad_loop()`. The mock stream will then trigger shutdown on the next read.

### Group 1: State machine transitions (5 cases)

| # | Test ID | Probs sequence | Expected |
|---|---------|---------------|----------|
| 1 | `test_speech_onset_emits_utterance` | 9 × 0.9 (onset) + 31 × 0.1 (silence) | 1 utterance, audio length = (9+31) × 512 samples |
| 2 | `test_continued_speech_then_silence` | 9 × 0.9 (onset) + 20 × 0.9 (speech) + 31 × 0.1 (silence) | 1 utterance, audio = (9+20+31) × 512 |
| 3 | `test_brief_silence_no_end` | 9 × 0.9 (onset) + 10 × 0.9 + 15 × 0.1 (< 31) + 10 × 0.9 + 31 × 0.1 | 1 utterance (brief silence doesn't end recording) |
| 4 | `test_two_separate_utterances` | 9 × 0.9 + 31 × 0.1 (utt 1) + 9 × 0.9 + 31 × 0.1 (utt 2) | 2 utterances |
| 5 | `test_below_ratio_no_onset` | 9 frames: 7 × 0.9 + 2 × 0.1 (7/9 = 0.778 < 0.80) + 40 × 0.1 | 0 utterances |

**Test 1 details** — The simplest complete cycle:
- Frames 0-8: prob=0.9 → ring fills, 9/9=1.0 ≥ 0.80 → recording starts on frame 8
- Frames 9-39: prob=0.1 → silence_count increments, speech_frames=0
- Frame 39: silence_count=31 ≥ SILENCE_RING(31) → utterance emitted
- Assert: `len(utterances) == 1`, `len(utterances[0]) == 40 * 512`
- Assert: `model.reset_states.call_count == 1`

**Test 3 details** — Brief silence is NOT long enough to end recording:
- After onset: 10 speech + 15 silence (silence_count=15 < 31) + 10 speech (resets silence_count) + 31 silence
- Total recording frames: 10 + 15 + 10 + 31 = 66
- speech_frames = 20 (only the speech frames counted), 20 × 32 = 640ms < 1500ms → standard silence threshold
- Audio: (9 + 66) × 512 = 75 × 512 samples

**Test 4 details** — Two separate utterances verify state reset between utterances:
- First: 9 onset + 31 silence → utterance 1
- After utterance 1: recording=False, ring cleared, model.reset_states() called
- Second: new ring fills (9 frames) → recording → 31 silence → utterance 2
- Assert: `len(utterances) == 2`, `model.reset_states.call_count == 2`

**Test 5 details** — Speech ratio at boundary:
- Ring fills with 7 speech + 2 silence = 7/9 = 0.778 < 0.80 → no onset
- Ring then slides: new silence frames push out old speech frames → ratio drops further
- After all frames: no recording ever started, no callback
- Assert: `len(utterances) == 0`

### Group 2: Ring buffer management (3 cases)

| # | Test ID | Description | Verification |
|---|---------|-------------|--------------|
| 6 | `test_pre_speech_buffer_in_utterance` | Ring contents (9 frames) transferred to recording on onset | Audio length includes ring frames: onset + 1 speech + silence → (9 + 1 + 31) × 512 |
| 7 | `test_ring_respects_maxlen` | Feed >9 sub-threshold frames → ring doesn't grow past 9 | Next 9 speech frames trigger onset → audio = exactly (9 + 31) × 512, not more |
| 8 | `test_ring_resets_between_utterances` | After first utterance, second onset requires 9 fresh frames | Second utterance audio length includes exactly 9 ring frames |

**Test 6 details** — Pre-speech buffer inclusion:
- Feed 9 speech frames (onset) → recording starts, `frames = [9 frame_bytes from ring]`
- Feed 1 speech frame + 31 silence → end
- Audio = (9 + 1 + 31) × 512 = 41 × 512 = 20992 samples
- The 9 frames come from the ring buffer (pre-speech buffer), proving inclusion
- Probs: 9 × 0.9 + 1 × 0.9 + 31 × 0.1 = 41 total

**Test 7 details** — Ring maxlen enforcement:
- Feed 20 frames with prob=0.4 (all silence, ring fills but never triggers onset)
- Then feed 9 frames with prob=0.9 → these push out silence frames from ring → ratio=9/9=1.0 → onset
- Feed 31 × 0.1 → utterance
- Audio = (9 + 31) × 512 — NOT (20 + 9 + 31) × 512
- This proves the ring respects maxlen and doesn't accumulate unboundedly
- Probs: 20 × 0.4 + 9 × 0.9 + 31 × 0.1 = 60 total

**Test 8 details** — Ring reset between utterances:
- Same probs as test 4 (two utterances: 9+31 + 9+31 = 80 probs)
- Verify both utterances have the same audio length: (9 + 31) × 512 = 20480 samples each
- If the ring weren't reset after utterance 1, the second onset would behave differently

### Group 3: Silence detection (3 cases)

| # | Test ID | Probs sequence | Expected |
|---|---------|---------------|----------|
| 9 | `test_standard_silence_threshold` | 9 × 0.9 + 10 × 0.9 + 31 × 0.1 | 1 utterance at silence_count=31 |
| 10 | `test_adaptive_silence_long_speech` | 9 × 0.9 + 47 × 0.9 + 62 × 0.1 | 1 utterance at silence_count=62 (adaptive) |
| 11 | `test_silence_resets_on_speech` | 9 × 0.9 + 5 × 0.9 + 20 × 0.1 + 5 × 0.9 + 31 × 0.1 | 1 utterance (silence_count reset mid-recording) |

**Test 9 details** — Standard (short speech) silence threshold:
- Onset → 10 speech frames (speech_frames=10, 10×32=320ms < 1500ms → standard threshold)
- 31 silence frames → silence_count=31 ≥ SILENCE_RING(31) → end
- Audio: (9 + 10 + 31) × 512 = 50 × 512

**Test 10 details** — Adaptive (long speech) silence threshold:
- Onset → 47 speech frames (speech_frames=47, 47×32=1504ms > 1500ms → adaptive)
- `adaptive_ring = SILENCE_RING * 2 = 62`
- 62 silence frames → silence_count=62 ≥ 62 → end
- If standard threshold applied, 31 silence would end it at (9+47+31)×512 — but adaptive requires 62
- Audio: (9 + 47 + 62) × 512 = 118 × 512

**Test 11 details** — Silence counter resets when speech resumes:
- Onset → 5 speech + 20 silence (count=20 < 31) + 5 speech (count resets to 0) + 31 silence (count=31)
- speech_frames = 10 total (5+5), 10×32=320ms < 1500ms → standard threshold
- Audio: (9 + 5 + 20 + 5 + 31) × 512 = 70 × 512

### Group 4: Timeout behavior (2 cases)

| # | Test ID | Probs sequence | Expected |
|---|---------|---------------|----------|
| 12 | `test_max_record_timeout` | 9 × 0.9 + 366 × 0.9 | 1 utterance at frame 375 (MAX_RECORD_FRAMES) |
| 13 | `test_silence_ends_before_timeout` | 9 × 0.9 + 10 × 0.9 + 31 × 0.1 | 1 utterance well before timeout |

**Test 12 details** — Max recording duration:
- Onset → 366 continuous speech frames (all prob=0.9)
- After onset, frames starts at 9 (ring). Each recording frame appends 1.
- After 366 recording frames: len(frames) = 9 + 366 = 375 ≥ MAX_RECORD_FRAMES(375)
- `timed_out = True` → utterance emitted even though silence_count=0
- Audio: 375 × 512 = 192000 samples
- Total probs: 9 + 366 = 375

**Test 13 details** — Normal end well before timeout:
- Onset → 10 speech (speech_frames=10, 10×32=320ms < 1500ms → standard threshold)
- 31 silence → silence_count=31 ≥ 31 → end
- Total frames: 9 + 10 + 31 = 50 << 375 (MAX_RECORD_FRAMES)
- Audio: 50 × 512 — far before max timeout
- This verifies silence ends recording normally when no timeout pressure exists

### Group 5: Edge cases (3 cases)

| # | Test ID | Description | Expected |
|---|---------|-------------|----------|
| 14 | `test_all_silence_no_utterance` | 100 frames all prob=0.1 | 0 utterances, no callback |
| 15 | `test_model_exception_handled` | Model raises on frame 5, then normal speech+silence | 1 utterance (exception frame skipped) |
| 16 | `test_muted_cancels_recording` | Onset → 5 speech → mute → unmute → new onset → silence | 1 utterance (first recording cancelled) |

**Test 14 details** — All silence:
- 100 frames, all prob=0.1 → ring fills with non-speech, ratio=0/9=0 < 0.80
- Recording never starts
- Assert: `len(utterances) == 0`, `model.reset_states.call_count == 0`

**Test 15 details** — Model exception graceful handling:
- Feed a sequence where the mock model raises `RuntimeError` on a specific call
- Other frames are normal speech + silence
- The exception frame is skipped (`except Exception: continue`)
- Utterance still captured from the remaining frames
- Implementation: use a custom side_effect function that raises on a specific call index

**Test 16 details** — Muted during recording:
- This test requires controlling `_mic_muted` at a specific frame. Use MockInputStream's `events` dict to set/clear `_mic_muted` at specific frame indices during `read()`.
- Frame sequence:
  - Frames 0-8: normal → onset (model called 9×, prob=0.9)
  - Frames 9-13: normal → recording (model called 5×, prob=0.9)
  - Frame 13: `read()` triggers `_mic_muted.set()`
  - Frames 14-16: muted → recording cancelled (model NOT called, `time.sleep` mocked)
  - Frame 16: `read()` triggers `_mic_muted.clear()`
  - Frames 17-25: normal → new onset (model called 9×, prob=0.9)
  - Frames 26-56: normal → silence (model called 31×, prob=0.1)
  - Frame 57+: shutdown
- Model probs: 9 + 5 + 9 + 31 = 54 values (muted frames don't call model)
- Stream frames: 57 total (14 normal + 3 muted + 40 normal)
- Expected: 1 utterance (from the second recording), not 2

## Implementation Steps

### Step 1: Verify test infrastructure exists

```bash
cd /home/daniel/Projects/barf/cyrus

# Check issue 018 artifacts
test -d cyrus2/tests/ && echo "OK: tests dir" || echo "MISSING: tests dir"
test -f cyrus2/tests/__init__.py && echo "OK: __init__" || echo "MISSING: __init__"
test -f cyrus2/pyproject.toml && echo "OK: pyproject.toml" || echo "MISSING: pyproject.toml"
```

If anything is missing, create:

```bash
mkdir -p cyrus2/tests
touch cyrus2/tests/__init__.py
```

If `pyproject.toml` doesn't exist:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = [".."]
```

**Critical:** `pythonpath = [".."]` adds the cyrus root to `sys.path` so `from cyrus_voice import vad_loop` resolves from `cyrus2/tests/`.

### Step 2: Create `cyrus2/tests/test_vad_logic.py`

Write the file with all 16 test cases. Complete file structure:

```python
"""Tier 3 VAD (Voice Activity Detection) logic tests.

Tests cover:
    State transitions — speech onset, recording, silence end, two-utterance cycle
    Ring buffer       — pre-speech buffer inclusion, maxlen enforcement, inter-utterance reset
    Silence detection — standard threshold, adaptive threshold, counter reset on speech
    Timeout           — max recording duration, normal silence end before timeout
    Edge cases        — all-silence input, model exception handling, muted during recording

Mocking strategy:
    - sd.RawInputStream  → MockInputStream (feeds zero-filled frames, triggers shutdown)
    - load_silero_vad()  → Mock model returning controlled probabilities
    - time.sleep         → no-op (avoid test latency from muted branch)
    - asyncio event loop → Mock with call_soon_threadsafe calling callback directly

All VAD constants (SPEECH_RING, SILENCE_RING, etc.) are imported from cyrus_voice
and used in assertions, so tests stay correct if constants change.
"""

from __future__ import annotations

from collections import deque
from unittest.mock import Mock, patch, MagicMock

import numpy as np
import pytest

from cyrus_voice import (
    vad_loop,
    FRAME_SIZE,
    FRAME_MS,
    SPEECH_RING,
    SILENCE_RING,
    SPEECH_THRESHOLD,
    SPEECH_RATIO,
    MAX_RECORD_FRAMES,
    _shutdown,
    _mic_muted,
    _user_paused,
)


# ── Test helpers ──────────────────────────────────────────────────────────────

class MockInputStream:
    """Mock sd.RawInputStream: feeds N zero-filled frames, then triggers shutdown."""

    def __init__(self, num_frames: int, *, events: dict[int, callable] | None = None):
        self._remaining = num_frames
        self._index = 0
        self._events = events or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, blocksize):
        if self._index in self._events:
            self._events[self._index]()
        if self._remaining <= 0:
            _shutdown.set()
            return bytes(blocksize * 2), False
        self._remaining -= 1
        self._index += 1
        return bytes(blocksize * 2), False


def _make_model(probs: list[float]) -> Mock:
    """Create mock Silero VAD model returning controlled probabilities."""
    model = Mock()
    results = [Mock(**{"item.return_value": p}) for p in probs]
    model.side_effect = results
    model.reset_states = Mock()
    return model


def _run_vad(probs: list[float], *, stream_events=None):
    """Run vad_loop with controlled inputs, return (utterances, model_mock)."""
    # ... setup, patching, run, return
```

### Step 3: Implement test helpers and all 16 tests

Implement `_run_vad()` helper and all test functions following the test inventory above. Group tests with comment headers matching acceptance criteria categories.

### Step 4: Run tests and iterate

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_vad_logic.py -v
```

Expected: 16 test items pass. If any fail, trace the probability sequence through the algorithm step by step.

Common failure modes:
- **Import errors**: Missing production dependencies (torch, sounddevice, etc.) — flag as STUCK
- **Off-by-one in frame counts**: Ring → recording transition boundary. Double-check whether the onset frame is counted in ring or recording.
- **Mock model exhaustion**: If probs list is too short, `StopIteration` is caught but the frame is skipped. This can change expected audio length.
- **Adaptive threshold not triggering**: Verify `speech_frames * FRAME_MS > 1500` — note the `>` (not `>=`). 46 frames × 32 = 1472 < 1500, 47 × 32 = 1504 > 1500.

### Step 5: Verify test count

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_vad_logic.py --collect-only -q | tail -1
```

Expected: `16 tests collected` (exceeds the 15+ requirement).

### Step 6: Run subset commands from acceptance criteria

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_vad_logic.py -k "onset or continued or brief or two_utterances or below_ratio" -v
pytest tests/test_vad_logic.py -k "buffer or maxlen or resets_between" -v
pytest tests/test_vad_logic.py -k "silence" -v
pytest tests/test_vad_logic.py -k "timeout" -v
pytest tests/test_vad_logic.py -k "all_silence or exception or muted" -v
```

All should pass independently.

## Files Created/Modified

| File | Action | Description |
|---|---|---|
| `cyrus2/tests/test_vad_logic.py` | **Create** | 16 test cases across 16 test functions covering VAD state transitions, ring buffer, silence detection, timeout, and edge cases |
| `cyrus2/tests/` directory | **Verify** | Must exist (from issue 018); create if missing |
| `cyrus2/tests/__init__.py` | **Verify** | Must exist (from issue 018); create if missing |
| `cyrus2/pyproject.toml` | **Verify** | Must have `pythonpath = [".."]`; create if missing |

## Import Risk

**Moderate risk.** `cyrus_voice.py` imports at module level:

```python
import numpy as np           # Usually available
import sounddevice as sd      # Needs audio subsystem
import keyboard               # Needs root or input group on Linux
import pygame                 # Needs display/audio
import torch                  # Heavy but standard for ML
from silero_vad import load_silero_vad    # Silero VAD package
from faster_whisper import WhisperModel   # Whisper bindings
```

If any of these fail, `from cyrus_voice import vad_loop` will raise `ModuleNotFoundError` before any test runs.

**Mitigation**: Run on the dev machine where Cyrus is deployed (all deps installed). If imports fail, flag as STUCK — fixing conditional imports is a separate issue.
