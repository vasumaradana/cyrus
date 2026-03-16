# Plan 007: Break up `_execute_cyrus_command` into dispatch table

## Goal

Refactor `_execute_cyrus_command()` from a 69-line if/elif chain (6 command branches) into a dispatch table mapping command type strings to small, testable handler functions. Each handler becomes independently testable, extensible, and has cyclomatic complexity < 5.

## Prerequisites

- **Issue 005** (Extract shared code into cyrus_common.py) is listed as a blocker but is still PLANNED.
- **Issue 006** (Deprecate main.py) is listed as a blocker but is still PLANNED.
- **Neither blocks this work.** Design decision D1 keeps all handlers in `cyrus_brain.py` where the globals live. Every function referenced by handlers (`_resolve_project`, `_send`, `SessionManager`) already exists in `cyrus_brain.py`. The `cyrus2/` directory is empty and `cyrus_common.py` does not exist — this plan operates entirely on the root-level `cyrus_brain.py` file as it stands today.
- If 005/006 later move functions to `cyrus_common.py`, the handlers' internal calls would change from local to imported — a trivial follow-up, not a blocker.

## Key Findings from Gap Analysis

### Path discrepancy

The issue file references `cyrus2/` paths but the actual source files live at the project root (`/home/daniel/Projects/barf/cyrus/`). The `cyrus2/` directory is empty. This plan uses root-level paths matching the actual codebase, consistent with plans 005 and 006.

### Actual function size

The issue description says "678–776 line monolith" but that appears to be the original pre-refactor line range (331–1107) which includes ChatWatcher, PermissionWatcher, and SessionManager. The actual `_execute_cyrus_command()` in `cyrus_brain.py` is ~69 lines (lines 331–399). After Issue 005 extracts classes, the function remains the same size. The refactor is still valuable for testability, extensibility, error handling, and complexity reduction.

### Command types identified

The function handles 6 command types, all dispatched from `_fast_command()` regex parsing:

| Command Type | Lines | CC | Description | Globals accessed |
|---|---|---|---|---|
| `switch_project` | 335–347 | 3 | Lock routing to a named project | `_active_project`, `_project_locked` (write) |
| `unlock` | 349–353 | 1 | Release project lock | `_project_locked` (write) |
| `which_project` | 355–362 | 1 | Report active project + lock status | `_active_project`, `_project_locked` (read) |
| `last_message` | 364–375 | 2 | Replay last response via TTS | `_active_project` (read), `_speak_queue` (write) |
| `rename_session` | 377–390 | 3 | Rename a session alias | `_active_project` (read) |
| `pause` | 392–395 | 1 | Delegate pause toggle to voice service | none (sends via `_send`) |

**Tail behavior** (line 397–398): After the if/elif, `if spoken: enqueue_speech(spoken)`. The `last_message` and `pause` handlers `return` early to skip this. All others fall through to the tail.

### Module globals the handlers touch

All handlers live in the same module as the globals. No cross-module access needed:

- `_active_project` + `_active_project_lock` — read/write by switch, which, last_message, rename
- `_project_locked` + `_project_locked_lock` — read/write by switch, unlock, which
- `_speak_queue` — enqueue by last_message (and by the tail of _execute_cyrus_command)
- `_send()` — async send to voice service, used by pause

### Call site

Single call site at line 1521:
```python
_execute_cyrus_command(ctype, decision.get("command", {}), spoken, session_mgr, loop)
```
No return value is used. After the call, `_conversation_active` is set based on whether `spoken` ends with `?`.

### Test infrastructure

No pytest framework exists yet (Issue 018). No `requirements-dev.txt` (Issue 003). The issue's acceptance criterion "Unit tests added for each handler (Issue 009)" defers test creation to a later issue. This plan makes handlers testable but does not create the test file — that belongs to the test suite sprint.

## Design Decisions

### D1. Handlers live in cyrus_brain.py, not cyrus_common.py

Every handler accesses brain-specific module globals (`_active_project`, `_project_locked`, `_speak_queue`, `_send`). Moving them to `cyrus_common.py` would require injecting all this state via callbacks — the same pattern Issue 005 used for classes, but with diminishing returns for 5–15 line functions. Handlers stay in `cyrus_brain.py` where the globals live.

### D2. Uniform handler signature with return value

All handlers share the same signature:
```python
def _handle_xxx(cmd: dict, spoken: str, session_mgr: SessionManager,
                loop: asyncio.AbstractEventLoop) -> str:
```

**Return value**: the `spoken` text to enqueue for TTS. Returning `""` means the handler already handled speech (or doesn't need any). This replaces the current pattern of some branches doing `return` early to skip the tail TTS enqueue.

Why not a `NamedTuple` with `(spoken, handled_speech)` fields? The extra type adds complexity for no gain — `""` is a clear "nothing to speak" signal, and handlers that enqueue speech themselves (like `last_message`) simply return `""`.

### D3. Logging added to handlers, prints kept for now

The issue explicitly requires `logging.debug()`, `logging.info()`, `logging.exception()` in handlers. Issue 010 ("Replace prints in cyrus_brain") handles the broader print-to-logging conversion. For this issue:

- **New handler functions**: use `logging` only (no print)
- **Existing code outside handlers**: prints untouched (Issue 010 scope)
- `import logging` + `logger = logging.getLogger(__name__)` added near top of file

### D4. Error handling in dispatcher, not in each handler

A single try/except in the dispatcher wraps each handler call. This is cleaner than duplicating try/except in every 5–15 line handler. The exception is logged with `logger.exception()` which includes the full traceback.

### D5. No state object extraction

The issue's step 5 suggests extracting a "parameter state object" for handlers. This is over-engineering for functions that are 5–15 lines and live in the same module as the globals. The globals are accessed via locks (already thread-safe). For testing, `unittest.mock.patch` / pytest monkeypatch can mock the globals directly. A state object adds indirection without improving safety or testability at this scale.

If a future issue moves handlers out of cyrus_brain.py (e.g., into a `commands.py` module), a state object would then be justified. For now, YAGNI.

### D6. Type annotation on dispatch table

```python
CommandHandler = Callable[[dict, str, SessionManager, asyncio.AbstractEventLoop], str]
_COMMAND_HANDLERS: dict[str, CommandHandler] = { ... }
```

This makes the contract explicit and catches signature mismatches during type checking.

## Implementation Steps

### Step 1: Add logging import and type alias

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

Add near the top of the file, after existing imports:
```python
import logging
from typing import Callable

logger = logging.getLogger(__name__)
```

Check if `logging` is already imported (it may have been added by Issue 005 or 006). If so, only add the `logger` line.

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 2: Create handler functions

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

Add these functions immediately before the current `_execute_cyrus_command()` definition (before line 331). Each handler follows the uniform signature from D2.

```python
# ── Command handlers ──────────────────────────────────────────────────────────

def _handle_switch_project(cmd: dict, spoken: str, session_mgr: "SessionManager",
                           loop: asyncio.AbstractEventLoop) -> str:
    """Lock routing to a named project."""
    global _active_project, _project_locked
    target = _resolve_project(cmd.get("project", ""), session_mgr.aliases)
    if target:
        with _active_project_lock:
            _active_project = target
        with _project_locked_lock:
            _project_locked = True
        session_mgr.on_session_switch(target, loop)
        spoken = spoken or f"Switched to {target}. Routing locked."
        logger.info("Switch project: %s", spoken)
    else:
        spoken = f"No session matching '{cmd.get('project', '')}' found."
        logger.info("Switch project failed: %s", spoken)
    return spoken


def _handle_unlock(cmd: dict, spoken: str, session_mgr: "SessionManager",
                   loop: asyncio.AbstractEventLoop) -> str:
    """Release project lock, return to auto-follow mode."""
    global _project_locked
    with _project_locked_lock:
        _project_locked = False
    spoken = spoken or "Following window focus."
    logger.info("Routing unlocked.")
    return spoken


def _handle_which_project(cmd: dict, spoken: str, session_mgr: "SessionManager",
                          loop: asyncio.AbstractEventLoop) -> str:
    """Report current active project and lock status."""
    with _active_project_lock:
        proj_name = _active_project
    with _project_locked_lock:
        locked = _project_locked
    status = "locked" if locked else "following focus"
    spoken = spoken or f"Active project: {proj_name or 'none'}, {status}."
    logger.info("Which project: %s", spoken)
    return spoken


def _handle_last_message(cmd: dict, spoken: str, session_mgr: "SessionManager",
                         loop: asyncio.AbstractEventLoop) -> str:
    """Replay the last response in the active session."""
    with _active_project_lock:
        proj_name = _active_project
    resp = session_mgr.last_response(proj_name)
    if resp:
        asyncio.run_coroutine_threadsafe(
            _speak_queue.put((proj_name, resp)), loop
        )
        logger.info("Replaying last message for %s", proj_name or "active session")
        return ""  # speech already enqueued
    spoken = spoken or f"No recorded response for {proj_name or 'this session'}."
    logger.info("Last message: %s", spoken)
    return spoken


def _handle_rename_session(cmd: dict, spoken: str, session_mgr: "SessionManager",
                           loop: asyncio.AbstractEventLoop) -> str:
    """Rename a session alias."""
    new_name = cmd.get("new", "").strip()
    old_hint = cmd.get("old", "").strip()
    with _active_project_lock:
        active = _active_project
    proj = _resolve_project(old_hint, session_mgr.aliases) if old_hint else active
    if proj and new_name:
        old_alias = next((a for a, p in session_mgr.aliases.items() if p == proj), proj)
        session_mgr.rename_alias(old_alias, new_name, proj)
        spoken = spoken or f"Renamed to '{new_name}'."
        logger.info("%s -> alias '%s'", proj, new_name)
    else:
        spoken = spoken or "Could not find that session to rename."
        logger.info("Rename failed: %s", spoken)
    return spoken


def _handle_pause(cmd: dict, spoken: str, session_mgr: "SessionManager",
                  loop: asyncio.AbstractEventLoop) -> str:
    """Toggle listening pause state — delegates to voice service."""
    asyncio.run_coroutine_threadsafe(_send({"type": "pause"}), loop)
    logger.debug("Pause command sent to voice service")
    return ""  # voice service handles the response
```

**Key behavioral notes**:
- `_handle_last_message` returns `""` when it enqueues speech directly (replacing the old `return` that skipped the tail)
- `_handle_pause` returns `""` because it delegates to voice (replacing the old `return`)
- All other handlers return `spoken` text for the dispatcher to enqueue

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 3: Create dispatch table

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

Add immediately after the handler functions, before `_execute_cyrus_command()`:

```python
CommandHandler = Callable[[dict, str, "SessionManager", asyncio.AbstractEventLoop], str]

_COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "switch_project": _handle_switch_project,
    "unlock":         _handle_unlock,
    "which_project":  _handle_which_project,
    "last_message":   _handle_last_message,
    "rename_session": _handle_rename_session,
    "pause":          _handle_pause,
}
```

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 4: Refactor `_execute_cyrus_command` to use dispatch table

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

Replace the entire function body (lines 331–398) with:

```python
def _execute_cyrus_command(ctype: str, cmd: dict, spoken: str,
                            session_mgr: "SessionManager",
                            loop: asyncio.AbstractEventLoop) -> None:
    """Execute a Cyrus meta-command via dispatch table."""
    handler = _COMMAND_HANDLERS.get(ctype)
    if handler is None:
        logger.warning("Unknown command type: %s", ctype)
        return

    logger.debug("Executing command: %s", ctype)
    try:
        result_spoken = handler(cmd, spoken, session_mgr, loop)
    except Exception:
        logger.exception("Error executing command '%s'", ctype)
        return

    if result_spoken:
        asyncio.run_coroutine_threadsafe(
            _speak_queue.put(("", result_spoken)), loop
        )
```

**What changed**:
- if/elif chain → single `_COMMAND_HANDLERS.get(ctype)` lookup
- `global _active_project, _project_locked` removed (globals mutated by handlers, not this function)
- Unknown commands logged instead of silently ignored
- All handler calls wrapped in try/except with `logger.exception()`
- Tail TTS enqueue only fires when `result_spoken` is truthy

**Call site** (line 1521): unchanged — same signature, same void return.

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 5: Lint and format

```bash
cd /home/daniel/Projects/barf/cyrus
ruff check cyrus_brain.py
ruff format cyrus_brain.py
```

Fix any violations. Expected issues:
- `Callable` may need `from __future__ import annotations` or `from typing import Callable`
- Unused `cmd` parameter in `_handle_unlock`, `_handle_which_project`, `_handle_pause` — add `# noqa: ARG001` or prefix with `_` if ruff complains. However, keeping a uniform signature is intentional (D2).

If ruff is not yet installed (Issue 001 sets it up), use:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 6: Verify behavior preservation

Test manually by verifying:
1. Each command type in `_COMMAND_HANDLERS` matches the original if/elif branches
2. The return-early behavior of `last_message` and `pause` is preserved via `return ""`
3. The tail TTS enqueue only fires for non-empty spoken text
4. The `global` declarations moved into the handlers that need them

```bash
cd /home/daniel/Projects/barf/cyrus
python -c "
import cyrus_brain
# Verify dispatch table has all 6 command types
expected = {'switch_project', 'unlock', 'which_project', 'last_message', 'rename_session', 'pause'}
actual = set(cyrus_brain._COMMAND_HANDLERS.keys())
assert actual == expected, f'Missing: {expected - actual}, Extra: {actual - expected}'
# Verify all handlers are callable
for name, fn in cyrus_brain._COMMAND_HANDLERS.items():
    assert callable(fn), f'{name} handler is not callable'
    assert fn.__doc__, f'{name} handler missing docstring'
print('All 6 handlers registered and documented.')
"
```

### Step 7: Verify complexity

If `radon` is available:
```bash
pip install radon 2>/dev/null
radon cc /home/daniel/Projects/barf/cyrus/cyrus_brain.py -s -n C | grep -E "_handle_|_execute_cyrus"
```

Expected: all handlers CC ≤ 3, dispatcher CC = 2. If radon is not available, manually verify:
- `_handle_switch_project`: 1 if/else → CC = 2
- `_handle_unlock`: no branches → CC = 1
- `_handle_which_project`: no branches → CC = 1
- `_handle_last_message`: 1 if/else → CC = 2
- `_handle_rename_session`: 2 branches (old_hint ternary + if/else) → CC = 3
- `_handle_pause`: no branches → CC = 1
- `_execute_cyrus_command`: 2 branches (handler None check + try/except + if result) → CC = 3

All under the target of CC < 5.

### Step 8: Line count verification

```bash
wc -l /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

Expected change:
- Removed: ~69 lines (old function body)
- Added: ~110 lines (6 handlers ~80 lines + dispatch table ~8 lines + new dispatcher ~15 lines + type alias + blank lines)
- Net: +~40 lines

This is acceptable — the goal is not line reduction but decomposition into testable units.

## Acceptance Criteria Mapping

| Criterion | Verified by |
|-----------|-------------|
| `_execute_cyrus_command()` refactored into dispatch dict `_COMMAND_HANDLERS` | Step 3 (dispatch table), Step 4 (refactored function) |
| Each handler is < 50 lines and handles a single command type | Step 2 (longest handler `_handle_rename_session` is ~14 lines) |
| All original behavior preserved (no logic changes) | Step 6 (manual verification + import test) |
| Unit tests added for each handler (Issue 009) | Deferred — handlers have clean signatures for testing. Test file creation belongs to test suite sprint. |
| Complexity reduced: cyclomatic complexity per function < 5 | Step 7 (all handlers CC ≤ 3, dispatcher CC = 3) |
| Error handling improved: specific exceptions logged instead of silently swallowed | Step 4 (try/except with `logger.exception()` + unknown command `logger.warning()`) |

## Risk Notes

1. **Issues 005/006 still PLANNED**: `_resolve_project()`, `_fast_command()`, `SessionManager`, and all globals remain inline in `cyrus_brain.py` (no `cyrus_common.py` exists). Handlers call local definitions directly. If 005 later extracts shared functions, handler call sites change from local to import — a straightforward follow-up.

2. **Global state in handlers**: Handlers directly access module globals (`_active_project`, `_project_locked`, etc.) using the existing lock pattern. This is thread-safe and matches the existing code. If a future issue extracts handlers into a separate module, a state object or callback injection will be needed.

3. **Uniform signature with unused params**: Some handlers don't use all parameters (`_handle_unlock` ignores `cmd`, `session_mgr`). The uniform signature is intentional — it enables the dispatch table pattern. If ruff or a linter flags unused params, use `_` prefix on the param names in those specific handlers.

4. **`_send` vs `_send_threadsafe`**: The `pause` handler uses `_send()` (async coroutine via `run_coroutine_threadsafe`), not `_send_threadsafe()`. This matches the original code. `_send_threadsafe` is a sync wrapper used by other parts of the codebase.

5. **Logging configuration**: `logger = logging.getLogger(__name__)` works with any logging configuration. If no handler is configured (common in scripts), log messages above WARNING go to stderr by default. The `main()` function should configure `logging.basicConfig()` — but that's Issue 010's scope.
