# 02 — Startup and Lifecycle

## Split Services Boot Sequence

```mermaid
sequenceDiagram
    participant User
    participant Brain as cyrus_brain.py
    participant Voice as cyrus_voice.py
    participant VSCode as VS Code
    participant CC as Claude Code

    Note over User: Terminal 1
    User->>Brain: python cyrus_brain.py [--host HOST] [--port PORT]
    Brain->>Brain: Parse CLI args
    Brain->>Brain: Init asyncio queues (_speak_queue, _utterance_queue)
    Brain->>Brain: SessionManager.start() — scan VS Code windows
    Brain->>Brain: Per window: spawn ChatWatcher + PermissionWatcher threads
    Brain->>Brain: Set _active_project to first detected window
    Brain->>Brain: Start _start_active_tracker thread (window focus polling)
    Brain->>Brain: Start _submit_worker thread (dedicated COM apartment)
    Brain->>Brain: Create _speak_worker + routing_loop async tasks
    Brain->>Brain: Open TCP server on :8766 (voice)
    Brain->>Brain: Open TCP server on :8767 (hooks)
    Brain->>Brain: Open WebSocket on :8769 (mobile)
    Brain-->>Brain: Waiting for voice connection...

    Note over User: Terminal 2
    User->>Voice: python cyrus_voice.py [--host HOST] [--port PORT]
    Voice->>Voice: Detect GPU (CUDA availability)
    Voice->>Voice: Load Whisper medium.en model
    Voice->>Voice: Load Kokoro TTS (or note Edge TTS fallback)
    Voice->>Voice: Init pygame mixer
    Voice->>Voice: Register hotkeys (F7, F8, F9)
    Voice->>Brain: TCP connect to :8766
    Brain->>Voice: whisper_prompt with project names
    Brain->>Voice: speak: "Cyrus is online. Session: project-name."
    Brain->>Voice: listen_chime
    Voice->>Voice: Start VAD loop thread
    Voice->>Voice: Start tts_worker + brain_reader async tasks
    Voice->>Voice: Discard stale audio from model-load echo window
    Note over Voice,Brain: System ready

    Note over CC: During usage
    CC->>Brain: Hook events on :8767 (Stop, PreToolUse, etc.)
```

## Monolith Boot Sequence (main.py)

```mermaid
sequenceDiagram
    participant User
    participant Main as main.py
    participant VSCode as VS Code

    User->>Main: python main.py [--remote URL]
    Main->>Main: Optional: connect to remote brain WebSocket
    Main->>Main: Load Whisper model
    Main->>Main: Load Kokoro TTS (or Edge TTS fallback)
    Main->>Main: Init pygame mixer
    Main->>Main: Create TTS queue, Whisper executor
    Main->>Main: Start VAD loop thread
    Main->>Main: SessionManager.start() — scan VS Code windows
    Main->>Main: Start active tracker thread
    Main->>Main: Register hotkeys (F7, F8, F9)
    Main->>Main: startup_sequence() — speak greeting
    Main->>Main: Discard startup echo audio
    Main->>Main: Enter main utterance loop
    Note over Main: System ready
```

## CLI Arguments

### cyrus_brain.py

| Arg | Default | Description |
|-----|---------|-------------|
| `--host` | `0.0.0.0` | Listen interface |
| `--port` | `8766` | Voice TCP port |

### cyrus_voice.py

| Arg | Default | Description |
|-----|---------|-------------|
| `--host` | `localhost` | Brain host to connect to |
| `--port` | `8766` | Brain port to connect to |

### main.py

| Arg | Default | Description |
|-----|---------|-------------|
| `--remote` | (none) | WebSocket URL of remote brain, e.g. `ws://192.168.1.10:8765` |

## Port Map

| Port | Protocol | From | To | Purpose |
|------|----------|------|----|---------|
| 8766 | TCP | Voice | Brain | Utterances + TTS commands (bidirectional) |
| 8767 | TCP | Hook script | Brain | Claude Code lifecycle events (one-shot) |
| 8768-8778 | TCP (Windows) | Brain | Companion Ext | Submit text to chat panel |
| Unix socket | AF_UNIX (Linux/Mac) | Brain | Companion Ext | Submit text to chat panel |
| 8769 | WebSocket | Mobile clients | Brain | Remote voice control |
| 8765 | WebSocket | main.py | cyrus_server.py | Optional remote brain routing |

## Shutdown

### Voice service (cyrus_voice.py)

On Ctrl+C or disconnect:
1. Set `_shutdown` event -- VAD loop exits
2. Set `_stop_speech` -- abort TTS playback
3. Set `_mic_muted` -- stop VAD processing
4. Stop pygame mixer
5. Stop sounddevice streams
6. Shutdown Whisper executor
7. Unhook all keyboard listeners
8. `os._exit(0)` -- force-exit to avoid PortAudio/SDL destructor crashes

### Brain service (cyrus_brain.py)

On Ctrl+C: asyncio servers close, daemon threads die automatically.

### Monolith (main.py)

Same shutdown as voice service, since it owns the audio hardware.

## Reconnection

```mermaid
flowchart TD
    DISC[Voice TCP disconnects] --> BRAIN[Brain detects closed reader]
    BRAIN --> CLEAR["Clear _voice_writer = None"]
    BRAIN --> WAIT[Brain continues running, preserves all state]

    DISC --> VOICE[Voice detects disconnected writer]
    VOICE --> SLEEP["Sleep 3 seconds"]
    SLEEP --> RETRY[Retry TCP connect]
    RETRY -->|success| SYNC["Brain re-sends whisper_prompt + greeting"]
    RETRY -->|fail| SLEEP
```

The brain can be restarted freely during development. The voice service stays warm (Whisper model loaded) and reconnects automatically.
