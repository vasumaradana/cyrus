# Plan 038: Add Session State Persistence

## Summary

Create `cyrus2/cyrus_state.py` — a state persistence module that saves brain session state (aliases, pending response queues, active project, routing lock) to `~/.cyrus/state.json` on shutdown and restores it on startup. Uses atomic writes (write `.tmp` → rename) with restricted file permissions (0o600). Modify `cyrus_brain.py` to integrate state save/load into the asyncio lifecycle. Add `SessionManager` methods for state collection/application to keep encapsulation clean.

## Dependencies

None blocking. Follows the `cyrus2/` module pattern established by plan 027 (config module): new module lives in `cyrus2/`, consumer modifications target root-level `cyrus_brain.py`.

**Note on cyrus2/ vs. root**: The `cyrus2/` directory exists but is empty — all code lives at root level. Following plan 027's convention, the new state module goes in `cyrus2/` while `cyrus_brain.py` at root imports from it. `sys.path[0]` is set to the script's directory (project root), so `from cyrus2.cyrus_state import ...` works without path manipulation.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| State file at `~/.cyrus/state.json` | No state persistence anywhere | Create on first save via `save_state()` |
| Persist aliases | `SessionManager._aliases: dict[str, str]` — in-memory only | Collect via new `SessionManager.collect_state()` method |
| Persist pending queues | `ChatWatcher._pending_queue: list[str]` — per-instance, in-memory | Collect via new `SessionManager.collect_state()` method |
| Persist project mappings | Active project + lock state in module globals | Include in state dict |
| Atomic writes (.tmp → rename) | N/A | `os.replace()` in `save_state()` |
| File permissions 0600 | N/A | `os.chmod()` after rename |
| Save on shutdown (SIGTERM, Ctrl+C) | Only `KeyboardInterrupt` caught in `__main__` block | `try/finally` in `main()` + `add_signal_handler(SIGTERM)` on Unix |
| Load state on startup | No state loading | Load in `main()` after `session_mgr.start()` |
| Handle missing state file | N/A | Return `{}`, log info, start fresh |
| Handle corrupted state file | N/A | Catch `json.JSONDecodeError`, return `{}`, log warning |
| `CYRUS_STATE_FILE` env var | Does not exist | Read in `get_state_file()` |
| `.env.example` documents env var | Only has `ANTHROPIC_API_KEY=` | Add `CYRUS_STATE_FILE` entry |

## Key Findings from Codebase Exploration

### Session state structures (cyrus_brain.py)

**Three categories of state worth persisting:**

| State | Location | Type | Persistence Value |
|---|---|---|---|
| `SessionManager._aliases` | Line 1031 | `dict[str, str]` (alias → project name) | **High** — user-renamed aliases survive restart |
| `ChatWatcher._pending_queue` | Line 422 | `list[str]` per project | **Medium** — buffered responses accessible after restart |
| `_active_project` | Line 81 (module global) | `str` | **Low** — convenience; window tracker resets anyway |
| `_project_locked` | Line 87 (module global) | `bool` | **Low** — convenience; routing lock persists |

**State NOT persisted** (transient, rebuilt on startup):
- `_chat_watchers` / `_perm_watchers` — rebuilt by VS Code window scan in `session_mgr.start()`
- Auto-generated aliases — rebuilt by `_make_alias()` during `_add_session()`
- `_conversation_active`, `_tts_active_remote` — ephemeral voice state
- `_response_history` — bounded deque, low value across restarts

### Alias lifecycle

1. `SessionManager._add_session()` (line 1060) creates auto-generated aliases via `_make_alias(proj)` — converts `"barf-ts"` → `"barf ts"`
2. `rename_alias()` (line 1056) lets users override: pops old alias, adds new one
3. On restore: auto-generated aliases are recreated by `session_mgr.start()` before we apply saved state. Calling `_aliases.update(saved_aliases)` merges saved aliases over auto-generated ones, restoring user renames.
4. Stale aliases (for projects no longer open) are harmless — they resolve to nothing in `_resolve_project()`.

### Pending queue lifecycle

1. `ChatWatcher` queues responses when project is inactive (line 616: `self._pending_queue.append(text)`)
2. `flush_pending()` (line 431) speaks all queued responses when user switches to that project via `on_session_switch()`
3. **Interview answer**: "Load into state file but don't auto-replay (manual recovery)"
4. **Strategy**: on load, inject saved items into `_pending_queue`. The normal `on_session_switch()` → `flush_pending()` flow handles replay when user activates that session. This IS manual recovery — the user actively switches to trigger it.

### Shutdown flow (current, lines 1767-1773)

```python
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        print("\nCyrus Brain signing off.")
```

No signal handlers. `asyncio.run()` catches `KeyboardInterrupt` and cancels tasks. The `finally` block runs but has no access to `session_mgr` (local to `main()`).

### Platform constraint

`asyncio.add_signal_handler()` raises `NotImplementedError` on Windows (ProactorEventLoop). This codebase uses Windows-specific deps (comtypes, uiautomation, pygetwindow). The plan uses `try/finally` inside `main()` as the primary mechanism (works everywhere), with `add_signal_handler(SIGTERM)` as an enhancement for Unix/WSL.

## Design Decisions

### D1. Standalone module in `cyrus2/cyrus_state.py`

The persistence logic is pure I/O — no UIA, no asyncio, no threading. A standalone module is testable in isolation and follows the pattern established by plan 027 (config) and 009 (logging). Dependencies: `json`, `os`, `stat`, `time`, `pathlib` — all stdlib.

### D2. `SessionManager.collect_state()` and `.apply_state()` methods

Rather than a standalone function reaching into `session_mgr._chat_watchers` and `session_mgr._aliases`, encapsulate state collection/application as SessionManager methods. This keeps private attributes private, makes the interface clear, and follows OOP conventions.

```python
class SessionManager:
    def collect_state(self) -> dict:
        """Return aliases and per-project pending queues."""
        ...

    def apply_state(self, state: dict) -> None:
        """Merge saved aliases and inject pending queues."""
        ...
```

### D3. `try/finally` in `main()` as primary save mechanism

The `try/finally` block around the `async with ... serve_forever()` section guarantees state is saved on ANY exit path: Ctrl+C, SIGTERM, exceptions, or graceful shutdown. This is more reliable than signal handlers alone (which are platform-dependent).

`add_signal_handler(SIGTERM, loop.stop)` is added for Unix — it stops the loop, which triggers the `finally` cleanup. On Windows, it's wrapped in `try/except NotImplementedError`. `SIGINT` (Ctrl+C) is already handled by `asyncio.run()` which cancels tasks and triggers `finally`.

### D4. State version field for forward compatibility

State dict includes `"version": 1`. On load, unknown versions are rejected with a warning and `{}` is returned. This allows schema evolution without corrupting state.

### D5. `load_state()` returns `{}` (not `None`) on failure

Returning `{}` instead of `None` eliminates null-check boilerplate everywhere. Callers can safely do `state.get("aliases", {})` without checking for `None` first.

### D6. Pending queues injected but not auto-replayed (per interview Q2)

On load, saved pending items are injected into `ChatWatcher._pending_queue` for matching projects. They are NOT flushed immediately. The normal `on_session_switch() → flush_pending()` flow speaks them when the user switches to that project. This is "manual recovery" — the user triggers it by switching sessions. Items for projects not currently detected are logged and discarded.

### D7. Synchronous save function

`save_state()` is synchronous (blocking I/O). Justification: it writes <1 KB of JSON to local disk — sub-millisecond. Called from the shutdown path where async infrastructure may be tearing down.

## State File Schema

```json
{
  "version": 1,
  "timestamp": 1710300000.123,
  "aliases": {
    "barf ts": "barf-ts",
    "cyrus": "cyrus"
  },
  "pending_queues": {
    "barf-ts": ["Response text waiting to be spoken"]
  },
  "active_project": "barf-ts",
  "project_locked": true
}
```

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Test(s) |
|---|---|---|
| AC1 | State saved to `~/.cyrus/state.json` on shutdown | `test_save_creates_file`, verify `try/finally` in `main()` calls save |
| AC2 | State includes aliases, pending queues, project mappings | `test_collect_includes_aliases`, `test_collect_includes_pending_queues`, `test_make_state_dict_fields` |
| AC3 | Atomic writes (.tmp → rename) | `test_save_uses_tmp_then_renames`, `test_save_no_leftover_tmp` |
| AC4 | State loaded from file at startup | `test_load_valid_state_roundtrip`, `test_apply_restores_aliases` |
| AC5 | Gracefully handles missing state file | `test_load_missing_file_returns_empty` |
| AC5b | Gracefully handles corrupted state file | `test_load_corrupted_json_returns_empty`, `test_load_wrong_version_returns_empty` |
| AC6 | File permissions restricted (0600) | `test_save_sets_permissions_0600` |
| AC7 | Configurable via `CYRUS_STATE_FILE` env var | `test_get_state_file_env_override`, `test_get_state_file_default` |

## Implementation Steps

### Step 1: Write verification script (RED)

**TDD: tests first.** Create `cyrus2/test_cyrus_state.py` — a standalone verification script (no pytest dependency) that exercises all acceptance criteria. Expected to fail initially (module doesn't exist).

**File**: `cyrus2/test_cyrus_state.py`

```python
"""Verification script for cyrus_state module — all acceptance criteria."""

import importlib
import json
import os
import sys
import stat
import tempfile
from pathlib import Path

failures = []


def check(label, condition):
    if not condition:
        failures.append(label)
        print(f"  FAIL: {label}")
    else:
        print(f"  OK:   {label}")


# ── AC-import: module imports ────────────────────────────────────────────────
print("=== AC-import: import state module ===")
try:
    from cyrus2.cyrus_state import get_state_file, save_state, load_state, make_state_dict
    check("import state functions", True)
except ImportError as e:
    check(f"import state functions ({e})", False)
    print("\nCannot continue without the module. Exiting.")
    sys.exit(1)


# Use a temporary directory for all tests
with tempfile.TemporaryDirectory() as tmpdir:
    test_state_file = Path(tmpdir) / "state.json"

    # ── AC7: env var override ────────────────────────────────────────────────
    print("\n=== AC7: CYRUS_STATE_FILE env var ===")
    os.environ["CYRUS_STATE_FILE"] = str(test_state_file)
    importlib.reload(sys.modules["cyrus2.cyrus_state"])
    from cyrus2.cyrus_state import get_state_file, save_state, load_state, make_state_dict

    check("get_state_file returns custom path", get_state_file() == test_state_file)

    # ── AC5: missing file → empty dict ───────────────────────────────────────
    print("\n=== AC5: missing file ===")
    check("load missing file returns {}", load_state() == {})

    # ── AC2 + AC3: save state with all fields, atomic write ──────────────────
    print("\n=== AC2 + AC3: save state ===")
    test_data = make_state_dict(
        aliases={"barf ts": "barf-ts", "my proj": "my-project"},
        pending_queues={"barf-ts": ["Hello", "World"]},
        active_project="barf-ts",
        project_locked=True,
    )
    save_state(test_data)
    check("state file created", test_state_file.exists())
    check("tmp file cleaned up", not test_state_file.with_suffix(".tmp").exists())

    # Verify JSON contents
    with open(test_state_file) as f:
        saved = json.load(f)
    check("version field present", saved.get("version") == 1)
    check("timestamp is float", isinstance(saved.get("timestamp"), float))
    check("aliases saved", saved.get("aliases") == {"barf ts": "barf-ts", "my proj": "my-project"})
    check("pending_queues saved", saved.get("pending_queues") == {"barf-ts": ["Hello", "World"]})
    check("active_project saved", saved.get("active_project") == "barf-ts")
    check("project_locked saved", saved.get("project_locked") is True)

    # ── AC6: file permissions ────────────────────────────────────────────────
    print("\n=== AC6: file permissions ===")
    mode = stat.S_IMODE(test_state_file.stat().st_mode)
    check("permissions are 0600", mode == 0o600)

    # ── AC4: load state roundtrip ────────────────────────────────────────────
    print("\n=== AC4: load state ===")
    loaded = load_state()
    check("loaded version == 1", loaded.get("version") == 1)
    check("loaded aliases match", loaded.get("aliases") == test_data["aliases"])
    check("loaded pending_queues match", loaded.get("pending_queues") == test_data["pending_queues"])
    check("loaded active_project match", loaded.get("active_project") == "barf-ts")
    check("loaded project_locked match", loaded.get("project_locked") is True)

    # ── AC5b: corrupted file ─────────────────────────────────────────────────
    print("\n=== AC5b: corrupted file ===")
    test_state_file.write_text("not valid json {{{")
    loaded = load_state()
    check("corrupted file returns {}", loaded == {})

    # ── AC5b: unsupported version ────────────────────────────────────────────
    print("\n=== AC5b: unsupported version ===")
    test_state_file.write_text(json.dumps({"version": 999}))
    loaded = load_state()
    check("unsupported version returns {}", loaded == {})

    # Clean up env
    del os.environ["CYRUS_STATE_FILE"]


# ── Default path test ────────────────────────────────────────────────────────
print("\n=== Default path ===")
importlib.reload(sys.modules["cyrus2.cyrus_state"])
from cyrus2.cyrus_state import get_state_file
default = get_state_file()
check("default path ends with .cyrus/state.json",
      str(default).endswith(os.path.join(".cyrus", "state.json")))
check("default path is under home",
      str(default).startswith(str(Path.home())))


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
python3 cyrus2/test_cyrus_state.py
```

### Step 2: Ensure `cyrus2/__init__.py` exists

```bash
mkdir -p /home/daniel/Projects/barf/cyrus/cyrus2
touch /home/daniel/Projects/barf/cyrus/cyrus2/__init__.py
```

If this file already exists from plan 027, this step is a no-op.

### Step 3: Create `cyrus2/cyrus_state.py` (GREEN)

**File**: `cyrus2/cyrus_state.py`

```python
"""Session state persistence for Cyrus Brain.

Saves and restores brain session state (aliases, pending queues, active
project, routing lock) to a JSON file. Uses atomic writes to prevent
corruption.

Default state file: ~/.cyrus/state.json
Override with: CYRUS_STATE_FILE env var

Usage::

    from cyrus2.cyrus_state import save_state, load_state, make_state_dict

    # Save
    state = make_state_dict(aliases={...}, pending_queues={...}, ...)
    save_state(state)

    # Load
    state = load_state()  # returns {} if missing or corrupted
"""

import json
import os
import stat
import time
from pathlib import Path

_STATE_VERSION = 1


def get_state_file() -> Path:
    """Return the path to the state file.

    Reads CYRUS_STATE_FILE env var, falls back to ~/.cyrus/state.json.
    Creates parent directory if needed.
    """
    custom = os.environ.get("CYRUS_STATE_FILE")
    if custom:
        p = Path(custom)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    default = Path.home() / ".cyrus" / "state.json"
    default.parent.mkdir(parents=True, exist_ok=True)
    return default


def save_state(state: dict) -> None:
    """Save state dict to disk with atomic write and restricted permissions.

    Writes to a .tmp file first, then renames (atomic on POSIX and NTFS).
    Sets file permissions to 0600 (owner read/write only).
    """
    state_file = get_state_file()
    tmp_file = state_file.with_suffix(".tmp")

    try:
        with open(tmp_file, "w") as f:
            json.dump(state, f, indent=2)

        # Atomic rename — overwrites existing file
        os.replace(str(tmp_file), str(state_file))

        # Restrict permissions (Unix; silently ignored on Windows)
        try:
            os.chmod(str(state_file), stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        except OSError:
            pass

        print(f"[State] Saved to {state_file}")
    except Exception as e:
        print(f"[State] Failed to save: {e}")
        # Clean up tmp file if rename failed
        try:
            tmp_file.unlink(missing_ok=True)
        except OSError:
            pass


def load_state() -> dict:
    """Load state from disk. Returns empty dict on any error.

    Handles: missing file, corrupted JSON, unsupported version.
    """
    state_file = get_state_file()

    if not state_file.exists():
        print("[State] No state file found; starting fresh")
        return {}

    try:
        with open(state_file) as f:
            state = json.load(f)
    except json.JSONDecodeError:
        print(f"[State] Corrupted state file ({state_file}), starting fresh")
        return {}
    except Exception as e:
        print(f"[State] Failed to load ({e}), starting fresh")
        return {}

    version = state.get("version", 0)
    if version != _STATE_VERSION:
        print(f"[State] Unsupported state version {version}, starting fresh")
        return {}

    ts = state.get("timestamp")
    if ts:
        age_hrs = (time.time() - ts) / 3600
        print(f"[State] Loaded state from {age_hrs:.1f}h ago")

    return state


def make_state_dict(
    *,
    aliases: dict[str, str],
    pending_queues: dict[str, list[str]],
    active_project: str,
    project_locked: bool,
) -> dict:
    """Build a state dict with version and timestamp."""
    return {
        "version": _STATE_VERSION,
        "timestamp": time.time(),
        "aliases": aliases,
        "pending_queues": pending_queues,
        "active_project": active_project,
        "project_locked": project_locked,
    }
```

**Run verification** (should pass):

```bash
cd /home/daniel/Projects/barf/cyrus
python3 cyrus2/test_cyrus_state.py
```

Expected: `All acceptance criteria passed.`

### Step 4: Add state methods to `SessionManager` in `cyrus_brain.py`

Add two methods to the `SessionManager` class for collecting and applying state, keeping `_chat_watchers` and `_aliases` encapsulated.

**Add after the existing `rename_alias` method (after line 1058):**

```python
    def collect_state(self) -> dict:
        """Collect session state for persistence."""
        aliases = dict(self._aliases)
        pending: dict[str, list[str]] = {}
        for proj, cw in self._chat_watchers.items():
            if cw._pending_queue:
                pending[proj] = list(cw._pending_queue)
        return {"aliases": aliases, "pending_queues": pending}

    def apply_state(self, state: dict) -> None:
        """Restore session state from persistence. Call after start().

        Aliases are merged over auto-detected ones (user renames survive).
        Pending queues are injected but NOT auto-replayed — the normal
        on_session_switch() → flush_pending() flow handles replay when
        the user switches to that project.
        """
        # Merge saved aliases over auto-detected ones
        aliases = state.get("aliases", {})
        if aliases:
            self._aliases.update(aliases)
            print(f"[State] Restored {len(aliases)} alias(es)")

        # Inject pending queues (don't auto-replay — per design)
        pending = state.get("pending_queues", {})
        for proj, items in pending.items():
            cw = self._chat_watchers.get(proj)
            if cw and items:
                cw._pending_queue.extend(items)
                print(f"[State] Loaded {len(items)} pending response(s) for {proj}")
            elif items:
                print(f"[State] Skipped {len(items)} pending response(s) "
                      f"for {proj} (session not detected)")
```

### Step 5: Integrate state save/load into `main()` in `cyrus_brain.py`

**5a. Add `import signal` to the imports section (top of file, around line 25):**

```python
import signal
```

**5b. Add state loading after `session_mgr.start()` (after line 1710), before the initial active project selection (lines 1713-1716):**

```python
    # Load persisted state
    from cyrus2.cyrus_state import load_state, save_state, make_state_dict
    saved_state = load_state()
    if saved_state:
        session_mgr.apply_state(saved_state)
        # Restore active project if still detected
        detected = {p for p, _ in (first or [])}
        saved_active = saved_state.get("active_project", "")
        if saved_active and saved_active in detected:
            with _active_project_lock:
                _active_project = saved_active
            if saved_state.get("project_locked", False):
                with _project_locked_lock:
                    _project_locked = True
            print(f"[State] Restored active project: {saved_active}")
```

**5c. Add signal handler for SIGTERM after the loop is available (before server setup):**

```python
    # Register SIGTERM handler (Unix) — stops loop, triggers finally cleanup
    try:
        loop.add_signal_handler(signal.SIGTERM, loop.stop)
    except NotImplementedError:
        pass  # Windows — Ctrl+C handled via asyncio.run() KeyboardInterrupt
```

**5d. Wrap the `async with` server block in `try/finally` (replace lines 1759-1764):**

```python
    try:
        async with voice_server, hook_server:
            await asyncio.gather(
                voice_server.serve_forever(),
                hook_server.serve_forever(),
                mobile_server.wait_closed(),
            )
    finally:
        # Save state on any exit (Ctrl+C, SIGTERM, exception)
        try:
            with _active_project_lock:
                active = _active_project
            with _project_locked_lock:
                locked = _project_locked
            sm_state = session_mgr.collect_state()
            state_dict = make_state_dict(
                aliases=sm_state["aliases"],
                pending_queues=sm_state["pending_queues"],
                active_project=active,
                project_locked=locked,
            )
            save_state(state_dict)
        except Exception as e:
            print(f"[Brain] Failed to save state on shutdown: {e}")
```

### Step 6: Update `.env.example`

Append to the existing file:

```env
# ── Session State ───────────────────────────────────────────────────────────
# Persistence file for brain session state (aliases, pending queues).
# Leave blank to use default ~/.cyrus/state.json
# CYRUS_STATE_FILE=
```

### Step 7: Run verification (GREEN)

```bash
cd /home/daniel/Projects/barf/cyrus
python3 cyrus2/test_cyrus_state.py
```

Expected: `All acceptance criteria passed.`

### Step 8: Manual smoke test

```bash
cd /home/daniel/Projects/barf/cyrus

# 1. State module imports cleanly
python3 -c "from cyrus2.cyrus_state import save_state, load_state, make_state_dict; print('OK')"

# 2. Env var override works
CYRUS_STATE_FILE=/tmp/cyrus-test-state.json python3 -c "
from cyrus2.cyrus_state import get_state_file
assert str(get_state_file()) == '/tmp/cyrus-test-state.json'
print('Env override OK')
"

# 3. Round-trip test
python3 -c "
import os, tempfile
os.environ['CYRUS_STATE_FILE'] = tempfile.mktemp(suffix='.json')
from cyrus2.cyrus_state import save_state, load_state, make_state_dict
sd = make_state_dict(
    aliases={'test': 'proj'},
    pending_queues={'proj': ['hello']},
    active_project='proj',
    project_locked=True,
)
save_state(sd)
loaded = load_state()
assert loaded['aliases'] == {'test': 'proj'}
assert loaded['pending_queues'] == {'proj': ['hello']}
assert loaded['active_project'] == 'proj'
assert loaded['project_locked'] is True
print('Round-trip OK')
os.unlink(os.environ['CYRUS_STATE_FILE'])
"
```

### Step 9: Delete verification scaffold

```bash
rm /home/daniel/Projects/barf/cyrus/cyrus2/test_cyrus_state.py
```

The module is verified by the manual steps and verification script. A proper pytest suite is planned in Issue 018.

## Files Created/Modified

| File | Action | Purpose |
|---|---|---|
| `cyrus2/__init__.py` | **Create** (if missing) | Make `cyrus2/` a Python package |
| `cyrus2/cyrus_state.py` | **Create** | State persistence module (get/save/load/make_state_dict) |
| `cyrus_brain.py` | **Modify** | Add `SessionManager.collect_state()` and `.apply_state()` methods; add state load at startup and save at shutdown; add SIGTERM signal handler |
| `.env.example` | **Update** | Document `CYRUS_STATE_FILE` env var |
| `cyrus2/test_cyrus_state.py` | **Create then delete** | TDD verification scaffold |

## Risk Assessment

**Low risk.** One new module, surgical additions to `cyrus_brain.py`, no changes to existing logic flow.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| `save_state()` throws during shutdown | State not saved; no data loss (best-effort) | Low | Wrapped in `try/except` in `main()` finally block |
| Stale aliases for removed projects | `_resolve_project()` false match | Very low | Stale aliases resolve to projects not in `_chat_watchers`; commands handle "no session matching" gracefully |
| `os.replace()` not atomic on network drives | Corrupted state file | Very low | `~/.cyrus/` is always local; `load_state()` handles corruption gracefully |
| `add_signal_handler()` fails on Windows | SIGTERM not caught | Expected | `try/except NotImplementedError`; `try/finally` is the primary mechanism |
| Pending queue items stale after long downtime | Confusing TTS on replay | Low | User triggers replay by switching to project (manual); can inspect `state.json` first |
| `cyrus2/__init__.py` conflict with plan 027 | File already exists | Likely | Check before creating; harmless if exists |
| State file grows unbounded | Disk usage | Very low | State is <1 KB (aliases + short text queues); bounded by `deque(maxlen=10)` on response history |
