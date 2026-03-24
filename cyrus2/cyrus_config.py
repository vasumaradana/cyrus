"""
cyrus_config.py — Centralized configuration for Cyrus 2.0

All tuneable constants are defined here with environment-variable overrides so
that deployments can adjust behaviour without modifying source code.  Every
constant is read from its corresponding CYRUS_* env var at import time; if the
var is absent the hardcoded default is used.

Usage
-----
    from cyrus_config import BRAIN_PORT, TTS_TIMEOUT, SPEECH_THRESHOLD

Environment variables
---------------------
See .env.example in the cyrus2/ directory for a full listing with defaults and
descriptions.  Any of the variables listed there can be exported in the shell
or placed in a .env file (loaded by your process runner) to override the
defaults at runtime.

No hardware or third-party packages are imported here — this module is safe to
use in CI, headless servers, and test environments.
"""

from __future__ import annotations

import hmac
import os
import secrets
import sys

# ── Port assignments ───────────────────────────────────────────────────────────
# Each service owns one port.  Override via the corresponding CYRUS_*_PORT var.
# All ports are integers; providing a non-integer value will raise ValueError.

# Brain TCP server — receives voice utterances from cyrus_voice.py
BRAIN_PORT: int = int(os.environ.get("CYRUS_BRAIN_PORT", "8766"))

# Hook TCP server — Claude Code Stop/PreToolUse/PostToolUse hooks connect here
HOOK_PORT: int = int(os.environ.get("CYRUS_HOOK_PORT", "8767"))

# Mobile WebSocket — streams events to the Cyrus mobile companion app
MOBILE_PORT: int = int(os.environ.get("CYRUS_MOBILE_PORT", "8769"))

# VS Code companion extension — brain connects here to submit text without UIA
COMPANION_PORT: int = int(os.environ.get("CYRUS_COMPANION_PORT", "8770"))

# Standalone server (cyrus_server.py) — remote brain for mobile-only setups
SERVER_PORT: int = int(os.environ.get("CYRUS_SERVER_PORT", "8765"))

# Health check HTTP server — exposes GET /health for Docker/k8s liveness probes
HEALTH_PORT: int = int(os.environ.get("CYRUS_HEALTH_PORT", "8771"))

# ── Timeout constants ──────────────────────────────────────────────────────────
# Timeouts are in seconds unless the name includes a different unit.

# Maximum wall-clock seconds to wait for a TTS synthesis + playback call
TTS_TIMEOUT: float = float(os.environ.get("CYRUS_TTS_TIMEOUT", "25.0"))

# Socket connect/recv timeout used by cyrus_hook.py when reaching the brain
SOCKET_TIMEOUT: int = int(os.environ.get("CYRUS_SOCKET_TIMEOUT", "10"))

# ── VAD (Voice Activity Detection) thresholds ─────────────────────────────────
# These values tune the Silero VAD model behaviour in cyrus_voice.py.

# Silero probability above which a frame is classified as speech (0.0–1.0)
SPEECH_THRESHOLD: float = float(os.environ.get("CYRUS_SPEECH_THRESHOLD", "0.6"))

# Milliseconds of consecutive silence required to end an utterance recording
SILENCE_WINDOW: int = int(os.environ.get("CYRUS_SILENCE_WINDOW", "1500"))

# Minimum milliseconds of speech required before an utterance is submitted
MIN_SPEECH_DURATION: int = int(os.environ.get("CYRUS_MIN_SPEECH_DURATION", "500"))

# ── Watcher poll intervals ─────────────────────────────────────────────────────
# Intervals (in seconds) for the background threads that watch the VS Code UI.

# How often ChatWatcher polls the Claude Code chat output pane for new text
CHAT_WATCHER_POLL_INTERVAL: float = float(os.environ.get("CYRUS_CHAT_POLL_MS", "0.5"))

# How often PermissionWatcher polls for Claude Code permission dialogs
PERMISSION_WATCHER_POLL_INTERVAL: float = float(
    os.environ.get("CYRUS_PERMISSION_POLL_MS", "0.3")
)

# ── Miscellaneous ──────────────────────────────────────────────────────────────

# Hard cap on spoken words in a TTS call (~12 s at 150 wpm)
MAX_SPEECH_WORDS: int = int(os.environ.get("CYRUS_MAX_SPEECH_WORDS", "200"))

# ── Whisper speech-to-text ─────────────────────────────────────────────────────
# English-only model variants in ascending size order.  The default (medium.en)
# gives good accuracy; use tiny.en or base.en on CPU-constrained hardware.

VALID_WHISPER_MODELS: list[str] = ["tiny.en", "base.en", "small.en", "medium.en"]

WHISPER_MODEL: str = os.environ.get("CYRUS_WHISPER_MODEL", "medium.en")

if WHISPER_MODEL not in VALID_WHISPER_MODELS:
    print(
        f"WARN: CYRUS_WHISPER_MODEL={WHISPER_MODEL!r} not in {VALID_WHISPER_MODELS}",
        file=sys.stderr,
    )
    print(
        "      Using default: medium.en",
        file=sys.stderr,
    )
    WHISPER_MODEL = "medium.en"

# ── Session state persistence ─────────────────────────────────────────────────
# Path to the JSON file where brain session state (aliases, pending queues,
# project mappings) is saved on shutdown and restored on startup.
# Leave empty to use the default: ~/.cyrus/state.json

CYRUS_STATE_FILE: str = os.environ.get("CYRUS_STATE_FILE", "")

# ── Headless mode ─────────────────────────────────────────────────────────────
# When True, all Windows GUI libraries (comtypes, pyautogui, pygetwindow,
# pyperclip, uiautomation) are NOT imported. The companion extension provides
# session discovery and text submission via TCP on port 8770. Set to True in
# Docker / Linux deployments where Windows GUI libraries are unavailable.

HEADLESS: bool = os.environ.get("CYRUS_HEADLESS") == "1"

# ── Authentication ─────────────────────────────────────────────────────────────
# Shared-secret token used to authenticate all TCP port connections.  Every
# client (cyrus_hook.py, cyrus_voice.py, mobile companion) must present this
# token on connection; the brain rejects connections that omit or mismatch it.
#
# If CYRUS_AUTH_TOKEN is not set a random token is generated at startup and
# printed to stderr so the operator can copy it into their .env file.  The
# generated token is unique per process, so leaving the env var unset effectively
# blocks all clients (they will not know the generated token).

AUTH_TOKEN: str = os.environ.get("CYRUS_AUTH_TOKEN", "")
if not AUTH_TOKEN:
    AUTH_TOKEN = secrets.token_hex(16)
    print(
        f"WARN: No CYRUS_AUTH_TOKEN set. Generated: {AUTH_TOKEN}",
        file=sys.stderr,
    )
    print(
        "      Set CYRUS_AUTH_TOKEN in .env or shell. Generate with: "
        'python -c "import secrets; print(secrets.token_hex(16))"',
        file=sys.stderr,
    )


def validate_auth_token(received: str) -> bool:
    """Check if received token matches the configured AUTH_TOKEN.

    Uses hmac.compare_digest for constant-time comparison, preventing
    timing-based side-channel attacks on the token value.

    Args:
        received: The token string received from a connecting client.

    Returns:
        True if received matches AUTH_TOKEN, False otherwise.
    """
    return hmac.compare_digest(received, AUTH_TOKEN)
