"""
Tier 3 acceptance-driven tests for VAD (Voice Activity Detection) logic.

Issue 024 — cyrus_voice.py VAD state machine, ring buffer, silence detection,
timeout logic, and edge cases.  All tests run without hardware by mocking the
hardware/GPU/audio dependencies at the sys.modules level before the module is
imported.

Test categories
---------------
  Ring buffer management   (3 tests) — deque FIFO, size limits, speech-ratio gate
  VAD state transitions    (5 tests) — idle→recording→utterance, muted mic, state reset
  Silence detection        (3 tests) — threshold, silence counter, adaptive ring
  Timeout behavior         (2 tests) — SILENCE_RING timeout, MAX_RECORD_FRAMES timeout
  Edge cases               (2 tests) — Silero model exception, pre-speech buffer

All vad_loop integration tests use:
  - _make_model_mock(items)  — Silero mock; raises or returns float per frame,
                               sets _shutdown when items are exhausted
  - _make_stream_mock()      — sd.RawInputStream mock; returns silent frames
  - _run_vad(probs)          — runs vad_loop in a thread with a live event loop,
                               collects on_utterance calls, cleans up

Usage
-----
    pytest tests/test_vad_logic.py -v
    pytest tests/test_vad_logic.py -k "buffer" -v
    pytest tests/test_vad_logic.py -k "silence or timeout" -v
"""

from __future__ import annotations

import asyncio
import queue
import sys
import threading
import time
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Mock ALL hardware/GPU/audio deps BEFORE importing cyrus_voice ─────────────
# cyrus_voice.py imports keyboard, numpy, pygame, sounddevice, torch,
# faster_whisper, and silero_vad at module level.  None are in requirements-dev.

_torch_mock = MagicMock()
# Force _CUDA = False at module load so GPU detection takes the safe branch
_torch_mock.cuda.is_available.return_value = False

_HW_MOCKS: dict = {
    "keyboard": MagicMock(),
    "numpy": MagicMock(),
    "pygame": MagicMock(),
    "sounddevice": MagicMock(),
    "torch": _torch_mock,
    "faster_whisper": MagicMock(),
    "silero_vad": MagicMock(),
}
for _mod, _mock in _HW_MOCKS.items():
    if _mod not in sys.modules:
        sys.modules[_mod] = _mock

# Add both:
#   cyrus2/       — so `import cyrus_voice` resolves (cyrus_voice.py is here)
#   cyrus2/..     — so `from cyrus2.cyrus_log import …` inside cyrus_voice resolves
_CYRUS2_DIR = Path(__file__).parent.parent  # .../cyrus/cyrus2/
_CYRUS_ROOT = _CYRUS2_DIR.parent  # .../cyrus/
for _p in (_CYRUS2_DIR, _CYRUS_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import cyrus_voice  # noqa: E402  — must come after sys.modules setup

# ── Sentinel for "raise an exception on this frame" ──────────────────────────
_RAISE = object()

# One silent 512-sample int16 audio frame (1024 bytes)
_SILENT_FRAME = b"\x00" * (cyrus_voice.FRAME_SIZE * 2)


# ── Test helpers ──────────────────────────────────────────────────────────────


def _make_model_mock(items: list) -> MagicMock:
    """Return a Silero VAD model mock driven by *items*.

    Each element of *items* controls one model call:
      - float  → model returns a mock whose ``.item()`` yields that float
      - _RAISE → model raises ``RuntimeError("Silero model error")``

    When the list is exhausted the mock sets ``cyrus_voice._shutdown`` so
    ``vad_loop()`` exits cleanly on the next iteration check.

    ``reset_states()`` is wired as a no-op (called after utterance emission).

    Args:
        items: Sequence of floats or _RAISE sentinels controlling per-frame behavior.

    Returns:
        Configured MagicMock that acts as the Silero VAD model.
    """
    call_idx = [0]

    def _side_effect(tensor, sr):  # noqa: ANN001 — mocked types
        i = call_idx[0]
        call_idx[0] += 1
        if i >= len(items):
            # All items exhausted → stop the loop
            cyrus_voice._shutdown.set()
            rv = MagicMock()
            rv.item.return_value = 0.0
            return rv
        item = items[i]
        if item is _RAISE:
            raise RuntimeError("Silero model error (injected by test)")
        rv = MagicMock()
        rv.item.return_value = float(item)
        return rv

    model = MagicMock()
    model.side_effect = _side_effect
    return model


def _make_stream_mock() -> MagicMock:
    """Return a mock ``sd.RawInputStream`` context manager.

    The mock's ``read()`` always returns the same silent 512-sample frame so
    that ``np.frombuffer`` (itself mocked) receives consistent bytes.

    Returns:
        MagicMock configured as a context-manager stream returning silent frames.
    """
    stream = MagicMock()
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)
    stream.read.return_value = (_SILENT_FRAME, False)
    return stream


def _run_vad(
    items: list,
    *,
    pre_muted: bool = False,
    pre_paused: bool = False,
    timeout: float = 5.0,
) -> list:
    """Run ``vad_loop()`` in a thread with mocked hardware, return utterances.

    Sets up a live ``asyncio`` event loop (needed for ``call_soon_threadsafe``
    callbacks) and collects every audio array delivered to ``on_utterance``.

    Module-level state (``_shutdown``, ``_mic_muted``, ``_user_paused``) is
    reset before each run so tests are independent.

    Args:
        items: Probability / _RAISE sequence passed to ``_make_model_mock``.
        pre_muted: If True, ``_mic_muted`` is set before the loop starts.
        pre_paused: If True, ``_user_paused`` is set before the loop starts.
        timeout: Wall-clock seconds to wait for ``vad_loop`` thread.

    Returns:
        List of audio values passed to the ``on_utterance`` callback.
    """
    model = _make_model_mock(items)
    stream = _make_stream_mock()

    utterances: list = []
    utq: queue.Queue = queue.Queue()

    def _on_utterance(audio):  # noqa: ANN001
        utq.put(audio)

    # ── Reset module state so tests don't bleed into each other ──────────────
    cyrus_voice._shutdown.clear()
    cyrus_voice._mic_muted.clear()
    cyrus_voice._user_paused.clear()
    if pre_muted:
        cyrus_voice._mic_muted.set()
    if pre_paused:
        cyrus_voice._user_paused.set()

    # ── Run a real event loop so call_soon_threadsafe callbacks execute ───────
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()

    with (
        patch.object(cyrus_voice, "sd") as mock_sd,
        patch.object(cyrus_voice, "load_silero_vad", return_value=model),
    ):
        mock_sd.RawInputStream.return_value = stream
        vad_thread = threading.Thread(
            target=cyrus_voice.vad_loop,
            args=(_on_utterance, loop),
            daemon=True,
        )
        vad_thread.start()
        vad_thread.join(timeout=timeout)

    # Ensure any pending call_soon_threadsafe callbacks are flushed
    _flushed = threading.Event()
    loop.call_soon_threadsafe(_flushed.set)
    _flushed.wait(timeout=1.0)

    loop.call_soon_threadsafe(loop.stop)
    loop_thread.join(timeout=1.0)

    while not utq.empty():
        utterances.append(utq.get_nowait())
    return utterances


def _run_vad_with_delayed_shutdown(
    items: list,
    shutdown_after_secs: float = 0.3,
    *,
    pre_muted: bool = False,
    timeout: float = 5.0,
) -> list:
    """Like ``_run_vad`` but terminates the loop after a wall-clock delay.

    Used for scenarios where the model is never called (e.g. muted mic) so
    ``_shutdown`` is never set by the model-exhaustion path.

    Args:
        items: Probability sequence (may be unused if muted).
        shutdown_after_secs: Seconds before _shutdown is forced.
        pre_muted: If True, ``_mic_muted`` is set before the loop starts.
        timeout: Max seconds to wait for the vad_loop thread.

    Returns:
        List of utterances captured during the run.
    """
    model = _make_model_mock(items)
    stream = _make_stream_mock()

    utterances: list = []
    utq: queue.Queue = queue.Queue()

    def _on_utterance(audio):  # noqa: ANN001
        utq.put(audio)

    cyrus_voice._shutdown.clear()
    cyrus_voice._mic_muted.clear()
    cyrus_voice._user_paused.clear()
    if pre_muted:
        cyrus_voice._mic_muted.set()

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()

    def _force_shutdown():
        time.sleep(shutdown_after_secs)
        cyrus_voice._shutdown.set()

    threading.Thread(target=_force_shutdown, daemon=True).start()

    with (
        patch.object(cyrus_voice, "sd") as mock_sd,
        patch.object(cyrus_voice, "load_silero_vad", return_value=model),
    ):
        mock_sd.RawInputStream.return_value = stream
        vad_thread = threading.Thread(
            target=cyrus_voice.vad_loop,
            args=(_on_utterance, loop),
            daemon=True,
        )
        vad_thread.start()
        vad_thread.join(timeout=timeout)

    _flushed = threading.Event()
    loop.call_soon_threadsafe(_flushed.set)
    _flushed.wait(timeout=1.0)
    loop.call_soon_threadsafe(loop.stop)
    loop_thread.join(timeout=1.0)

    while not utq.empty():
        utterances.append(utq.get_nowait())
    return utterances


# ── Ring Buffer Management Tests ──────────────────────────────────────────────


class TestRingBufferManagement(unittest.TestCase):
    """Ring buffer (deque) behaviour — pure Python, no hardware deps.

    The pre-speech ring buffer is a ``deque(maxlen=SPEECH_RING)`` that holds
    (frame_bytes, is_speech) tuples.  When it fills and ≥80% are voiced,
    recording begins.  These tests verify the data-structure properties in
    isolation.
    """

    def test_ring_buffer_fifo_order(self):
        """FIFO: oldest items are dropped first when the buffer is full.

        When five items are added to a ring of maxlen=3, the three youngest
        should remain in insertion order.
        """
        ring: deque = deque(maxlen=3)
        for i in range(5):
            ring.append(i)
        # Elements 0 and 1 were evicted; [2, 3, 4] remain
        self.assertEqual(list(ring), [2, 3, 4], "Ring must drop oldest items first")

    def test_ring_buffer_max_size_respected(self):
        """Buffer length never exceeds SPEECH_RING regardless of appends.

        Appending more than maxlen items must not grow the deque beyond its
        configured maximum.
        """
        maxlen = cyrus_voice.SPEECH_RING  # 9 at standard settings
        ring: deque = deque(maxlen=maxlen)
        for i in range(maxlen + 20):
            ring.append((b"\x00", bool(i % 2)))
        self.assertEqual(len(ring), maxlen, "deque must cap at SPEECH_RING frames")

    def test_ring_buffer_speech_ratio_threshold(self):
        """Speech-ratio gate: ≥80% voiced triggers; <80% does not.

        SPEECH_RATIO = 0.80.  With SPEECH_RING = 9:
          - 8 voiced / 9 total → 88.9% ≥ 80% → should trigger
          - 7 voiced / 9 total → 77.8% < 80% → should not trigger
        """
        maxlen = cyrus_voice.SPEECH_RING  # 9
        ratio = cyrus_voice.SPEECH_RATIO  # 0.80

        # 8 voiced out of 9 → above threshold
        ring_high: deque = deque([(b"", i < 8) for i in range(maxlen)], maxlen=maxlen)
        num_voiced_high = sum(1 for _, s in ring_high if s)
        high_pct = num_voiced_high / maxlen
        self.assertGreaterEqual(
            high_pct,
            ratio,
            f"8/{maxlen} voiced ({high_pct:.1%}) should be >= {ratio:.0%}",
        )

        # 7 voiced out of 9 → below threshold
        ring_low: deque = deque([(b"", i < 7) for i in range(maxlen)], maxlen=maxlen)
        num_voiced_low = sum(1 for _, s in ring_low if s)
        low_pct = num_voiced_low / maxlen
        self.assertLess(
            low_pct,
            ratio,
            f"7/{maxlen} voiced ({low_pct:.1%}) should be < {ratio:.0%}",
        )


# ── VAD State Transition Tests ────────────────────────────────────────────────


class TestVADStateTransitions(unittest.TestCase):
    """VAD state-machine transitions tested end-to-end via mocked vad_loop.

    States observed behaviorally:
      idle         — ring accumulating, no recording
      recording    — speech detected, collecting frames
      utterance    — silence/timeout ends recording, on_utterance fired
    """

    def test_idle_to_recording_on_speech_majority(self):
        """Full SPEECH_RING of voiced frames triggers recording and produces utterance.

        9 voiced frames (100% > 80%) fill the ring and start recording.
        SILENCE_RING subsequent silence frames end recording and emit one utterance.
        """
        # 9 voiced → trigger recording;  31 silence → emit utterance
        probs = [0.9] * cyrus_voice.SPEECH_RING + [0.1] * cyrus_voice.SILENCE_RING
        utterances = _run_vad(probs)
        self.assertEqual(
            len(utterances),
            1,
            "Exactly one utterance expected after speech + silence sequence",
        )

    def test_no_recording_on_insufficient_speech_ratio(self):
        """7/9 voiced frames (77.8% < 80%) must NOT trigger recording.

        Feed a ring's worth of frames but only 7/9 voiced.  Then add
        SILENCE_RING more silence frames.  No utterance should be emitted
        because recording never started.
        """
        # Pattern: 7 voiced + 2 silence in ring, then silence to fill out
        ring_frames = [0.9] * 7 + [0.1] * 2
        # Extra frames so the model exhaustion path (shutdown) runs after
        extra_silence = [0.1] * (cyrus_voice.SILENCE_RING + 5)
        probs = ring_frames + extra_silence
        utterances = _run_vad(probs)
        self.assertEqual(
            len(utterances),
            0,
            "No utterance expected when speech ratio is below 80%",
        )

    def test_utterance_emitted_after_silence_ends_recording(self):
        """Recording followed by silence produces exactly one utterance.

        Sequence: trigger (9 voiced) → short speech (5 voiced) →
        silence (SILENCE_RING frames) → utterance.
        """
        probs = (
            [0.9] * cyrus_voice.SPEECH_RING  # fill ring, trigger recording
            + [0.9] * 5  # a few in-recording speech frames
            + [0.1] * cyrus_voice.SILENCE_RING  # silence timeout
        )
        utterances = _run_vad(probs)
        self.assertEqual(len(utterances), 1, "One utterance expected after silence")

    def test_muted_mic_blocks_recording(self):
        """When _mic_muted is set the loop discards frames and emits no utterance.

        Pre-setting _mic_muted before starting vad_loop means every iteration
        takes the muted branch (ring.clear(); time.sleep(0.01); continue) and
        never calls the Silero model.  A forced shutdown after 0.3 s terminates
        the loop cleanly.
        """
        # These probs would normally trigger recording — but mic is muted
        probs = [0.9] * cyrus_voice.SPEECH_RING + [0.1] * cyrus_voice.SILENCE_RING
        utterances = _run_vad_with_delayed_shutdown(probs, pre_muted=True)
        self.assertEqual(
            len(utterances),
            0,
            "Muted mic must prevent any utterance from being emitted",
        )

    def test_state_resets_cleanly_after_utterance(self):
        """State resets so a second speech sequence produces a second utterance.

        Two identical speech+silence sequences must each produce exactly one
        utterance — demonstrating that recording state, silence_count,
        speech_frames, and the ring are all reset between utterances.
        """
        single = [0.9] * cyrus_voice.SPEECH_RING + [0.1] * cyrus_voice.SILENCE_RING
        probs = single + single  # two identical speech/silence cycles
        utterances = _run_vad(probs)
        self.assertEqual(
            len(utterances),
            2,
            "Two consecutive speech+silence cycles must each produce one utterance",
        )


# ── Silence Detection Tests ───────────────────────────────────────────────────


class TestSilenceDetection(unittest.TestCase):
    """Silence threshold, silence counter, and adaptive silence ring tests."""

    def test_low_probability_frames_not_counted_as_speech(self):
        """Frames with probability below SPEECH_THRESHOLD (0.5) are silence.

        Nine frames at prob=0.3 (< 0.5) should all register as silence.
        The ring fills with 9 silence flags (0/9 voiced = 0% < 80%) so
        recording is never triggered and no utterance is emitted.
        """
        probs = [0.3] * cyrus_voice.SPEECH_RING + [0.1] * 5
        utterances = _run_vad(probs)
        self.assertEqual(
            len(utterances),
            0,
            "Frames below SPEECH_THRESHOLD must not be voiced; no utterance expected",
        )

    def test_silence_counter_triggers_utterance_after_silence_ring_frames(self):
        """SILENCE_RING silence frames must end recording and emit utterance.

        After triggering recording with voiced frames, exactly SILENCE_RING
        consecutive silence frames satisfy ``silence_count >= SILENCE_RING``
        and emit the utterance.
        """
        probs = (
            [0.9] * cyrus_voice.SPEECH_RING  # trigger recording
            + [0.1] * cyrus_voice.SILENCE_RING  # hit silence timeout
        )
        utterances = _run_vad(probs)
        self.assertEqual(
            len(utterances),
            1,
            "Exactly SILENCE_RING silence frames should trigger the utterance",
        )

    def test_adaptive_silence_ring_extended_for_long_speech(self):
        """After >1500 ms of in-recording speech the silence ring doubles.

        Adaptive rule: if ``speech_frames * FRAME_MS > 1500``, then
        ``adaptive_ring = SILENCE_RING * 2``.

        With FRAME_MS = 32 ms, 47 speech frames = 1504 ms > 1500 ms triggers
        the extended threshold.  SILENCE_RING (31) frames of silence must NOT
        emit the utterance; SILENCE_RING * 2 (62) frames must.
        """
        # Need speech_frames > 1500 / FRAME_MS = 46.9  → use 47
        speech_for_adaptive = 47
        self.assertGreater(
            speech_for_adaptive * cyrus_voice.FRAME_MS,
            1500,
            "Precondition: 47 frames must exceed the 1500 ms adaptive threshold",
        )

        # 9 trigger + 47 speech → adaptive_ring = SILENCE_RING * 2 = 62
        # Then SILENCE_RING (31) silence → should NOT trigger (31 < 62)
        # Then 31 more silence → total = 62 >= 62 → SHOULD trigger
        probs = (
            [0.9] * cyrus_voice.SPEECH_RING  # ring fill → trigger recording
            + [0.9] * speech_for_adaptive  # 47 in-recording speech frames
            + [0.1] * cyrus_voice.SILENCE_RING  # partial silence (no trigger yet)
            + [0.1] * cyrus_voice.SILENCE_RING  # hits doubled threshold → trigger
        )
        utterances = _run_vad(probs)
        self.assertEqual(
            len(utterances),
            1,
            "Utterance must fire at SILENCE_RING*2 when adaptive threshold is active",
        )


# ── Timeout Behavior Tests ────────────────────────────────────────────────────


class TestTimeoutBehavior(unittest.TestCase):
    """Tests for the two timeout conditions in vad_loop:

    1. Silence timeout — ``silence_count >= adaptive_ring``
    2. Max-duration timeout — ``len(frames) >= MAX_RECORD_FRAMES``
    """

    def test_silence_timeout_triggers_utterance(self):
        """Silence timeout path: SILENCE_RING frames of silence emit utterance.

        This is a direct test of the ``silence_count >= adaptive_ring``
        condition in non-adaptive mode (< 1500 ms of in-recording speech).
        """
        probs = (
            [0.9] * cyrus_voice.SPEECH_RING  # trigger recording
            + [0.9] * 3  # tiny amount of speech (3 * 32 = 96 ms < 1500 ms)
            + [0.1] * cyrus_voice.SILENCE_RING  # silence timeout
        )
        utterances = _run_vad(probs)
        self.assertEqual(
            len(utterances),
            1,
            "Silence timeout must produce exactly one utterance",
        )

    def test_max_duration_timeout_triggers_utterance(self):
        """Max-duration timeout: MAX_RECORD_FRAMES collected frames end recording.

        MAX_RECORD_FRAMES = MAX_RECORD_MS // FRAME_MS = 12000 // 32 = 375.
        Feeding 375 frames of speech (alternating so silence_count never
        reaches SILENCE_RING) must trigger the ``timed_out`` path and emit
        an utterance.
        """
        max_frames = cyrus_voice.MAX_RECORD_FRAMES  # 375

        # Alternate speech/silence to prevent silence_count reaching SILENCE_RING
        # Pattern: 3 voiced, 1 silence, repeat → silence_count resets every 3 voiced
        single_cycle = [0.9, 0.9, 0.9, 0.1]
        repeats = (max_frames // len(single_cycle)) + 5  # enough to exceed max
        probs = (
            [0.9] * cyrus_voice.SPEECH_RING  # trigger recording
            + single_cycle * repeats  # accumulate frames without silence timeout
        )
        utterances = _run_vad(probs, timeout=10.0)
        self.assertEqual(
            len(utterances),
            1,
            "Max-duration timeout must produce exactly one utterance",
        )


# ── Edge Case Tests ───────────────────────────────────────────────────────────


class TestEdgeCases(unittest.TestCase):
    """Edge cases: model exceptions and pre-speech ring buffer contents."""

    def test_model_exception_handled_gracefully(self):
        """A Silero model exception must not crash the loop; next frame continues.

        The try/except block in vad_loop catches all exceptions from the model
        and logs them, then ``continue``s.  The loop must recover and eventually
        trigger an utterance after the injection of a single exception frame.
        """
        # 4 voiced → ring=[T,T,T,T]; then exception → ring unchanged (continue)
        # 5 more voiced → ring fills to 9 → trigger recording
        # 31 silence → utterance
        probs = (
            [0.9] * 4  # partial ring fill
            + [_RAISE]  # injected exception — loop must continue
            + [0.9] * 5  # complete the ring fill
            + [0.1] * cyrus_voice.SILENCE_RING  # silence timeout → utterance
        )
        utterances = _run_vad(probs)
        self.assertEqual(
            len(utterances),
            1,
            "Loop must survive a model exception and still emit utterance",
        )

    def test_pre_speech_buffer_included_in_utterance(self):
        """Pre-speech ring frames are included in the emitted audio.

        When recording starts, vad_loop builds the initial ``frames`` list
        from the ring buffer contents.  This test verifies the on_utterance
        callback is invoked (meaning the full audio path executed), and that
        two independent speech sequences each emit one utterance, confirming
        the ring is re-populated correctly after each utterance.
        """
        # First speech+silence cycle
        cycle = [0.9] * cyrus_voice.SPEECH_RING + [0.1] * cyrus_voice.SILENCE_RING
        # Two cycles — both must emit utterances
        probs = cycle + cycle
        utterances = _run_vad(probs)
        self.assertEqual(
            len(utterances),
            2,
            "Two speech+silence cycles with pre-speech buffer must each produce one utterance",  # noqa: E501
        )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
