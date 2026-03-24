# Cyrus v1 → v2 Migration Guide

This guide covers everything you need to move an existing Cyrus v1 installation to v2. Read it top to bottom the first time, then use the [step-by-step checklist](#step-by-step-upgrade) at the bottom as your working reference.

---

## 1. Overview

### Why v2 was created

Cyrus v1 was a single-machine, Windows-only tool: all Python files lived at the repository root, and the brain relied on Windows UI Automation (UIA) for nearly every interaction with VS Code. This made it impossible to run the brain on macOS or Linux, difficult to deploy in a Docker container, and hard to extend without touching a growing monolith.

v2 addresses these problems with four major architectural shifts:

| Area | v1 | v2 |
|------|----|----|
| File layout | Root-level `.py` files | All runtime files under `cyrus2/` |
| Configuration | Ad-hoc environment variables | Centralised `cyrus_config.py` module |
| OS support | Windows only (UIA hard-coded) | Cross-platform via headless/Docker mode |
| Security | No authentication | Shared-secret `CYRUS_AUTH_TOKEN` on every port |

Additional improvements: health-check HTTP endpoint, configurable Whisper model, session-state persistence across restarts, and structured logging throughout.

### What is NOT changing

- The voice pipeline (Whisper STT, Silero VAD, Kokoro/Edge TTS) works identically.
- Port numbers are the same defaults (8766, 8767, 8769, 8770).
- Claude Code hook events (`Stop`, `PreToolUse`, `PostToolUse`, `Notification`, `PreCompact`) are handled exactly as before.
- The Companion extension protocol is backwards-compatible; only new messages have been added.

---

## 2. Directory Changes

### File layout comparison

| v1 path | v2 path |
|---------|---------|
| `cyrus_brain.py` | `cyrus2/cyrus_brain.py` |
| `cyrus_voice.py` | `cyrus2/cyrus_voice.py` |
| `cyrus_hook.py` | `cyrus2/cyrus_hook.py` |
| `main.py` | `cyrus2/main.py` (deprecated — see §6) |
| `cyrus_server.py` | `cyrus2/cyrus_server.py` |
| `.env` | `cyrus2/.env` |
| `requirements.txt` | `cyrus2/requirements-brain.txt` and `cyrus2/requirements-voice.txt` |
| `cyrus-companion/` | `cyrus-companion/` (unchanged) |

### Updated run commands

**Starting the brain:**

```bash
# v1
python cyrus_brain.py

# v2 — option A: run from project root
python cyrus2/cyrus_brain.py

# v2 — option B: change into the subdirectory first
cd cyrus2
python cyrus_brain.py
```

**Starting the voice service:**

```bash
# v1
python cyrus_voice.py

# v2
python cyrus2/cyrus_voice.py
# or: cd cyrus2 && python cyrus_voice.py
```

**Starting the hook script** (called by Claude Code, not run directly — but the path in `~/.claude/settings.json` must be updated):

```bash
# v1 path used in hook config
/path/to/project/cyrus_hook.py

# v2 path used in hook config
/path/to/project/cyrus2/cyrus_hook.py
```

**Deprecated monolith:**

```bash
# v1
python main.py

# v2 — prefer split services; see §6 for monolith deprecation notes
python cyrus2/cyrus_brain.py   # Terminal 1
python cyrus2/cyrus_voice.py   # Terminal 2
```

---

## 3. Configuration Migration

### Moving your .env file

Your v1 `.env` lived at the project root. v2 expects it inside `cyrus2/`.

```bash
# Copy your existing .env into the new location
cp .env cyrus2/.env

# Or start fresh from the template
cp cyrus2/.env.example cyrus2/.env
```

### New environment variables in v2

The following variables are new. All have defaults except `CYRUS_AUTH_TOKEN`, which you **must** set explicitly (see §5).

| Variable | Default | Purpose |
|----------|---------|---------|
| `CYRUS_AUTH_TOKEN` | *(none — blocks all clients if unset)* | Shared secret for all TCP connections |
| `CYRUS_HEADLESS` | `0` | Set to `1` to disable all Windows UIA code (required for Docker/Linux/macOS) |
| `CYRUS_WHISPER_MODEL` | `medium.en` | Whisper model to load (`tiny.en`, `base.en`, `small.en`, `medium.en`) |
| `CYRUS_STATE_FILE` | `~/.cyrus/state.json` | Path for session-state persistence JSON |
| `CYRUS_HEALTH_PORT` | `8771` | Port for the health-check HTTP server |

### Variables that existed in v1 and still work

All previously recognised variables (`CYRUS_BRAIN_PORT`, `CYRUS_HOOK_PORT`, `CYRUS_MOBILE_PORT`, `CYRUS_COMPANION_PORT`, `CYRUS_SERVER_PORT`, `CYRUS_TTS_TIMEOUT`, `CYRUS_SOCKET_TIMEOUT`, `CYRUS_SPEECH_THRESHOLD`, `CYRUS_SILENCE_WINDOW`, `CYRUS_MIN_SPEECH_DURATION`, `CYRUS_MAX_SPEECH_WORDS`, `CYRUS_CHAT_POLL_MS`, `CYRUS_PERMISSION_POLL_MS`) are read through `cyrus_config.py` and behave as before.

---

## 4. Claude Code Hook Path Updates

Your `~/.claude/settings.json` currently points hook commands at the v1 file locations. Update every occurrence of the old path.

### Before (v1)

```json
{
  "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "/path/to/project/.venv/bin/python /path/to/project/cyrus_hook.py" }] }],
    "PreToolUse": [{ "hooks": [{ "type": "command", "command": "/path/to/project/.venv/bin/python /path/to/project/cyrus_hook.py" }] }],
    "PostToolUse": [{ "hooks": [{ "type": "command", "command": "/path/to/project/.venv/bin/python /path/to/project/cyrus_hook.py" }] }],
    "Notification": [{ "hooks": [{ "type": "command", "command": "/path/to/project/.venv/bin/python /path/to/project/cyrus_hook.py" }] }],
    "PreCompact": [{ "hooks": [{ "type": "command", "command": "/path/to/project/.venv/bin/python /path/to/project/cyrus_hook.py" }] }]
  }
}
```

### After (v2)

```json
{
  "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "/path/to/project/.venv/bin/python /path/to/project/cyrus2/cyrus_hook.py" }] }],
    "PreToolUse": [{ "hooks": [{ "type": "command", "command": "/path/to/project/.venv/bin/python /path/to/project/cyrus2/cyrus_hook.py" }] }],
    "PostToolUse": [{ "hooks": [{ "type": "command", "command": "/path/to/project/.venv/bin/python /path/to/project/cyrus2/cyrus_hook.py" }] }],
    "Notification": [{ "hooks": [{ "type": "command", "command": "/path/to/project/.venv/bin/python /path/to/project/cyrus2/cyrus_hook.py" }] }],
    "PreCompact": [{ "hooks": [{ "type": "command", "command": "/path/to/project/.venv/bin/python /path/to/project/cyrus2/cyrus_hook.py" }] }]
  }
}
```

The only change is inserting `cyrus2/` into the script path. The venv path is unchanged.

**Important:** If `cyrus_hook.py` cannot reach the brain it exits with code `0` (it never blocks Claude Code), so a stale path will silently drop all hook events rather than crashing Claude Code. Verify the path is correct before assuming hooks are working.

---

## 5. Authentication (New in v2)

v2 requires a shared-secret token on every TCP connection. The brain, voice service, hook script, and Companion extension all use the same value.

### Generating a token

```bash
python -c "import secrets; print(secrets.token_hex(16))"
# Example output: 4a7f2c91e3b05d8a1f6e9c2b7d4e0f3a
```

### Setting the token

Add the generated value to `cyrus2/.env`:

```
CYRUS_AUTH_TOKEN=4a7f2c91e3b05d8a1f6e9c2b7d4e0f3a
```

All clients read `CYRUS_AUTH_TOKEN` from the environment automatically. No further configuration is needed if everything runs on the same machine with the same `.env`.

### What happens if the token is missing

- If `CYRUS_AUTH_TOKEN` is not set, the brain generates a random token at startup and prints it to stderr. Since no client knows this token, **all connections will be rejected** until you set a matching value.
- Connections that present the wrong token are closed immediately with an error logged.

### Remote / Docker deployments

When running the brain in Docker or on a remote machine, pass the token via the environment:

```bash
# Docker
docker run -e CYRUS_AUTH_TOKEN=<your-token> ...

# Remote machine
export CYRUS_AUTH_TOKEN=<your-token>
python cyrus2/cyrus_brain.py
```

The voice service and hook script on the host must have the same variable set.

---

## 6. main.py Deprecation

`cyrus2/main.py` (the single-process monolith) still exists and still works in v2, but it is **deprecated** and will be removed in Cyrus 3.0.

Reasons:
- The monolith cannot restart the brain without also reloading Whisper (slow, ~30 s on CPU).
- It cannot run the voice service on a separate machine.
- It makes headless/Docker deployment harder because audio and brain logic are entangled.

**Recommended replacement:**

```bash
# Terminal 1 — brain (no audio dependencies)
python cyrus2/cyrus_brain.py

# Terminal 2 — voice (no UIA dependencies)
python cyrus2/cyrus_voice.py
```

If you have scripts or aliases that invoke `main.py`, update them now. Continued use of `main.py` will work through the v2 lifecycle but expect it to disappear in v3.

---

## 7. New Features Summary

A brief reference to everything new in v2:

| Feature | How to use |
|---------|-----------|
| **Authentication tokens** | Set `CYRUS_AUTH_TOKEN` in `cyrus2/.env` (§5) |
| **Headless / Docker mode** | Set `CYRUS_HEADLESS=1`; all Windows UIA code is skipped. Companion extension handles submit and permission clicks. |
| **Docker deployment** | `docker compose up` from `cyrus2/`; see `docs/13-docker-containerization.md` |
| **Centralised config module** | `cyrus2/cyrus_config.py` is the single source of truth for all env-var defaults; import `from cyrus_config import cfg` in any module |
| **Health check endpoint** | `GET http://localhost:8771/health` returns `{"status": "ok", ...}`. Port configurable via `CYRUS_HEALTH_PORT`. |
| **Session persistence** | Brain saves session state on shutdown and restores it on startup. Default path: `~/.cyrus/state.json`. Override with `CYRUS_STATE_FILE`. |
| **Configurable Whisper model** | Set `CYRUS_WHISPER_MODEL` to `tiny.en`, `base.en`, `small.en`, or `medium.en`. Invalid values fall back to `medium.en` with a warning. |
| **Structured logging** | All services use Python `logging` with consistent level/format instead of bare `print()` calls. Set `CYRUS_LOG_LEVEL=DEBUG` for verbose output. |
| **Companion extension registration** | Extension now connects to brain on port 8770, registers its workspace, and sends focus/blur events. Enables headless session discovery. |

---

## 8. Step-by-Step Upgrade

Work through these steps in order. Each step is independent of the next, so you can stop and test between them.

**1. Pull the latest code**

```bash
cd /path/to/project
git pull
```

**2. Install updated Python dependencies**

```bash
source .venv/bin/activate          # or .venv\Scripts\activate on Windows
pip install -r cyrus2/requirements-brain.txt
pip install -r cyrus2/requirements-voice.txt
```

**3. Move your .env**

```bash
# If you have a customised v1 .env at the project root:
cp .env cyrus2/.env

# If you are starting fresh:
cp cyrus2/.env.example cyrus2/.env
```

**4. Generate and set an auth token**

```bash
python -c "import secrets; print(secrets.token_hex(16))"
```

Open `cyrus2/.env` in an editor and set:

```
CYRUS_AUTH_TOKEN=<the value you just generated>
```

**5. Update hook paths in ~/.claude/settings.json**

Open `~/.claude/settings.json`. Find every line containing `cyrus_hook.py` and insert `cyrus2/` before the filename:

```
# Before
.../cyrus_hook.py

# After
.../cyrus2/cyrus_hook.py
```

Save the file. No reload of Claude Code is needed; hook commands are read fresh on each invocation.

**6. Rebuild and reinstall the Companion extension**

```bash
cd cyrus-companion
npm install
npm run compile
code --install-extension cyrus-companion-*.vsix
```

Reload VS Code (`Ctrl+Shift+P` → "Developer: Reload Window") after installing.

**7. Start the services with the new paths**

```bash
# Terminal 1
python cyrus2/cyrus_brain.py

# Terminal 2
python cyrus2/cyrus_voice.py
```

Check stderr on the brain for a line like `Auth token loaded` (or a warning if the token was auto-generated). Check that the Companion extension connects: you should see a `register` log line from the brain within a few seconds of VS Code loading.

**8. Smoke test**

- Say "Cyrus, what time is it?" — the utterance should route through and Claude Code should respond.
- Trigger a tool-use action and verify the hook fires: the brain log should show an incoming hook event.
- Hit the health endpoint: `curl http://localhost:8771/health` should return `{"status": "ok"}`.

**9. Clean up old root-level files (optional)**

Once you are satisfied that v2 is working, the old root-level files (`cyrus_brain.py`, `cyrus_voice.py`, `cyrus_hook.py`, `main.py` at the root, root-level `.env`) can be deleted. They are no longer used by any v2 component.

```bash
# Only do this after confirming v2 works
git rm cyrus_brain.py cyrus_voice.py cyrus_hook.py main.py
rm .env   # if you copied it rather than moved it
```

---

## Troubleshooting

**Brain starts but all clients are immediately disconnected**
The auth token does not match. Verify `CYRUS_AUTH_TOKEN` is identical in `cyrus2/.env` and in the environment of every client (voice service, hook invocations). Restart the brain after changing the token.

**Hook events are silent (no log lines on brain)**
The hook path in `~/.claude/settings.json` still points to the old location, or the `.venv` Python path is wrong. Test manually:

```bash
echo '{}' | /path/to/.venv/bin/python /path/to/cyrus2/cyrus_hook.py
```

It should exit `0` with no errors.

**Companion extension does not register**
Check the extension's Output panel (View → Output → Cyrus Companion). If it shows connection refused, confirm the brain is running and `CYRUS_COMPANION_PORT` (default 8770) is not blocked by a firewall. If you changed `brainPort` in VS Code settings, make sure `CYRUS_COMPANION_PORT` matches.

**Voice service cannot connect to brain**
Confirm `CYRUS_BRAIN_PORT` (default 8766) matches on both sides, and that `CYRUS_AUTH_TOKEN` is set in both environments.

**Health check returns connection refused**
The health endpoint only starts if `CYRUS_HEALTH_PORT` is set (or uses the default 8771). The port may already be in use; set a different value in `cyrus2/.env` and restart the brain.
