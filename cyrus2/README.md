# Cyrus 2.0 — Voice Layer for Claude Code

Voice assistant for Claude Code in VS Code. Speak naturally, Cyrus transcribes
and routes your words to Claude Code, then reads the response aloud.

## Quick Start (Split Mode — Recommended)

Run two services independently:

```bash
# Terminal 1 — Brain (dev machine with VS Code)
python cyrus_brain.py

# Terminal 2 — Voice (same machine or remote)
python cyrus_voice.py --host <brain-ip>
```

For local use, `--host` defaults to `localhost`.

## Project Structure

```
cyrus_brain.py          — Brain service (routing/UIA/hooks) — PRIMARY ENTRY POINT
cyrus_voice.py          — Voice service (mic/VAD/Whisper/TTS)
cyrus_common.py         — Shared types, constants, session management
cyrus_hook.py           — Claude Code hook script (all 4 events)
cyrus_server.py         — HTTP server for hook delivery
main.py                 — DEPRECATED monolith wrapper (delegates to cyrus_brain.py)
```

## Deprecated: Monolith Mode

> **⚠️ `main.py` is deprecated and will be removed in Cyrus 3.0.**

The original `main.py` combined voice I/O and brain logic in a single process.
It now delegates to `cyrus_brain.py` and prints a deprecation warning on startup.

**Use split mode instead** (documented in Quick Start above). If you previously
ran `python main.py`, switch to:

```bash
python cyrus_brain.py &
python cyrus_voice.py
```

No configuration changes needed — split mode uses the same `.env` and hooks.
