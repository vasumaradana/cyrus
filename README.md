# Cyrus — Voice Layer for Claude Code

Voice assistant for Claude Code in VS Code. Speak naturally, Cyrus transcribes and routes your words to Claude Code, then reads the response aloud.

**Whisper STT + Silero VAD + Edge TTS + VS Code Companion Extension**

## Architecture

```
Phone/Mic ──► Cyrus Voice ──► Cyrus Brain ──► VS Code (Claude Code)
                (any machine)    (dev machine)    (companion extension)
                Whisper STT      routing/UIA       focus + paste + enter
                Edge TTS         hooks/watchers    SetForegroundWindow
```

Two services, independently deployable:

| Service | What it does | Where it runs |
|---------|-------------|---------------|
| **Voice** | Mic capture, VAD, Whisper transcription, TTS playback | Any machine (local or remote) |
| **Brain** | Command routing, VS Code automation, Claude Code hooks, permission handling | Dev machine (with VS Code) |

## Quick Start (Developer)

**Prerequisites:** Python 3.10+, Node.js 18+, VS Code with the Claude Code extension installed.
CUDA GPU recommended for Whisper (falls back to CPU).

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/user/cyrus.git
cd cyrus

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys (e.g. `ANTHROPIC_API_KEY`).

### 3. Build and install the VS Code companion extension

```bash
cd cyrus-companion
npm install
npm run compile
npx @vscode/vsce package --no-dependencies
code --install-extension cyrus-companion-*.vsix --force
cd ..
```

Restart VS Code after installing.

### 4. Configure Claude Code hooks

Add all 4 hook events to `~/.claude/settings.json`. Use the **venv Python** and the absolute path to `cyrus_hook.py`:

```json
{
  "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "/absolute/path/.venv/bin/python /absolute/path/cyrus_hook.py", "timeout": 5 }] }],
    "PreToolUse": [{ "hooks": [{ "type": "command", "command": "/absolute/path/.venv/bin/python /absolute/path/cyrus_hook.py", "timeout": 5 }] }],
    "PostToolUse": [{ "hooks": [{ "type": "command", "command": "/absolute/path/.venv/bin/python /absolute/path/cyrus_hook.py", "timeout": 5 }] }],
    "Notification": [{ "hooks": [{ "type": "command", "command": "/absolute/path/.venv/bin/python /absolute/path/cyrus_hook.py", "timeout": 5 }] }]
  }
}
```

Replace `/absolute/path/` with the actual path to your repo.
Use forward slashes, even on Windows (e.g. `C:/source/cyrus/.venv/Scripts/python.exe C:/source/cyrus/cyrus_hook.py`).

### 5. Run both services

```bash
# Terminal 1 — Brain (on the machine with VS Code)
python cyrus_brain.py

# Terminal 2 — Voice (same machine or remote)
python cyrus_voice.py --host <brain-ip>
```

For local use, `--host` defaults to `localhost`.

## Install from Release (Users)

Download the two zip packages from [Releases](../../releases):

### 1. Brain (dev machine with VS Code + Claude Code)

```powershell
# Windows
Expand-Archive cyrus-brain-0.1.2.zip -DestinationPath cyrus-brain
cd cyrus-brain
powershell -ExecutionPolicy Bypass -File install-brain.ps1
```

```bash
# macOS / Linux
unzip cyrus-brain-0.1.2.zip -d cyrus-brain
cd cyrus-brain
bash install-brain.sh
```

The installer handles everything automatically:
- Creates a Python virtual environment and installs dependencies
- Installs the VS Code companion extension
- Configures all 4 Claude Code hooks in `~/.claude/settings.json` (Stop, PreToolUse, PostToolUse, Notification)
- Backs up any existing `settings.json` to `settings.json.bak`
- Creates `start-brain.bat` / `start-brain.sh` launch script

**After install, restart VS Code.**

### 2. Voice (any machine)

```powershell
# Windows
Expand-Archive cyrus-voice-0.1.2.zip -DestinationPath cyrus-voice
cd cyrus-voice
powershell -ExecutionPolicy Bypass -File install-voice.ps1 -BrainHost <brain-ip>
```

```bash
# macOS / Linux
unzip cyrus-voice-0.1.2.zip -d cyrus-voice
cd cyrus-voice
bash install-voice.sh --brain-host <brain-ip>
```

This will:
- Install Python dependencies (Whisper, VAD, TTS)
- Download/configure speech models
- Create `start-voice.bat` / `start-voice.sh` launch script

### Running

```bash
# On the brain machine
start-brain.bat          # or ./start-brain.sh

# On the voice machine
start-voice.bat          # or ./start-voice.sh
```

## Networking

Voice connects to Brain on **port 8766** (TCP). Both machines must be reachable.

| Setup | Configuration |
|-------|--------------|
| **Local** (same machine) | Default — no config needed |
| **LAN / ZeroTier / Tailscale** | `--host <brain-ip>` when starting voice |
| **Remote** | Ensure port 8766 is reachable (VPN or tunnel) |

Brain also listens on **port 8767** for Claude Code hooks (local only).

## Voice Commands

After the wake word ("Cyrus"):

| Command | Action |
|---------|--------|
| `switch to [name]` | Lock routing to a specific VS Code project |
| `auto` / `unlock` | Follow window focus again |
| `which project` | Hear which session is active |
| `last message` | Replay the last Claude response |
| `pause` | Toggle listening on/off |
| `yes` / `no` | Approve/deny permission prompts |

Anything else is forwarded to Claude Code as a message.

## Hotkeys

| Key | Action |
|-----|--------|
| F9 | Pause / resume listening |
| F7 | Stop speaking + clear speech queue |
| F8 | Read clipboard aloud |

## Claude Code Hooks

All 4 hook events are configured automatically by the brain installer:

| Hook | What Cyrus does |
|------|----------------|
| **Stop** | Reads Claude's response aloud via TTS |
| **PreToolUse** | Pre-arms permission watcher for voice approval |
| **PostToolUse** | Announces file edits, reports command failures |
| **Notification** | Speaks Claude Code notifications aloud |

## Building Release Packages

```powershell
powershell -ExecutionPolicy Bypass -File build-release.ps1 -Version 0.1.2
```

Creates `dist/cyrus-voice-0.1.2.zip` and `dist/cyrus-brain-0.1.2.zip`.

## Requirements

- Python 3.10+
- Node.js 18+ (for building the companion extension)
- VS Code with Claude Code extension
- Windows 10/11 (full UIA support), macOS/Linux (partial — no permission watcher)
- CUDA GPU recommended for Whisper (falls back to CPU)

## Project Structure

```
cyrus_voice.py          — Voice service (mic/VAD/Whisper/TTS)
cyrus_brain.py          — Brain service (routing/UIA/hooks/watchers)
cyrus_hook.py           — Claude Code hook script (all 4 events)
cyrus-companion/        — VS Code extension (submit text to Claude Code)
requirements-voice.txt  — Voice service dependencies
requirements-brain.txt  — Brain service dependencies
install-voice.ps1/.sh   — Voice installer
install-brain.ps1/.sh   — Brain installer
build-release.ps1       — Packages both zips for distribution
```
