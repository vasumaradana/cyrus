# Plan 027: Create Centralized Config Module

## Summary

Create `cyrus2/cyrus_config.py` with a `ConfigManager` class that consolidates all hardcoded ports, timeouts, and thresholds into one module. Every value reads from an environment variable with a fallback matching the current codebase default. Modify the four root-level consumer files (`cyrus_brain.py`, `cyrus_voice.py`, `cyrus_hook.py`, `cyrus_server.py`) to import from the config instead of defining their own constants. Update `.env.example` with all configurable keys.

## Dependencies

None blocking. The `cyrus2/` directory exists (empty). Other plans (009, 018) also create files there.

**Note on cyrus2/ vs. root**: The interview answer says "assume issues 005+ complete" and work with `cyrus2/` files. In practice, `cyrus2/` is empty — all code lives at root level. Following the pattern established by plans 009 and 018, the new config module goes in `cyrus2/` while consumer modifications target the root-level scripts. When Python runs these scripts, `sys.path[0]` is set to the script's directory (the project root), so `from cyrus2.cyrus_config import ...` works without `sys.path` manipulation.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/cyrus_config.py` with ConfigManager | Does not exist | Create |
| BRAIN_PORT=8766 | Hardcoded in `cyrus_brain.py:65`, `cyrus_voice.py:60` | Centralize |
| HOOK_PORT=8767 | Hardcoded in `cyrus_brain.py:66`; misnamed as `BRAIN_PORT` in `cyrus_hook.py:16` | Centralize + fix name |
| MOBILE_PORT=8769 | Hardcoded in `cyrus_brain.py:67` | Centralize |
| COMPANION_PORT=8770 | Not in codebase yet | Define for future use |
| SERVER_PORT=8765 | Hardcoded in `cyrus_server.py:159` argparse default | Centralize |
| TTS_TIMEOUT=25.0 | Hardcoded in `cyrus_voice.py:174`, `main.py:1336` | Centralize |
| SOCKET_TIMEOUT=10 | Hardcoded in `cyrus_brain.py:1183,1190` | Centralize |
| HOOK_TIMEOUT=2 | Hardcoded in `cyrus_hook.py:21` | Centralize |
| VAD thresholds | Hardcoded in `cyrus_voice.py:66-76`, `main.py:83-97` | Centralize |
| Poll intervals | Hardcoded in `cyrus_brain.py:408-409,642` | Centralize |
| MAX_SPEECH_WORDS | 50 in `cyrus_brain.py:70`, 30 in `main.py:89` | Centralize (use 50) |
| `.env.example` documents all keys | Only has `ANTHROPIC_API_KEY=` | Expand |
| Imported in consumer files | N/A | Add imports to 4 files |

## Key Findings from Codebase Exploration

### Port assignments (across 4 files)

| Port | Purpose | Defined In | Used By |
|---|---|---|---|
| 8766 | Voice ↔ Brain TCP | `cyrus_brain.py:65`, `cyrus_voice.py:60` | Brain listens, Voice connects |
| 8767 | Hook → Brain TCP | `cyrus_brain.py:66`, `cyrus_hook.py:16` | Brain listens, Hook connects |
| 8769 | Mobile WebSocket | `cyrus_brain.py:67` | Brain listens |
| 8765 | Remote Brain WebSocket | `cyrus_server.py:159` | Server listens |
| 8770 | Companion (future) | Not in code | Defined in issue spec |

### Naming mismatch in cyrus_hook.py

`cyrus_hook.py:16` defines `BRAIN_PORT = 8767` — but 8767 is the **hook** port, not the brain port. After centralization this becomes `HOOK_PORT` imported from config, fixing the confusion.

### Host address asymmetry

- **Brain** binds on `"0.0.0.0"` (accept all interfaces) — `cyrus_brain.py:64`
- **Voice** and **Hook** connect to `"localhost"` — `cyrus_voice.py:59`, `cyrus_hook.py:15`
- Both patterns are correct (server vs. client) and should remain separate config values

### Issue spec vs. actual code values

| Constant | Issue Spec | Actual Code | Plan Uses |
|---|---|---|---|
| SPEECH_THRESHOLD | 0.6 | 0.5 (voice:66, main:83) | **0.5** (match code) |
| SILENCE_WINDOW | 1500 | 1000 (voice:70, main:87) | **1000** (match code) |
| MIN_SPEECH_DURATION | 500 | Does not exist | **SPEECH_WINDOW_MS=300** (closest equivalent) |
| MAX_SPEECH_WORDS | 200 | 50 (brain:70), 30 (main:89) | **50** (match brain) |
| CHAT_POLL env var | `CYRUS_CHAT_POLL_MS` | Value is 0.5 *seconds* | **`CYRUS_CHAT_POLL_SECS`** (fix unit) |
| PERMISSION_POLL env var | `CYRUS_PERMISSION_POLL_MS` | Value is 0.3 *seconds* | **`CYRUS_PERMISSION_POLL_SECS`** (fix unit) |

**Rationale**: defaults must match the currently-working code. Changing defaults would silently alter behavior across all services. The env vars allow users to tune to different values.

### dotenv consideration

`main.py` uses `python-dotenv` (`load_dotenv()`); the other four files do not. The config module should NOT call `load_dotenv()` itself — entry points that want `.env` support call it before importing the config. This keeps `cyrus_hook.py` dependency-free (critical: a crashing hook blocks Claude Code).

## Design Decisions

### D1. ConfigManager with class attributes + module-level aliases

The acceptance criteria require a `ConfigManager` class. Class attributes evaluated at import time (via `os.environ.get`) provide structured access (`ConfigManager.BRAIN_PORT`) while module-level aliases (`from cyrus2.cyrus_config import BRAIN_PORT`) preserve the existing constant-import pattern used throughout the codebase.

```python
# Both access patterns work:
from cyrus2.cyrus_config import BRAIN_PORT          # flat (matches existing code)
from cyrus2.cyrus_config import ConfigManager       # structured
```

### D2. Defaults match actual codebase values, not issue spec

Where the issue spec and codebase disagree (see table above), we use the codebase values. Changing defaults would be a behavior change, not a refactor. The env vars let users set whatever values they want.

### D3. Separate HOOK_TIMEOUT from SOCKET_TIMEOUT

The hook uses a 2-second timeout (`cyrus_hook.py:21`) while the brain uses 10-second timeouts for companion connections (`cyrus_brain.py:1183`). These serve different purposes and should be independently configurable.

### D4. Include VAD derived constants as computed properties

`SPEECH_RING`, `SILENCE_RING`, and `MAX_RECORD_FRAMES` are derived from the base VAD constants. They are computed at import time in the config module (matching current pattern in `cyrus_voice.py:73-75` and `main.py:94-96`) so consumers don't need to repeat the math.

### D5. COMPANION_PORT defined for forward compatibility

Port 8770 doesn't appear in the current codebase but is specified in the issue. Define it in config with the env var so it's ready when the companion feature lands.

### D6. main.py is not modified

`main.py` is the monolith slated for deprecation (Issue 006). Its hardcoded values are duplicates of what's in the service files. Modifying it adds risk for zero long-term value.

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC1 | `cyrus2/cyrus_config.py` created with ConfigManager class | `python3 -c "from cyrus2.cyrus_config import ConfigManager"` succeeds |
| AC2 | Ports: BRAIN=8766, HOOK=8767, MOBILE=8769, COMPANION=8770, SERVER=8765 | Assert each equals expected default |
| AC3 | Timeouts: TTS_TIMEOUT=25.0, SOCKET_TIMEOUT=10, HOOK_TIMEOUT=2 | Assert each equals expected default |
| AC4 | VAD: SPEECH_THRESHOLD=0.5, SILENCE_WINDOW_MS=1000, SPEECH_WINDOW_MS=300 | Assert each equals expected default |
| AC5 | All values read from env vars with fallback defaults | Set env var, re-import module, assert new value |
| AC6 | Imported in cyrus_brain.py, cyrus_voice.py, cyrus_hook.py, cyrus_server.py | `grep "from cyrus2.cyrus_config import" *.py` returns 4 files |
| AC7 | `.env.example` documents all configurable options | All `CYRUS_*` env var names from config appear in `.env.example` |

## Implementation Steps

### Step 1: Write verification script (RED)

**TDD: tests first.** Create `cyrus2/test_cyrus_config.py` that exercises all acceptance criteria. Expected to fail initially (module doesn't exist).

**File**: `cyrus2/test_cyrus_config.py`

```python
"""Verification script for cyrus_config module — all acceptance criteria."""

import importlib
import os
import sys

failures = []


def check(label, condition):
    if not condition:
        failures.append(label)
        print(f"  FAIL: {label}")
    else:
        print(f"  OK:   {label}")


# ── AC1: import succeeds ─────────────────────────────────────────────────────
print("=== AC1: import ConfigManager ===")
try:
    from cyrus2.cyrus_config import ConfigManager
    check("import ConfigManager", True)
except ImportError as e:
    check(f"import ConfigManager ({e})", False)
    print("\nCannot continue without the module. Exiting.")
    sys.exit(1)

from cyrus2 import cyrus_config

# ── AC2: port defaults ───────────────────────────────────────────────────────
print("\n=== AC2: port defaults ===")
check("BRAIN_PORT=8766", ConfigManager.BRAIN_PORT == 8766)
check("HOOK_PORT=8767", ConfigManager.HOOK_PORT == 8767)
check("MOBILE_PORT=8769", ConfigManager.MOBILE_PORT == 8769)
check("COMPANION_PORT=8770", ConfigManager.COMPANION_PORT == 8770)
check("SERVER_PORT=8765", ConfigManager.SERVER_PORT == 8765)

# Also verify module-level aliases
check("module BRAIN_PORT alias", cyrus_config.BRAIN_PORT == 8766)
check("module HOOK_PORT alias", cyrus_config.HOOK_PORT == 8767)

# ── AC3: timeout defaults ────────────────────────────────────────────────────
print("\n=== AC3: timeout defaults ===")
check("TTS_TIMEOUT=25.0", ConfigManager.TTS_TIMEOUT == 25.0)
check("SOCKET_TIMEOUT=10", ConfigManager.SOCKET_TIMEOUT == 10)
check("HOOK_TIMEOUT=2", ConfigManager.HOOK_TIMEOUT == 2)

# ── AC4: VAD defaults ────────────────────────────────────────────────────────
print("\n=== AC4: VAD and poll defaults ===")
check("SPEECH_THRESHOLD=0.5", ConfigManager.SPEECH_THRESHOLD == 0.5)
check("SILENCE_WINDOW_MS=1000", ConfigManager.SILENCE_WINDOW_MS == 1000)
check("SPEECH_WINDOW_MS=300", ConfigManager.SPEECH_WINDOW_MS == 300)
check("MAX_RECORD_MS=12000", ConfigManager.MAX_RECORD_MS == 12000)
check("SPEECH_RATIO=0.80", ConfigManager.SPEECH_RATIO == 0.80)
check("FRAME_MS=32", ConfigManager.FRAME_MS == 32)
check("FRAME_SIZE=512", ConfigManager.FRAME_SIZE == 512)
check("MAX_SPEECH_WORDS=50", ConfigManager.MAX_SPEECH_WORDS == 50)
check("CHAT_WATCHER_POLL_SECS=0.5", ConfigManager.CHAT_WATCHER_POLL_SECS == 0.5)
check("CHAT_WATCHER_STABLE_SECS=1.2", ConfigManager.CHAT_WATCHER_STABLE_SECS == 1.2)
check("PERMISSION_WATCHER_POLL_SECS=0.3", ConfigManager.PERMISSION_WATCHER_POLL_SECS == 0.3)

# ── AC4b: derived constants ──────────────────────────────────────────────────
print("\n=== AC4b: derived constants ===")
check("SPEECH_RING=9", ConfigManager.SPEECH_RING == 300 // 32)
check("SILENCE_RING=31", ConfigManager.SILENCE_RING == 1000 // 32)
check("MAX_RECORD_FRAMES=375", ConfigManager.MAX_RECORD_FRAMES == 12000 // 32)

# ── AC5: env var override ────────────────────────────────────────────────────
print("\n=== AC5: env var overrides ===")
os.environ["CYRUS_BRAIN_PORT"] = "9999"
os.environ["CYRUS_TTS_TIMEOUT"] = "30.0"
os.environ["CYRUS_SPEECH_THRESHOLD"] = "0.7"
importlib.reload(cyrus_config)
CM = cyrus_config.ConfigManager
check("BRAIN_PORT overridden to 9999", CM.BRAIN_PORT == 9999)
check("TTS_TIMEOUT overridden to 30.0", CM.TTS_TIMEOUT == 30.0)
check("SPEECH_THRESHOLD overridden to 0.7", CM.SPEECH_THRESHOLD == 0.7)
# Module-level aliases also update on reload
check("module alias BRAIN_PORT=9999", cyrus_config.BRAIN_PORT == 9999)

# Clean up
del os.environ["CYRUS_BRAIN_PORT"]
del os.environ["CYRUS_TTS_TIMEOUT"]
del os.environ["CYRUS_SPEECH_THRESHOLD"]

# ── AC5b: type correctness ───────────────────────────────────────────────────
print("\n=== AC5b: types are correct ===")
importlib.reload(cyrus_config)
CM = cyrus_config.ConfigManager
check("BRAIN_PORT is int", isinstance(CM.BRAIN_PORT, int))
check("TTS_TIMEOUT is float", isinstance(CM.TTS_TIMEOUT, float))
check("SPEECH_THRESHOLD is float", isinstance(CM.SPEECH_THRESHOLD, float))
check("SOCKET_TIMEOUT is int", isinstance(CM.SOCKET_TIMEOUT, int))
check("MAX_SPEECH_WORDS is int", isinstance(CM.MAX_SPEECH_WORDS, int))

# ── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
if failures:
    print(f"FAILED ({len(failures)}): {', '.join(failures)}")
    sys.exit(1)
else:
    print("All acceptance criteria passed.")
```

**Run** (will fail — module doesn't exist yet):

```bash
cd /home/daniel/Projects/barf/cyrus
python3 cyrus2/test_cyrus_config.py
```

### Step 2: Create `cyrus2/cyrus_config.py` (GREEN)

**File**: `cyrus2/cyrus_config.py`

```python
"""Centralized configuration for Cyrus.

All values read from environment variables with sensible defaults matching
the current codebase. Import individual constants or the ConfigManager class::

    from cyrus2.cyrus_config import BRAIN_PORT, HOOK_PORT
    from cyrus2.cyrus_config import ConfigManager

Entry points that want .env file support should call ``load_dotenv()``
before importing this module::

    from dotenv import load_dotenv
    load_dotenv()
    from cyrus2.cyrus_config import BRAIN_PORT
"""

import os


class ConfigManager:
    """Reads all Cyrus configuration from environment variables.

    Every attribute has a sensible default matching the current codebase.
    Override any value by setting the corresponding CYRUS_* env var.
    """

    # ── Ports ─────────────────────────────────────────────────────────────
    BRAIN_PORT     = int(os.environ.get("CYRUS_BRAIN_PORT", "8766"))
    HOOK_PORT      = int(os.environ.get("CYRUS_HOOK_PORT", "8767"))
    MOBILE_PORT    = int(os.environ.get("CYRUS_MOBILE_PORT", "8769"))
    COMPANION_PORT = int(os.environ.get("CYRUS_COMPANION_PORT", "8770"))
    SERVER_PORT    = int(os.environ.get("CYRUS_SERVER_PORT", "8765"))

    # ── Hosts ─────────────────────────────────────────────────────────────
    BRAIN_BIND_HOST    = os.environ.get("CYRUS_BRAIN_BIND_HOST", "0.0.0.0")
    BRAIN_CONNECT_HOST = os.environ.get("CYRUS_BRAIN_CONNECT_HOST", "localhost")

    # ── Timeouts ──────────────────────────────────────────────────────────
    TTS_TIMEOUT    = float(os.environ.get("CYRUS_TTS_TIMEOUT", "25.0"))
    SOCKET_TIMEOUT = int(os.environ.get("CYRUS_SOCKET_TIMEOUT", "10"))
    HOOK_TIMEOUT   = int(os.environ.get("CYRUS_HOOK_TIMEOUT", "2"))

    # ── VAD thresholds ────────────────────────────────────────────────────
    SPEECH_THRESHOLD  = float(os.environ.get("CYRUS_SPEECH_THRESHOLD", "0.5"))
    FRAME_MS          = int(os.environ.get("CYRUS_FRAME_MS", "32"))
    FRAME_SIZE        = int(os.environ.get("CYRUS_FRAME_SIZE", "512"))
    SPEECH_WINDOW_MS  = int(os.environ.get("CYRUS_SPEECH_WINDOW_MS", "300"))
    SILENCE_WINDOW_MS = int(os.environ.get("CYRUS_SILENCE_WINDOW_MS", "1000"))
    MAX_RECORD_MS     = int(os.environ.get("CYRUS_MAX_RECORD_MS", "12000"))
    SPEECH_RATIO      = float(os.environ.get("CYRUS_SPEECH_RATIO", "0.80"))

    # Derived — recomputed from base values
    SPEECH_RING       = SPEECH_WINDOW_MS  // FRAME_MS
    SILENCE_RING      = SILENCE_WINDOW_MS // FRAME_MS
    MAX_RECORD_FRAMES = MAX_RECORD_MS     // FRAME_MS

    # ── Poll intervals ────────────────────────────────────────────────────
    CHAT_WATCHER_POLL_SECS       = float(os.environ.get("CYRUS_CHAT_POLL_SECS", "0.5"))
    CHAT_WATCHER_STABLE_SECS     = float(os.environ.get("CYRUS_CHAT_STABLE_SECS", "1.2"))
    PERMISSION_WATCHER_POLL_SECS = float(os.environ.get("CYRUS_PERMISSION_POLL_SECS", "0.3"))

    # ── Speech ────────────────────────────────────────────────────────────
    MAX_SPEECH_WORDS = int(os.environ.get("CYRUS_MAX_SPEECH_WORDS", "50"))


# ── Module-level aliases (flat import style) ──────────────────────────────────

BRAIN_PORT     = ConfigManager.BRAIN_PORT
HOOK_PORT      = ConfigManager.HOOK_PORT
MOBILE_PORT    = ConfigManager.MOBILE_PORT
COMPANION_PORT = ConfigManager.COMPANION_PORT
SERVER_PORT    = ConfigManager.SERVER_PORT

BRAIN_BIND_HOST    = ConfigManager.BRAIN_BIND_HOST
BRAIN_CONNECT_HOST = ConfigManager.BRAIN_CONNECT_HOST

TTS_TIMEOUT    = ConfigManager.TTS_TIMEOUT
SOCKET_TIMEOUT = ConfigManager.SOCKET_TIMEOUT
HOOK_TIMEOUT   = ConfigManager.HOOK_TIMEOUT

SPEECH_THRESHOLD  = ConfigManager.SPEECH_THRESHOLD
FRAME_MS          = ConfigManager.FRAME_MS
FRAME_SIZE        = ConfigManager.FRAME_SIZE
SPEECH_WINDOW_MS  = ConfigManager.SPEECH_WINDOW_MS
SILENCE_WINDOW_MS = ConfigManager.SILENCE_WINDOW_MS
MAX_RECORD_MS     = ConfigManager.MAX_RECORD_MS
SPEECH_RATIO      = ConfigManager.SPEECH_RATIO
SPEECH_RING       = ConfigManager.SPEECH_RING
SILENCE_RING      = ConfigManager.SILENCE_RING
MAX_RECORD_FRAMES = ConfigManager.MAX_RECORD_FRAMES

CHAT_WATCHER_POLL_SECS       = ConfigManager.CHAT_WATCHER_POLL_SECS
CHAT_WATCHER_STABLE_SECS     = ConfigManager.CHAT_WATCHER_STABLE_SECS
PERMISSION_WATCHER_POLL_SECS = ConfigManager.PERMISSION_WATCHER_POLL_SECS

MAX_SPEECH_WORDS = ConfigManager.MAX_SPEECH_WORDS
```

### Step 3: Run verification script (GREEN)

```bash
cd /home/daniel/Projects/barf/cyrus
python3 cyrus2/test_cyrus_config.py
```

Expected: `All acceptance criteria passed.`

### Step 4: Replace constants in `cyrus_brain.py`

**Remove** the local constant definitions (lines 62–70):

```python
# BEFORE (cyrus_brain.py:62-70)
# ── Configuration ──────────────────
BRAIN_HOST       = "0.0.0.0"
BRAIN_PORT       = 8766
HOOK_PORT        = 8767
MOBILE_PORT      = 8769
VSCODE_TITLE     = "Visual Studio Code"
_CHAT_INPUT_HINT = "Message input"
MAX_SPEECH_WORDS = 50
```

**Replace with** imports from config:

```python
# ── Configuration (from centralized config) ───────────────────────────────────
from cyrus2.cyrus_config import (
    BRAIN_BIND_HOST as BRAIN_HOST,
    BRAIN_PORT,
    HOOK_PORT,
    MOBILE_PORT,
    MAX_SPEECH_WORDS,
    SOCKET_TIMEOUT,
    CHAT_WATCHER_POLL_SECS,
    CHAT_WATCHER_STABLE_SECS,
    PERMISSION_WATCHER_POLL_SECS,
)

VSCODE_TITLE     = "Visual Studio Code"
_CHAT_INPUT_HINT = "Message input"
```

**Also replace hardcoded values** deeper in the file:
- `cyrus_brain.py:408-409` — ChatWatcher `POLL_SECS = 0.5` and `STABLE_SECS = 1.2`: replace with config imports
- `cyrus_brain.py:642` — PermissionWatcher `POLL_SECS = 0.3`: replace with config import
- `cyrus_brain.py:1183,1190` — `s.settimeout(10)`: replace with `s.settimeout(SOCKET_TIMEOUT)`

**Verify**: run `python cyrus_brain.py --help` — should print help without import errors.

### Step 5: Replace constants in `cyrus_voice.py`

**Remove** local port and VAD definitions (lines 59-60, 66-76):

```python
# BEFORE (cyrus_voice.py:59-60)
BRAIN_HOST    = "localhost"
BRAIN_PORT    = 8766

# BEFORE (cyrus_voice.py:66-76)
SPEECH_THRESHOLD  = 0.5
FRAME_MS          = 32
FRAME_SIZE        = 512
SPEECH_WINDOW_MS  = 300
SILENCE_WINDOW_MS = 1000
MAX_RECORD_MS     = 12000

SPEECH_RING       = SPEECH_WINDOW_MS  // FRAME_MS
SILENCE_RING      = SILENCE_WINDOW_MS // FRAME_MS
MAX_RECORD_FRAMES = MAX_RECORD_MS     // FRAME_MS
SPEECH_RATIO      = 0.80
```

**Replace with** imports from config:

```python
from cyrus2.cyrus_config import (
    BRAIN_CONNECT_HOST as BRAIN_HOST,
    BRAIN_PORT,
    TTS_TIMEOUT,
    SPEECH_THRESHOLD,
    FRAME_MS,
    FRAME_SIZE,
    SPEECH_WINDOW_MS,
    SILENCE_WINDOW_MS,
    MAX_RECORD_MS,
    SPEECH_RING,
    SILENCE_RING,
    MAX_RECORD_FRAMES,
    SPEECH_RATIO,
)
```

**Also replace**: `cyrus_voice.py:174` — `timeout=25.0`: replace with `timeout=TTS_TIMEOUT`.

**Verify**: `python cyrus_voice.py --help` — prints help without errors.

### Step 6: Replace constants in `cyrus_hook.py`

**Remove** local definitions (lines 15-16):

```python
# BEFORE (cyrus_hook.py:15-16)
BRAIN_HOST = "localhost"
BRAIN_PORT = 8767
```

**Replace with** imports (note the name fix — was `BRAIN_PORT=8767`, now correctly `HOOK_PORT`):

```python
from cyrus2.cyrus_config import (
    BRAIN_CONNECT_HOST as BRAIN_HOST,
    HOOK_PORT as BRAIN_PORT,
    HOOK_TIMEOUT,
)
```

**Also replace**: `cyrus_hook.py:21` — `timeout=2`: replace with `timeout=HOOK_TIMEOUT`.

**Verify**: `echo '{}' | python cyrus_hook.py` — exits cleanly (no import errors, silent on empty payload).

### Step 7: Replace constants in `cyrus_server.py`

**Remove/replace** the argparse default (line 159):

```python
# BEFORE
parser.add_argument("--port", type=int, default=8765, ...)

# AFTER
from cyrus2.cyrus_config import SERVER_PORT
# ... later in main():
parser.add_argument("--port", type=int, default=SERVER_PORT,
                    help=f"Port to listen on (default: {SERVER_PORT})")
```

**Verify**: `python cyrus_server.py --help` — shows the port default.

### Step 8: Update `.env.example`

Replace the current single-line file with all configurable keys:

```env
# ── Cyrus Configuration ──────────────────────────────────────────────────────
# All values have sensible defaults. Only set what you need to change.
# See cyrus2/cyrus_config.py for the full list and default values.

# ── API Keys ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=

# ── Ports ────────────────────────────────────────────────────────────────────
# CYRUS_BRAIN_PORT=8766           # Voice ↔ Brain TCP
# CYRUS_HOOK_PORT=8767            # Claude Code hooks → Brain TCP
# CYRUS_MOBILE_PORT=8769          # Mobile WebSocket → Brain
# CYRUS_COMPANION_PORT=8770       # VS Code companion extension
# CYRUS_SERVER_PORT=8765          # Remote brain WebSocket

# ── Hosts ────────────────────────────────────────────────────────────────────
# CYRUS_BRAIN_BIND_HOST=0.0.0.0  # Brain server bind address
# CYRUS_BRAIN_CONNECT_HOST=localhost  # Voice/Hook → Brain connect address

# ── Timeouts ─────────────────────────────────────────────────────────────────
# CYRUS_TTS_TIMEOUT=25.0          # Max seconds for TTS generation
# CYRUS_SOCKET_TIMEOUT=10         # Companion extension socket timeout (s)
# CYRUS_HOOK_TIMEOUT=2            # Claude Code hook send timeout (s)

# ── VAD (Voice Activity Detection) ───────────────────────────────────────────
# CYRUS_SPEECH_THRESHOLD=0.5      # Silero probability threshold (0-1)
# CYRUS_FRAME_MS=32               # Silero frame duration (ms)
# CYRUS_FRAME_SIZE=512            # Audio frame size (samples)
# CYRUS_SPEECH_WINDOW_MS=300      # Speech detection window (ms)
# CYRUS_SILENCE_WINDOW_MS=1000    # Silence duration to end utterance (ms)
# CYRUS_MAX_RECORD_MS=12000       # Hard cap on recording duration (ms)
# CYRUS_SPEECH_RATIO=0.80         # Fraction of window that must be speech

# ── Poll Intervals ───────────────────────────────────────────────────────────
# CYRUS_CHAT_POLL_SECS=0.5        # Chat response check interval (s)
# CYRUS_CHAT_STABLE_SECS=1.2      # Wait for response stability (s)
# CYRUS_PERMISSION_POLL_SECS=0.3  # Permission dialog check interval (s)

# ── Speech ───────────────────────────────────────────────────────────────────
# CYRUS_MAX_SPEECH_WORDS=50       # Max words per spoken response
```

### Step 9: Verify — end-to-end

```bash
cd /home/daniel/Projects/barf/cyrus

# 1. Config module imports cleanly
python3 -c "from cyrus2.cyrus_config import ConfigManager; print('OK')"

# 2. All consumer files import cleanly
python3 -c "import cyrus_brain" 2>&1 | head -1     # may fail on Windows deps, but no ImportError for config
python3 -c "import cyrus_hook; print('OK')"
python3 -c "import cyrus_server; print('OK')"

# 3. Env var override works end-to-end
CYRUS_BRAIN_PORT=9000 python3 -c "from cyrus2.cyrus_config import BRAIN_PORT; assert BRAIN_PORT == 9000; print('Override OK')"

# 4. .env.example has all keys
python3 -c "
import re
with open('.env.example') as f:
    example = f.read()
from cyrus2.cyrus_config import ConfigManager
# Check a representative sample
for key in ['CYRUS_BRAIN_PORT', 'CYRUS_TTS_TIMEOUT', 'CYRUS_SPEECH_THRESHOLD', 'CYRUS_CHAT_POLL_SECS']:
    assert key in example, f'Missing: {key}'
print('.env.example complete')
"
```

### Step 10: Clean up verification script

Delete `cyrus2/test_cyrus_config.py` — the verification scaffold. The module is tested by the manual steps above and by any future pytest suite (Issue 018).

```bash
rm /home/daniel/Projects/barf/cyrus/cyrus2/test_cyrus_config.py
```

## Files Created/Modified

| File | Action | Purpose |
|---|---|---|
| `cyrus2/cyrus_config.py` | **Create** | Centralized config module |
| `cyrus_brain.py` | **Modify** | Import ports, timeouts, poll intervals from config |
| `cyrus_voice.py` | **Modify** | Import port, TTS timeout, VAD thresholds from config |
| `cyrus_hook.py` | **Modify** | Import hook port and timeout from config |
| `cyrus_server.py` | **Modify** | Import server port from config |
| `.env.example` | **Update** | Document all CYRUS_* env vars |
| `cyrus2/test_cyrus_config.py` | **Create then delete** | TDD verification scaffold |

## Risk Assessment

**Low risk.** One new file, four surgical constant-replacement edits, no logic changes.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Import path breaks for hook (different CWD) | Hook stops working | Low | Python sets `sys.path[0]` to script directory, so `cyrus2/` is always reachable. Verified in Step 9. |
| Env var typo changes port silently | Service binds wrong port | Low | Defaults match current code exactly — only explicit env vars change behavior |
| Module reload semantics in long-running processes | Stale config values | Very low | Config is read once at import time (same as current constants). No hot-reload needed. |
| main.py still has its own constants | Drift between config and monolith | Low | main.py is deprecated (Issue 006). Not modified here by design. |
| cyrus_brain.py/cyrus_voice.py fail to import (Windows-only deps) | Can't verify on Linux | Medium | Test config import independently; consumer file tests may skip on Linux (no UIA/pyautogui). Focus verification on `cyrus_hook.py` and `cyrus_server.py` which have no platform deps. |
