# 15 — Feature Recommendations for Cyrus 2.0

## High Impact

### 1. Extract `cyrus_common.py` (audit C3)
~2,000 lines duplicated between `main.py` and `cyrus_brain.py`. Single most impactful change — every subsequent fix becomes a one-file change.

### 2. Deprecate `main.py` monolith
Split architecture (brain + voice) is strictly better. After extracting common code, drop `main.py` and make split-mode the only mode.

### 3. Authentication on TCP ports
Brain listens on 0.0.0.0:8766/8767/8769 with zero auth. Add a shared secret token (from `.env`) validated on connection.

### 4. Replace `print()` with `logging` (audit M5)
Enables log levels, filtering, rotation. Critical for Docker (`docker logs`). See [16 — Logging System](./16-logging-system.md).

## Medium Impact

### 5. Configuration file
Ports, thresholds, wake words, MAX_SPEECH_WORDS, poll intervals are hardcoded constants scattered across files. A single `cyrus.toml` or env-var-driven config would make tuning painless.

### 6. Health check endpoint
Simple HTTP `/health` on the brain for Docker healthchecks, monitoring, and troubleshooting.

### 7. Companion extension bidirectional channel
Even without Docker, having the extension report focus events and handle permissions directly eliminates flaky UIA polling and works cross-platform natively. (See [13 — Docker Containerization](./13-docker-containerization.md))

### 8. Pin dependencies (audit H5)
`torch`, `faster-whisper`, `onnxruntime-gpu` break across versions. Lockfile prevents "it worked yesterday" issues.

## Nice to Have

### 9. Whisper model selection
Currently hardcoded to `medium.en`. Make configurable — smaller models (`tiny.en`, `base.en`) help on weaker hardware.

### 10. Session persistence
Brain restart loses all state (aliases, pending queues). Lightweight JSON state file could survive restarts.

### 11. Metrics/stats
Track utterance count, avg transcription time, TTS latency, permission response times.

### 12. `pyproject.toml` packaging
Modern Python packaging with optional dependency groups (`[voice]`, `[brain]`, `[dev]`).

## Recommended Priority Order
1 → 2 → 3 → 5 → 4 → 6 → 8 → 7 → rest

Items 1-2 are foundational — they cut the codebase nearly in half and make everything else easier.
