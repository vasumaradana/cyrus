# 16 — Logging System

## Context
Cyrus uses 218 bare `print()` calls across 6 files with ad-hoc `[Brain]`/`[Voice]`/`[Cyrus]` prefixes. No log levels, no filtering, no file output, no rotation. This makes debugging production issues (especially in Docker) difficult. Replace with Python's `logging` module.

## Design

### Logger per module
```python
import logging
log = logging.getLogger(__name__)
```

Each file gets its own logger, inheriting from the root `cyrus` logger. This preserves the existing `[Brain]`/`[Voice]` convention via logger names while adding levels.

### Log levels mapping

| Current pattern | New level | Examples |
|----------------|-----------|---------|
| `[!]` errors, `FATAL`, `except` messages | `ERROR` | UIA failures, socket errors, missing windows |
| `Cleared corrupted cache`, `falling back to` | `WARNING` | Fallback paths, retries, timeouts |
| `Connected`, `Ready`, `Listening`, `Paused/Resumed` | `INFO` | Lifecycle events, state changes |
| Routing decisions, command dispatch, session scan | `DEBUG` | Per-utterance flow, poll results |
| UIA tree dumps, raw JSON payloads | `DEBUG` (verbose) | Only with `-v` flag |

### Configuration

**`cyrus_log.py`** — single module, ~40 lines:

```python
import logging
import sys
import os

def setup_logging(name: str = "cyrus") -> logging.Logger:
    """Call once at startup in each entry point."""
    level_name = os.environ.get("CYRUS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = "[{name}] {levelname:.1s} {message}"
    if level <= logging.DEBUG:
        fmt = "{asctime} [{name}] {levelname:.1s} {message}"

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt, style="{", datefmt="%H:%M:%S"))

    root = logging.getLogger(name)
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False

    return root
```

**Usage at entry points:**
```python
# cyrus_brain.py
from cyrus_log import setup_logging
setup_logging("cyrus")
log = logging.getLogger("cyrus.brain")
```

```python
# cyrus_voice.py
from cyrus_log import setup_logging
setup_logging("cyrus")
log = logging.getLogger("cyrus.voice")
```

**Environment variable:** `CYRUS_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR` (default: `INFO`)

### Output format

**INFO (default):**
```
[cyrus.brain] I Listening for wake word...
[cyrus.brain] I Companion extension unavailable — falling back to UIA
[cyrus.voice] I Connected to brain.
[cyrus.voice] W TTS timed out
```

**DEBUG:**
```
14:32:01 [cyrus.brain] D Utterance received: "switch to backend"
14:32:01 [cyrus.brain] D Fast command matched: switch_project → backend
14:32:01 [cyrus.brain] I Switched to project: backend
14:32:02 [cyrus.brain] D Permission scan: no dialog found
```

### Docker integration
- Logs go to stderr → `docker logs` picks them up automatically
- `docker-compose.yml` can set `CYRUS_LOG_LEVEL: DEBUG` for troubleshooting
- No file rotation needed in containers (Docker handles log drivers)

---

## Migration approach

### Print-to-log conversion rules

| Print pattern | Replacement |
|--------------|-------------|
| `print("[Brain] Something happened")` | `log.info("Something happened")` |
| `print("[!] Error message")` | `log.error("Error message")` |
| `print(f"[Brain] {var}")` | `log.info("%s", var)` |
| `except Exception: pass` (silent) | `except Exception: log.debug("...", exc_info=True)` |
| `except Exception as e: print(e)` | `log.error("Context: %s", e)` |

### Per-file changes

| File | print count | Logger name |
|------|------------|-------------|
| `cyrus_brain.py` | 66 | `cyrus.brain` |
| `main.py` | 68 | `cyrus.main` |
| `cyrus_voice.py` | 32 | `cyrus.voice` |
| `cyrus_server.py` | 4 | `cyrus.server` |
| `cyrus_hook.py` | 0 | (no logging — must stay silent, never block Claude) |
| `probe_uia.py` | 19 | Keep `print()` — diagnostic tool, not production |
| `test_permission_scan.py` | 29 | Keep `print()` — diagnostic tool |

**Note:** `cyrus_hook.py` intentionally has no output. Adding logging there risks blocking Claude Code if stderr is captured. Leave it as-is.

---

## Files to create
- `cyrus_log.py` (~40 lines) — logging setup

## Files to modify
- `cyrus_brain.py` — replace 66 prints with log calls
- `cyrus_voice.py` — replace 32 prints with log calls
- `cyrus_server.py` — replace 4 prints with log calls
- `main.py` — replace 68 prints with log calls (if not deprecated)

## Verification
```bash
# Default — INFO level, clean output
python cyrus_brain.py

# Debug — verbose with timestamps
CYRUS_LOG_LEVEL=DEBUG python cyrus_brain.py

# Docker
docker compose up  # logs visible via docker logs
CYRUS_LOG_LEVEL=DEBUG docker compose up  # verbose
```
