# Cyrus Documentation

Voice assistant layer for Claude Code in VS Code — speak naturally, Cyrus transcribes and routes your words to Claude, then reads the response aloud.

## Table of Contents

| # | Document | Description |
|---|----------|-------------|
| 01 | [Architecture Overview](./01-overview.md) | High-level architecture, tech stack, service roles, deployment modes |
| 02 | [Startup & Lifecycle](./02-startup-and-lifecycle.md) | Boot sequence, CLI args, port map, shutdown, reconnection logic |
| 03 | [Voice Pipeline](./03-voice-pipeline.md) | Mic capture → Silero VAD → Whisper STT → Kokoro/Edge TTS → speaker |
| 04 | [Brain & Routing](./04-brain-and-routing.md) | Command routing, wake words, session management, ChatWatcher, submit pipeline |
| 05 | [Hooks & Permissions](./05-hooks-and-permissions.md) | Claude Code hook script, all 5 hook events, PermissionWatcher, auto-approval |
| 06 | [Networking & Protocols](./06-networking-and-protocols.md) | TCP/WebSocket protocols, message formats, connection lifecycle |
| 07 | [Threading & Concurrency](./07-threading-and-concurrency.md) | Asyncio + OS threads, sync primitives, COM threading, deadlock prevention |
| 08 | [Companion Extension](./08-companion-extension.md) | VS Code extension, platform-adaptive IPC, submit pipeline, configuration |
| 09 | [Error Handling & Recovery](./09-error-handling-and-recovery.md) | Recovery strategies, fallback chains, common issues, debugging |
| 10 | [Setup & Installation](./10-setup-and-installation.md) | Prerequisites, dependencies, dev setup, network scenarios, hook config |
| 11 | [File Reference](./11-file-reference.md) | File-by-file API reference — every function, class, and constant |


## New Features for Cyrus 2.0
| 12 | [Code Audit](./12-code-audit.md) | Code quality audit — anti-patterns, DRY violations, thread safety, security |
| 13 | [Docker Containerization](./13-docker-containerization.md) | Headless brain mode, Docker setup, cross-platform support (macOS/Linux/Windows) |
| 14 | [Test Suite](./14-test-suite.md) | pytest test plan — pure function tests, hook parsing, VAD, integration tests |
| 15 | [Recommendations](./15-recommendations.md) | Feature recommendations — auth, config, health checks, packaging |
| 16 | [Logging System](./16-logging-system.md) | Replace 218 print() calls with structured logging, env-configurable levels |
| 17 | [Ruff Linting & Formatting](./17-ruff-linting.md) | Add ruff for linting + formatting — replaces flake8/black/isort in one tool |

## Quick Start

```bash
# Terminal 1 — Brain (machine with VS Code)
python cyrus_brain.py

# Terminal 2 — Voice (same machine or remote)
python cyrus_voice.py --host <brain-ip>
```

Or run everything in one process:

```bash
python main.py
```

See [10 — Setup & Installation](./10-setup-and-installation.md) for full setup instructions.

## Reading Order

**New to Cyrus?** Start here:
1. [01 — Architecture Overview](./01-overview.md) — understand the big picture
2. [10 — Setup & Installation](./10-setup-and-installation.md) — get it running
3. [03 — Voice Pipeline](./03-voice-pipeline.md) — how audio flows through the system

**Working on the codebase?** Also read:
4. [04 — Brain & Routing](./04-brain-and-routing.md) — command processing logic
5. [07 — Threading & Concurrency](./07-threading-and-concurrency.md) — critical for avoiding bugs
6. [11 — File Reference](./11-file-reference.md) — quick lookup for any function/class
7. [12 — Code Audit](./12-code-audit.md) — known issues and prioritized fixes
