# Cyrus Documentation

Voice assistant layer for Claude Code in VS Code — speak naturally, Cyrus transcribes and routes your words to Claude, then reads the response aloud.

## Architecture Overview

Cyrus 2.0 splits its original monolithic design into two cooperating processes:

- **Brain** (`cyrus_brain.py`) — the headless coordination layer. Manages WebSocket connections from the VS Code companion extension, the Claude Code hook script, and optionally a mobile client. Handles session state, permission approval, and routes text to/from Claude Code. Can run in a Docker container.
- **Voice** (`cyrus_voice.py`) — the audio layer. Captures microphone input, runs Silero VAD and Whisper STT locally, sends transcribed text to the Brain over TCP, and plays back TTS responses via Kokoro or Edge TTS.

In **headless mode** (`CYRUS_HEADLESS=1`), the Brain runs without any audio hardware — suitable for Docker deployment on a remote server or CI. The Voice process runs separately on the machine with a microphone and speaker.

## Cyrus 2.0 Structure

All runtime code lives in `cyrus2/`:

```
cyrus2/
├── cyrus_brain.py                   # Brain entry point
├── cyrus_voice.py                   # Voice entry point
├── cyrus_hook.py                    # Claude Code hook script
├── cyrus_config.py                  # Centralised env-var configuration
├── Dockerfile                       # Brain container image
├── docker-compose.yml               # Compose stack
├── requirements-brain.txt           # Brain Python deps
├── requirements-brain-headless.txt  # Brain deps (no audio)
├── .env.example                     # Template for .env
└── tests/                           # pytest test suite
```

VS Code companion extension lives in `cyrus-companion/`:

```
cyrus-companion/
├── src/
│   ├── extension.ts            # Extension entry point
│   ├── brain-connection.ts     # TCP connection to Brain
│   ├── focus-tracker.ts        # Active editor/project tracking
│   └── permission-handler.ts   # Permission request UI
├── package.json
└── .vsix (built artifact)
```

## Table of Contents

| # | Document | Description |
|---|----------|-------------|
| 01 | [Architecture Overview](./01-overview.md) | High-level architecture, tech stack, service roles, deployment modes |
| 02 | [Startup & Lifecycle](./02-startup-and-lifecycle.md) | Boot sequence, CLI args, port map, shutdown, reconnection logic |
| 03 | [Voice Pipeline](./03-voice-pipeline.md) | Mic capture → Silero VAD → Whisper STT → Kokoro/Edge TTS → speaker |
| 04 | [Brain & Routing](./04-brain-and-routing.md) | Command routing, wake words, session management, ChatWatcher, submit pipeline |
| 05 | [Hooks & Permissions](./05-hooks-and-permissions.md) | Claude Code hook script, all 4 hook events, PermissionWatcher, auto-approval |
| 06 | [Networking & Protocols](./06-networking-and-protocols.md) | TCP/WebSocket protocols, message formats, connection lifecycle |
| 07 | [Threading & Concurrency](./07-threading-and-concurrency.md) | Asyncio + OS threads, sync primitives, COM threading, deadlock prevention |
| 08 | [Companion Extension](./08-companion-extension.md) | VS Code extension, platform-adaptive IPC, submit pipeline, configuration |
| 09 | [Error Handling & Recovery](./09-error-handling-and-recovery.md) | Recovery strategies, fallback chains, common issues, debugging |
| 10 | [Setup & Installation](./10-setup-and-installation.md) | Prerequisites, dependencies, dev setup, network scenarios, hook config |
| 11 | [File Reference](./11-file-reference.md) | File-by-file API reference — every function, class, and constant |
| 12 | [Code Audit](./12-code-audit.md) | Code quality audit — anti-patterns, DRY violations, thread safety, security |
| 13 | [Docker Containerization](./13-docker-containerization.md) | Headless brain mode, Docker setup, cross-platform support (macOS/Linux/Windows) |
| 14 | [Test Suite](./14-test-suite.md) | pytest test plan — pure function tests, hook parsing, VAD, integration tests |
| 15 | [Recommendations](./15-recommendations.md) | Feature recommendations — auth, config, health checks, packaging |
| 16 | [Logging System](./16-logging-system.md) | Structured logging, env-configurable levels |
| 17 | [Ruff Linting & Formatting](./17-ruff-linting.md) | ruff for linting + formatting — replaces flake8/black/isort |
| 18 | [Migration Guide](./18-migration-guide.md) | Upgrading from Cyrus 1.x to 2.0 — config, paths, breaking changes |

---

## Quick Start — Traditional Mode

### 1. Create your `.env` file

```bash
cd cyrus2
cp .env.example .env
```

Generate an auth token and add it to `.env`:

```bash
python -c "import secrets; print(secrets.token_hex(16))"
```

Set `CYRUS_AUTH_TOKEN` in `.env` to the generated value. This token must match across the Brain, Voice, hook script, and companion extension.

### 2. Start the Brain

```bash
# Terminal 1
cd cyrus2
python cyrus_brain.py
```

### 3. Start the Voice

```bash
# Terminal 2 (same machine, or a machine with a mic/speaker)
cd cyrus2
python cyrus_voice.py --host <brain-ip>
```

If the Brain is on the same machine, omit `--host` (defaults to `localhost`).

> **Note:** `main.py` exists in `cyrus2/` but is deprecated. Use `cyrus_brain.py` directly.

See [10 — Setup & Installation](./10-setup-and-installation.md) for full setup instructions.

---

## Quick Start — Docker Mode

Docker runs the Brain in headless mode (`CYRUS_HEADLESS=1`). The Voice process still runs natively on the machine with audio hardware.

### 1. Configure `.env`

```bash
cd cyrus2
cp .env.example .env
# Edit .env — set CYRUS_AUTH_TOKEN and any other overrides
```

### 2. Start the Brain container

```bash
cd cyrus2
docker compose up -d
```

Exposed ports (host → container):

| Host port | Container port | Purpose |
|-----------|---------------|---------|
| 8766 | 8766 | Brain TCP (Voice connects here) |
| 8767 | 8767 | Claude Code hook |
| 8769 | 8769 | Mobile WebSocket |
| 8770 | 8770 | VS Code companion extension |

### 3. Start the Voice natively

```bash
cd cyrus2
python cyrus_voice.py --host <docker-host-ip>
```

### 4. Connect the hook to the remote Brain

Set `CYRUS_BRAIN_HOST` in your shell or `.env` on the machine running Claude Code:

```bash
export CYRUS_BRAIN_HOST=<docker-host-ip>
```

The hook script (`cyrus2/cyrus_hook.py`) reads this variable to know where to send hook events.

---

## Configuration

All configuration is driven by environment variables. The defaults below apply when a variable is not set. Load them from a `.env` file at the root of `cyrus2/`, or export them in your shell before starting any process.

| Variable | Default | Description |
|----------|---------|-------------|
| `CYRUS_AUTH_TOKEN` | *(required)* | Shared secret — must match across Brain, Voice, hook, and extension. See [Authentication](#authentication). |
| `CYRUS_BRAIN_PORT` | `8766` | Brain TCP server port (Voice connects here) |
| `CYRUS_HOOK_PORT` | `8767` | Claude Code hook listener port |
| `CYRUS_MOBILE_PORT` | `8769` | Mobile WebSocket server port |
| `CYRUS_COMPANION_PORT` | `8770` | VS Code companion extension port |
| `CYRUS_SERVER_PORT` | `8765` | Standalone server port |
| `CYRUS_HEALTH_PORT` | `8771` | Health check HTTP server port |
| `CYRUS_HEADLESS` | `0` | Set to `1` to disable all audio (required for Docker) |
| `CYRUS_WHISPER_MODEL` | `medium.en` | Whisper model size: `tiny.en`, `base.en`, `small.en`, `medium.en` |
| `CYRUS_TTS_TIMEOUT` | `25.0` | TTS synthesis timeout in seconds |
| `CYRUS_SOCKET_TIMEOUT` | `10` | Hook socket connection timeout in seconds |
| `CYRUS_SPEECH_THRESHOLD` | `0.6` | Silero VAD confidence threshold (0.0–1.0) |
| `CYRUS_SILENCE_WINDOW` | `1500` | Milliseconds of silence that ends an utterance |
| `CYRUS_MIN_SPEECH_DURATION` | `500` | Minimum milliseconds of speech before submitting |
| `CYRUS_CHAT_POLL_MS` | `0.5` | ChatWatcher poll interval in milliseconds |
| `CYRUS_PERMISSION_POLL_MS` | `0.3` | PermissionWatcher poll interval in milliseconds |
| `CYRUS_MAX_SPEECH_WORDS` | `200` | Maximum word count for TTS output |
| `CYRUS_STATE_FILE` | `""` | Path to session state JSON; defaults to `~/.cyrus/state.json` |
| `CYRUS_BRAIN_HOST` | — | Brain host for hook to connect to when Brain is remote |

---

## Authentication

`CYRUS_AUTH_TOKEN` is a required shared secret that authenticates connections between all Cyrus components. Every connection (hook → Brain, extension → Brain, Voice → Brain) sends this token on handshake. If the token is missing or mismatched, the connection is rejected.

**Generate a token:**

```bash
python -c "import secrets; print(secrets.token_hex(16))"
```

**Set it consistently** in every location:

- `cyrus2/.env` (loaded by Brain, Voice, and hook)
- `CYRUS_AUTH_TOKEN` in the shell environment on any machine running `cyrus_voice.py`
- The environment that launches VS Code (so the companion extension inherits it)

**If `CYRUS_AUTH_TOKEN` is unset**, a random token is generated each time the Brain starts. Since connecting clients won't know the generated token, they will be rejected. Always set a stable token in `.env`.

---

## VS Code Companion Extension Setup

The companion extension connects VS Code to the Brain, enabling focus tracking (active file and project), permission request prompts, and the command submit pipeline.

### Build

```bash
cd cyrus-companion
npm install
npm run compile
```

To produce an installable `.vsix`:

```bash
npm install -g @vscode/vsce
vsce package
```

### Install

In VS Code: **Extensions → ... → Install from VSIX** → select the generated `.vsix` file.

Or via the CLI:

```bash
code --install-extension cyrus-companion-*.vsix
```

### Configure

Open VS Code settings (`Ctrl+,`) and search for **Cyrus**:

| Setting | Default | Description |
|---------|---------|-------------|
| `cyrusCompanion.brainHost` | `localhost` | Hostname or IP of the Brain process |
| `cyrusCompanion.brainPort` | `8770` | Port the Brain listens on for extension connections |
| `cyrusCompanion.focusCommand` | — | Optional shell command to run when editor focus changes |

If the Brain is running in Docker on a remote host, set `cyrusCompanion.brainHost` to that host's IP or hostname.

---

## Claude Code Hook Configuration

Cyrus intercepts Claude Code lifecycle events via hook scripts. Add the following to your Claude Code settings (`.claude/settings.json` in your project, or the global settings file):

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/cyrus2/cyrus_hook.py Stop"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/cyrus2/cyrus_hook.py PreToolUse"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/cyrus2/cyrus_hook.py PostToolUse"
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/cyrus2/cyrus_hook.py Notification"
          }
        ]
      }
    ]
  }
}
```

Replace `/path/to/cyrus2/` with the absolute path to your `cyrus2/` directory. If the Brain is running on a different machine, also export `CYRUS_BRAIN_HOST` in the environment that runs Claude Code (or add it to your `.env`).

---

## Health Checks

The Brain exposes a lightweight HTTP health endpoint on port `8771` (configurable via `CYRUS_HEALTH_PORT`).

**Request:**

```
GET http://localhost:8771/health
```

**Response:**

```json
{
  "status": "ok",
  "timestamp": 1710000000.0,
  "sessions": 2,
  "active_project": "/home/user/projects/my-app",
  "headless": false
}
```

| Field | Description |
|-------|-------------|
| `status` | `"ok"` when the Brain is healthy |
| `timestamp` | Unix timestamp of the response |
| `sessions` | Number of currently connected clients |
| `active_project` | Path of the project currently in focus (from companion extension) |
| `headless` | `true` when `CYRUS_HEADLESS=1` |

Use this endpoint in Docker health checks, monitoring scripts, or to verify connectivity before starting the Voice process.

---

## Session Persistence

The Brain saves session state to disk on shutdown and restores it on startup. This preserves context across restarts.

**Default path:** `~/.cyrus/state.json`

Override with `CYRUS_STATE_FILE`:

```bash
CYRUS_STATE_FILE=/var/cyrus/state.json python cyrus_brain.py
```

**What is saved:**

- Active project path
- Session identifiers
- Accumulated conversation context

If the state file does not exist on startup, the Brain initialises a fresh session. The `~/.cyrus/` directory is created automatically if it does not exist.

In Docker, mount a host path to persist state across container restarts:

```yaml
volumes:
  - ~/.cyrus:/root/.cyrus
```

---

## Troubleshooting

### Brain won't start in Docker

- **Check `CYRUS_AUTH_TOKEN`** — it must be set in `.env` before `docker compose up`. The Brain will refuse to start and log an error if it is missing.
- **Check `CYRUS_HEADLESS`** — must be `1` in the container environment. The `docker-compose.yml` sets this automatically; verify it has not been overridden.
- **Port conflicts** — if any of ports 8765–8771 are in use on the host, edit the port mappings in `docker-compose.yml`.
- **View logs:** `docker compose logs -f brain`

### Companion extension won't register with Brain

- Confirm the Brain is running and `cyrusCompanion.brainPort` matches `CYRUS_COMPANION_PORT` (default `8770`).
- If the Brain is remote, set `cyrusCompanion.brainHost` to its IP — `localhost` will not work.
- Check that `CYRUS_AUTH_TOKEN` is set identically in both the Brain environment and the extension settings.
- Open the VS Code Output panel → select **Cyrus Companion** for connection logs.

### Hook connection refused

- The hook script connects to the Brain on `CYRUS_HOOK_PORT` (default `8767`). Verify the Brain is running and that port is reachable.
- If the Brain is on a different machine, export `CYRUS_BRAIN_HOST` in the shell where Claude Code runs.
- Firewall rules may block the connection — ensure port `8767` (and `8766`, `8770`) are open between the machines.
- Test connectivity: `curl -s http://<brain-host>:8771/health`

### Voice can't connect to Brain

- Confirm the Brain is running and accessible on port `CYRUS_BRAIN_PORT` (default `8766`).
- Pass `--host <brain-ip>` to `cyrus_voice.py` when the Brain is not on `localhost`.
- Verify `CYRUS_AUTH_TOKEN` matches in both environments.

### Whisper model is slow or crashes

- Switch to a lighter model: `CYRUS_WHISPER_MODEL=base.en` or `tiny.en`.
- Ensure you have sufficient RAM — `medium.en` requires ~3 GB, `small.en` ~1 GB.

---

## Reading Order

**New to Cyrus?** Start here:

1. [01 — Architecture Overview](./01-overview.md) — understand the big picture
2. [10 — Setup & Installation](./10-setup-and-installation.md) — get it running
3. [03 — Voice Pipeline](./03-voice-pipeline.md) — how audio flows through the system

**Upgrading from Cyrus 1.x?** Read first:

4. [18 — Migration Guide](./18-migration-guide.md) — config changes, renamed files, breaking changes

**Working on the codebase?** Also read:

5. [04 — Brain & Routing](./04-brain-and-routing.md) — command processing logic
6. [07 — Threading & Concurrency](./07-threading-and-concurrency.md) — critical for avoiding bugs
7. [11 — File Reference](./11-file-reference.md) — quick lookup for any function/class
8. [12 — Code Audit](./12-code-audit.md) — known issues and prioritised fixes
9. [13 — Docker Containerization](./13-docker-containerization.md) — container deployment details
10. [14 — Test Suite](./14-test-suite.md) — running and extending the test suite
