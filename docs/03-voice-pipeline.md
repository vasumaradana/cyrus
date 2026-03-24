# 03 — Voice Pipeline

How speech goes from your microphone to text, and how text becomes speech.

## Speech-to-Text Flow

```mermaid
flowchart TD
    MIC["Microphone — 16kHz mono"] --> FRAMES["Split into 32ms frames — 512 samples"]
    FRAMES --> MUTED{Mic muted or<br/>user paused?}
    MUTED -->|Yes| DISCARD_FRAME[Discard frame, clear ring buffer]
    MUTED -->|No| VAD["Silero VAD — speech probability"]
    VAD --> THRESHOLD{prob > 0.5?}
    THRESHOLD -->|No speech| RING["Add to ring buffer — 300ms / ~10 frames"]
    RING --> FULL{Ring full and<br/>80%+ speech?}
    FULL -->|No| FRAMES
    FULL -->|Yes| RECORD["Start recording"]
    THRESHOLD -->|Speech| RECORDING{Currently<br/>recording?}
    RECORDING -->|No| RING
    RECORDING -->|Yes| APPEND[Append frame to buffer]
    RECORD --> APPEND
    APPEND --> SILENCE{Silence for<br/>1s or 2.5s?}
    SILENCE -->|No| MAXCHECK{Hit 12s max?}
    MAXCHECK -->|No| FRAMES
    MAXCHECK -->|Yes| STOP[Stop recording]
    SILENCE -->|Yes| STOP
    STOP --> SEND[Send audio to transcription]
    SEND --> RMS{RMS > 0.004?}
    RMS -->|No| DROP[Discard — too quiet]
    RMS -->|Yes| WHISPER["Whisper medium.en — transcribe"]
    WHISPER --> HALLUC{Hallucination filter?}
    HALLUC -->|Yes| DROP2[Discard]
    HALLUC -->|No| FILLER[Strip filler words]
    FILLER --> TEXT["Transcribed text"]
```

### Key Concepts

**Ring buffer.** A fixed-size circular buffer (`deque(maxlen=SPEECH_RING)`) holds the last ~300ms of audio. When VAD detects sustained speech, the ring contents become the start of the recording. This captures the beginning of an utterance that triggered detection.

**Adaptive silence window.** Short commands get 1s silence window. If speech exceeds 1.5s of voiced frames, the silence window doubles to ~2.5s. This allows natural pauses in longer utterances.

**Whisper initial prompt.** Whisper's `initial_prompt` parameter is seeded with project names (e.g., "Cyrus, switch to web-app cyrus."). This biases recognition toward expected vocabulary.

**Hallucination filter.** Whisper sometimes hallucinates YouTube-style phrases on silence ("thanks for watching", "subscribe"). A regex filter catches and discards these.

**Filler stripping.** Leading filler words (uh, um, okay, so, hey, please, can you, etc.) are stripped iteratively before forwarding to Claude.

## VAD Configuration Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `SAMPLE_RATE` | 16000 | Hz, required by Silero VAD |
| `FRAME_SIZE` | 512 | Samples per frame (32ms at 16kHz) |
| `SPEECH_THRESHOLD` | 0.5 | VAD probability threshold |
| `SPEECH_WINDOW_MS` | 300 | Ring buffer duration |
| `SPEECH_RATIO` | 0.80 | Fraction of ring that must be speech to trigger |
| `SILENCE_WINDOW_MS` | 1000 | Silence duration to end recording |
| `MAX_RECORD_MS` | 12000 | Hard cap on recording duration |
| `_MIN_RMS` | 0.004 | ~-48 dBFS energy floor |

## Text-to-Speech Flow

```mermaid
flowchart TD
    INPUT["Text to speak"] --> CLEAN["clean_for_speech()"]
    CLEAN --> SANITIZE["_sanitize_for_speech() — fix Unicode"]
    SANITIZE --> TRUNCATE["Truncate to MAX_SPEECH_WORDS"]
    TRUNCATE --> ENGINE{Kokoro TTS<br/>available?}
    ENGINE -->|Yes| KOKORO["Kokoro ONNX — local inference<br/>af_heart voice, 1.0x speed"]
    ENGINE -->|No| EDGE["Edge TTS — cloud API<br/>en-US-BrianNeural, -5% rate"]
    KOKORO --> MUTE["Set _mic_muted, send tts_start"]
    EDGE --> FFMPEG["ffmpeg decode MP3 to PCM"]
    FFMPEG --> MUTE
    MUTE --> PLAY["Play via sounddevice OutputStream<br/>1024-sample chunks"]
    PLAY --> CHECK{_stop_speech<br/>set?}
    CHECK -->|Yes| ABORT[Stop playback]
    CHECK -->|No| DONE{All chunks<br/>played?}
    DONE -->|No| PLAY
    DONE -->|Yes| UNMUTE["Wait 250ms echo guard<br/>Clear _mic_muted, send tts_end"]
    ABORT --> UNMUTE
```

### Response Cleaning Pipeline (`clean_for_speech`)

Applied before TTS to make Claude's markdown-heavy responses speakable:

1. Replace code blocks with "See the chat for the code."
2. Strip inline backticks, headers, bold/italic markers
3. Convert markdown links to just their text
4. Replace bullets and numbered lists with periods
5. Collapse whitespace
6. Sanitize Unicode (em dash to comma, curly quotes to straight, etc.)
7. Truncate to word limit (30 in monolith, 50 in brain) with "See the chat for the full response."

### TTS Engines

| Engine | Latency | Requires | Quality |
|--------|---------|----------|---------|
| **Kokoro ONNX** | ~80-150ms on GPU | `kokoro-v1.0.onnx` + `voices-v1.0.bin` in project dir | High, natural |
| **Edge TTS** | ~500-2000ms | Internet + ffmpeg on PATH | Good, Microsoft voices |

Kokoro is preferred. If model files are missing or load fails, Edge TTS is used automatically.

## Echo Prevention

```mermaid
sequenceDiagram
    participant TTS as TTS Player
    participant Mic as Microphone
    participant VAD as VAD Loop

    TTS->>TTS: Set _mic_muted + _tts_active
    TTS->>TTS: Playing audio...
    Note over Mic,VAD: VAD loop reads frames<br/>but discards them (muted)

    alt Wake word during TTS
        Mic->>VAD: Audio captured
        VAD->>VAD: Not muted check fails, discarded
        Note over VAD: In split mode: voice sends utterance<br/>with during_tts=true, brain checks wake word
    end

    TTS->>TTS: Playback done
    TTS->>TTS: 250ms echo-decay guard
    TTS->>TTS: Clear _mic_muted
    Note over Mic,VAD: Normal listening resumes
```

In the **split architecture**, the voice service tags utterances with `during_tts: true`. The brain only processes these if they contain a wake word, then sends `stop_speech` to interrupt playback.

In the **monolith**, the main loop checks `_tts_active` / `_tts_pending` directly and only processes wake-word utterances during TTS.

## Hotkeys

| Key | Action | Implementation |
|-----|--------|----------------|
| **F9** | Toggle pause/resume listening | Sets/clears `_user_paused` threading.Event |
| **F7** | Stop current TTS + clear queue | Sets `_stop_speech`, drains TTS queue |
| **F8** | Read clipboard contents aloud | Reads pyperclip.paste(), enqueues for TTS |
