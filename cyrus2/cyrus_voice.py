"""
cyrus_voice.py — Service 1: Voice I/O

Loads audio models once (Whisper, Kokoro TTS, Silero VAD) and keeps them warm.
Connects to cyrus_brain.py over TCP and handles all audio I/O.

Usage:
    python cyrus_voice.py [--host HOST] [--port PORT]

Protocol (line-delimited JSON):
  Voice → Brain:  {"type": "utterance",    "text": "...", "during_tts": false}
                  {"type": "tts_start"}
                  {"type": "tts_end"}
  Brain → Voice:  {"type": "speak",         "text": "...", "project": "..."}
                  {"type": "chime"}
                  {"type": "listen_chime"}
                  {"type": "stop_speech"}
                  {"type": "pause"}
                  {"type": "whisper_prompt", "text": "..."}
                  {"type": "status",         "msg":  "..."}
"""

import argparse
import asyncio
import json
import logging
import os
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import keyboard
import numpy as np
import pygame
import sounddevice as sd
import torch
from cyrus2.cyrus_config import (
    AUTH_TOKEN,
    BRAIN_PORT,
    SILENCE_WINDOW,
    SPEECH_THRESHOLD,
    TTS_TIMEOUT,
    WHISPER_MODEL,
)
from cyrus2.cyrus_log import setup_logging
from faster_whisper import WhisperModel
from silero_vad import load_silero_vad

log = logging.getLogger("cyrus.voice")

# ── GPU detection ──────────────────────────────────────────────────────────────

_CUDA = torch.cuda.is_available()
_GPU_NAME = torch.cuda.get_device_name(0) if _CUDA else "none"

# ── Configuration ──────────────────────────────────────────────────────────────
# Port, VAD, and Whisper model constants are imported from cyrus_config so they
# can be overridden via CYRUS_BRAIN_PORT, CYRUS_SPEECH_THRESHOLD,
# CYRUS_SILENCE_WINDOW, CYRUS_TTS_TIMEOUT, and CYRUS_WHISPER_MODEL env vars.
# BRAIN_PORT, SPEECH_THRESHOLD, SILENCE_WINDOW, TTS_TIMEOUT, WHISPER_MODEL
# are all imported above.

WHISPER_DEVICE = "cuda" if _CUDA else "cpu"
WHISPER_COMPUTE_TYPE = "float16" if _CUDA else "int8"
SAMPLE_RATE = 16000
CHANNELS = 1

KOKORO_MODEL = os.path.join(os.path.dirname(__file__), "kokoro-v1.0.onnx")
KOKORO_VOICES = os.path.join(os.path.dirname(__file__), "voices-v1.0.bin")
TTS_VOICE = "af_heart"
TTS_SPEED = 1.0

BRAIN_HOST = "localhost"
# BRAIN_PORT imported from cyrus_config

KEY_PAUSE = "f9"
KEY_STOP = "f7"
KEY_READ_CLIP = "f8"

# SPEECH_THRESHOLD imported from cyrus_config
FRAME_MS = 32
FRAME_SIZE = 512
SPEECH_WINDOW_MS = 300
SILENCE_WINDOW_MS = SILENCE_WINDOW  # SILENCE_WINDOW imported from cyrus_config
MAX_RECORD_MS = 12000

SPEECH_RING = SPEECH_WINDOW_MS // FRAME_MS
SILENCE_RING = SILENCE_WINDOW_MS // FRAME_MS
MAX_RECORD_FRAMES = MAX_RECORD_MS // FRAME_MS
SPEECH_RATIO = 0.80

# ── Shared state ───────────────────────────────────────────────────────────────

_mic_muted = threading.Event()
_user_paused = threading.Event()
_stop_speech = threading.Event()
_tts_active = threading.Event()
_tts_pending = threading.Event()
_shutdown = threading.Event()

_kokoro = None
_whisper_executor: ThreadPoolExecutor = None
_whisper_prompt: str = "Cyrus,"

_tts_queue: asyncio.Queue = None  # (project, text) pairs from brain
_brain_writer: asyncio.StreamWriter = None  # set once connected

# ── Hallucination / filler filters ────────────────────────────────────────────

_HALLUCINATIONS = re.compile(
    r"thank(s| you) for watching"
    r"|see you (in the next|next time|again)"
    r"|don'?t forget to (like|subscribe)"
    r"|like and subscribe"
    r"|please subscribe"
    r"|subtitles by"
    r"|transcribed by",
    re.IGNORECASE,
)
_MIN_RMS = 0.004
_FILLER_RE = re.compile(
    r"^(?:uh+|um+|er+|so|okay|ok|right|hey|please|can you|could you|would you)\s+",
    re.IGNORECASE,
)


def _strip_fillers(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _FILLER_RE.sub("", text).strip()
    return text


# ── Chimes ─────────────────────────────────────────────────────────────────────


def play_chime():
    try:
        sr, dur = 44100, 0.18
        t = np.linspace(0, dur, int(sr * dur), False)
        wave = (np.sin(2 * np.pi * 880 * t) * 32767 * 0.25).astype(np.int16)
        pygame.sndarray.make_sound(np.column_stack([wave, wave])).play()
    except Exception:
        log.debug("Chime playback failed", exc_info=True)


def play_listen_chime():
    try:
        sr = 44100
        gap = np.zeros(int(sr * 0.04), dtype=np.int16)

        def tone(freq, dur, vol=0.22):
            t = np.linspace(0, dur, int(sr * dur), False)
            return (np.sin(2 * np.pi * freq * t) * 32767 * vol).astype(np.int16)

        wave = np.concatenate([tone(500, 0.09), gap, tone(800, 0.09)])
        pygame.sndarray.make_sound(np.column_stack([wave, wave])).play()
    except Exception:
        log.debug("Listen chime playback failed", exc_info=True)


# ── Send to brain ──────────────────────────────────────────────────────────────


async def _send(msg: dict) -> None:
    if _brain_writer is None:
        return
    try:
        _brain_writer.write((json.dumps(msg) + "\n").encode())
        await _brain_writer.drain()
    except Exception:
        log.debug("Failed to send to brain", exc_info=True)


# ── TTS pipeline ───────────────────────────────────────────────────────────────


async def drain_tts_queue() -> None:
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except Exception:
            log.debug("Error draining TTS queue", exc_info=True)
            break


async def speak(text: str) -> None:
    _stop_speech.clear()
    _tts_active.set()
    _mic_muted.set()
    await _send({"type": "tts_start"})
    try:
        await asyncio.wait_for(_speak_save(text), timeout=TTS_TIMEOUT)
    except asyncio.TimeoutError:
        log.warning("TTS timed out")
        _stop_speech.set()
    finally:
        _tts_active.clear()
        await asyncio.sleep(0.25)
        _mic_muted.clear()
        await _send({"type": "tts_end"})


async def _speak_save(text: str) -> None:
    if _kokoro is not None:
        await _speak_kokoro(text)
    else:
        await _speak_edge(text)


async def _speak_kokoro(text: str) -> None:
    log.debug("TTS generating %s chars...", len(text))
    samples, sr = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: _kokoro.create(text, voice=TTS_VOICE, speed=TTS_SPEED, lang="en-us"),
    )
    log.debug("TTS %s samples at %sHz — playing", len(samples), sr)

    def _play():
        chunk = 1024
        with sd.OutputStream(samplerate=sr, channels=1, dtype="float32") as stream:
            for i in range(0, len(samples), chunk):
                if _stop_speech.is_set():
                    break
                stream.write(samples[i : i + chunk].reshape(-1, 1))

    await asyncio.get_event_loop().run_in_executor(None, _play)


async def _speak_edge(text: str) -> None:
    import subprocess
    import tempfile

    import edge_tts

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name
    try:
        await edge_tts.Communicate(
            text, "en-US-BrianNeural", rate="-5%", pitch="-5Hz"
        ).save(tmp_path)
        if not os.path.getsize(tmp_path):
            return
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "quiet",
                    "-i",
                    tmp_path,
                    "-f",
                    "s16le",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-",
                ],
                capture_output=True,
            ),
        )
        pcm = result.stdout
        if not pcm:
            return
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        def _play():
            chunk = 1024
            with sd.OutputStream(
                samplerate=24000, channels=1, dtype="float32"
            ) as stream:
                for i in range(0, len(audio), chunk):
                    if _stop_speech.is_set():
                        break
                    stream.write(audio[i : i + chunk])

        await asyncio.get_event_loop().run_in_executor(None, _play)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            log.debug("Failed to delete temp file", exc_info=True)


async def tts_worker() -> None:
    """Consumes speak requests from brain and plays them serially."""
    while True:
        project, text = await _tts_queue.get()
        _tts_pending.clear()
        try:
            log.debug("TTS worker speak: %r", text[:50])
            await speak(text)
            log.debug("TTS worker done")
        except Exception as e:
            log.error("TTS worker error: %s", e, exc_info=True)


# ── STT ────────────────────────────────────────────────────────────────────────


def transcribe(whisper_model: WhisperModel, audio: np.ndarray) -> str:
    rms = float(np.sqrt(np.mean(audio**2)))
    if rms < _MIN_RMS:
        return ""
    segments, _ = whisper_model.transcribe(
        audio,
        language="en",
        beam_size=1,
        best_of=1,
        initial_prompt=_whisper_prompt,
    )
    text = " ".join(s.text for s in segments if s.no_speech_prob < 0.6).strip()
    if _HALLUCINATIONS.search(text):
        log.debug("Hallucination filtered: %s", text[:60])
        return ""
    return text


# ── VAD loop ───────────────────────────────────────────────────────────────────


def vad_loop(on_utterance, loop: asyncio.AbstractEventLoop):
    model = load_silero_vad()
    ring: deque = deque(maxlen=SPEECH_RING)
    recording = False
    frames: list = []
    silence_count = 0
    speech_frames = 0

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=FRAME_SIZE
    ) as stream:
        while not _shutdown.is_set():
            if _mic_muted.is_set() or _user_paused.is_set():
                stream.read(FRAME_SIZE)
                ring.clear()
                if recording:
                    frames.clear()
                    recording = False
                    silence_count = 0
                time.sleep(0.01)
                continue

            raw, _ = stream.read(FRAME_SIZE)
            frame_bytes = bytes(raw)
            try:
                chunk = (
                    np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32)
                    / 32768.0
                )
                with torch.no_grad():
                    prob = model(torch.from_numpy(chunk), SAMPLE_RATE).item()
                is_speech = prob > SPEECH_THRESHOLD
            except Exception:
                log.debug("VAD frame error", exc_info=True)
                continue

            if not recording:
                ring.append((frame_bytes, is_speech))
                num_voiced = sum(1 for _, s in ring if s)
                if (
                    len(ring) == ring.maxlen
                    and num_voiced / ring.maxlen >= SPEECH_RATIO
                ):
                    recording = True
                    frames = [fb for fb, _ in ring]
                    silence_count = 0
                    speech_frames = 0
                    ring.clear()
                    log.debug("Listening...")
            else:
                frames.append(frame_bytes)
                if is_speech:
                    silence_count = 0
                    speech_frames += 1
                else:
                    silence_count += 1

                adaptive_ring = (
                    SILENCE_RING * 2
                    if speech_frames * FRAME_MS > 1500
                    else SILENCE_RING
                )
                timed_out = len(frames) >= MAX_RECORD_FRAMES
                if silence_count >= adaptive_ring or timed_out:
                    if timed_out:
                        log.debug("Max duration reached")
                    raw_audio = b"".join(frames)
                    audio = (
                        np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
                        / 32768.0
                    )
                    recording = False
                    frames = []
                    silence_count = 0
                    speech_frames = 0
                    ring.clear()
                    model.reset_states()
                    loop.call_soon_threadsafe(on_utterance, audio)


# ── Brain connection ───────────────────────────────────────────────────────────


async def brain_reader(reader: asyncio.StreamReader) -> None:
    """Read commands from brain and dispatch to local audio state."""
    global _whisper_prompt
    while True:
        try:
            line = await reader.readline()
            if not line:
                break
            msg = json.loads(line.decode().strip())
            mtype = msg.get("type", "")

            if mtype == "speak":
                text = msg.get("text", "")
                project = msg.get("project", "")
                if text:
                    _tts_pending.set()
                    await _tts_queue.put((project, text))

            elif mtype == "chime":
                play_chime()

            elif mtype == "listen_chime":
                play_listen_chime()

            elif mtype == "stop_speech":
                _stop_speech.set()
                await drain_tts_queue()

            elif mtype == "pause":
                if _user_paused.is_set():
                    _user_paused.clear()
                    log.info("Resumed")
                else:
                    _user_paused.set()
                    log.info("Paused")

            elif mtype == "whisper_prompt":
                _whisper_prompt = msg.get("text", _whisper_prompt)

            elif mtype == "status":
                log.info("%s", msg.get("msg", ""))

        except json.JSONDecodeError:
            log.debug("Invalid JSON from brain", exc_info=True)
        except Exception as e:
            log.error("Brain reader error: %s", e, exc_info=True)
            break


async def voice_loop(whisper_model, reader, writer, loop) -> None:
    """Transcribe utterances and stream to brain. Receive and play TTS."""
    global _brain_writer
    _brain_writer = writer

    # ── Authentication handshake ───────────────────────────────────────────────
    # Send the shared-secret token as the first message so the brain can
    # validate this connection before accepting any utterances.
    auth_msg = json.dumps({"type": "auth", "token": AUTH_TOKEN}) + "\n"
    writer.write(auth_msg.encode())
    await writer.drain()

    disconnected = asyncio.Event()

    async def _reader_task():
        await brain_reader(reader)
        disconnected.set()

    utterance_queue: asyncio.Queue = asyncio.Queue()
    threading.Thread(
        target=vad_loop,
        args=(utterance_queue.put_nowait, loop),
        daemon=True,
    ).start()

    # Discard audio captured during model-load TTS echo window
    await asyncio.sleep(0.5)
    while not utterance_queue.empty():
        try:
            utterance_queue.get_nowait()
        except Exception:
            log.debug("Queue drain error", exc_info=True)

    asyncio.create_task(_reader_task())
    asyncio.create_task(tts_worker())

    log.info("Ready — streaming utterances to brain.")

    while not disconnected.is_set():
        try:
            audio = await asyncio.wait_for(utterance_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        # Drop stale utterances — keep only most recent
        while not utterance_queue.empty():
            try:
                audio = utterance_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        log.debug("Transcribing...")
        text = await loop.run_in_executor(
            _whisper_executor, transcribe, whisper_model, audio
        )
        if not text:
            log.debug("Nothing heard")
            continue

        during_tts = _tts_active.is_set() or _tts_pending.is_set()
        log.debug("Transcribed%s: %s", " (during TTS)" if during_tts else "", text)
        await _send({"type": "utterance", "text": text, "during_tts": during_tts})

    log.warning("Brain disconnected — reconnecting...")


# ── Main ───────────────────────────────────────────────────────────────────────


async def main() -> None:
    global _tts_queue, _whisper_executor, _kokoro

    setup_logging("cyrus")

    parser = argparse.ArgumentParser(description="Cyrus Voice — audio I/O service")
    parser.add_argument("--host", default=BRAIN_HOST, help="Brain host")
    parser.add_argument("--port", type=int, default=BRAIN_PORT, help="Brain port")
    args = parser.parse_args()

    if _CUDA:
        log.info("GPU: %s", _GPU_NAME)
    else:
        log.info("No CUDA GPU — Whisper on CPU")
    log.info("Loading Whisper %s on %s...", WHISPER_MODEL, WHISPER_DEVICE)
    whisper_model = WhisperModel(
        WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE
    )

    if os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_VOICES):
        try:
            import onnxruntime as _ort
            from kokoro_onnx import Kokoro as _KokoroClass

            _ort.set_default_logger_severity(3)
            _providers = []
            if _CUDA:
                _providers.append(
                    ("CUDAExecutionProvider", {"cudnn_conv_algo_search": "DEFAULT"})
                )
            _providers.append("CPUExecutionProvider")
            _session = _ort.InferenceSession(KOKORO_MODEL, providers=_providers)
            _kokoro = _KokoroClass.from_session(_session, KOKORO_VOICES)
            _tts_dev = (
                "GPU" if "CUDAExecutionProvider" in _session.get_providers() else "CPU"
            )
            log.info("Kokoro TTS loaded (%s) — voice: %s", _tts_dev, TTS_VOICE)
        except Exception as e:
            log.warning("Kokoro load failed (%s) — using Edge TTS", e, exc_info=True)
    else:
        log.warning("Kokoro model not found — using Edge TTS")

    pygame.mixer.init()
    _whisper_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")
    _tts_queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    # ── Hotkeys ───────────────────────────────────────────────────────────────
    def _toggle_pause():
        if _user_paused.is_set():
            _user_paused.clear()
            log.info("Resumed (F9)")
        else:
            _user_paused.set()
            log.info("Paused (F9)")

    def _stop_and_clear():
        _stop_speech.set()
        asyncio.run_coroutine_threadsafe(drain_tts_queue(), loop)

    def _read_clipboard():
        try:
            import pyperclip

            text = pyperclip.paste().strip()
            if text:
                _tts_pending.set()
                asyncio.run_coroutine_threadsafe(_tts_queue.put(("", text)), loop)
        except Exception:
            log.debug("Clipboard read failed", exc_info=True)

    keyboard.add_hotkey(KEY_PAUSE, _toggle_pause)
    keyboard.add_hotkey(KEY_STOP, _stop_and_clear)
    keyboard.add_hotkey(KEY_READ_CLIP, _read_clipboard)
    log.info("F9 pause | F7 stop+clear | F8 clipboard | Ctrl+C exit")

    # ── Connect loop — reconnects automatically if brain restarts ─────────────
    log.info("Connecting to brain at %s:%s...", args.host, args.port)
    while not _shutdown.is_set():
        try:
            reader, writer = await asyncio.open_connection(args.host, args.port)
            log.info("Connected to brain.")
            try:
                await voice_loop(whisper_model, reader, writer, loop)
            except Exception as e:
                log.warning("Disconnected: %s", e, exc_info=True)
            finally:
                global _brain_writer
                _brain_writer = None
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    log.debug("Writer close error", exc_info=True)
        except Exception as e:
            log.warning(
                "Cannot connect to brain (%s) — retrying in 3s...", e, exc_info=True
            )
        await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Cyrus Voice signing off.")
        _shutdown.set()
        _stop_speech.set()
        _mic_muted.set()
        try:
            pygame.mixer.stop()
            pygame.mixer.quit()
        except Exception:
            log.debug("Pygame cleanup error", exc_info=True)
        try:
            sd.stop()
        except Exception:
            log.debug("Sound device cleanup error", exc_info=True)
        if _whisper_executor:
            _whisper_executor.shutdown(wait=False, cancel_futures=True)
        try:
            keyboard.unhook_all()
        except Exception:
            log.debug("Keyboard cleanup error", exc_info=True)
        os._exit(0)
