# Implementation Plan: Break up `_execute_cyrus_command` into dispatch table

**Issue**: [007-Break-up-execute-cyrus-command-into-dispatch-table](/home/daniel/Projects/barf/cyrus/issues/007-Break-up-execute-cyrus-command-into-dispatch-table.md)
**Created**: 2026-03-16
**PROMPT**: Plan phase — manual Claude Code session

## Gap Analysis

**Already exists**:
- `_execute_cyrus_command()` in `cyrus_brain.py` (lines 331–399) — 69-line if/elif chain handling 6 command types
- `_fast_command()` (lines 290–328) — regex parser that detects commands and returns `{"type": "...", ...}` dicts
- `_resolve_project()` (line 123) — alias resolution helper
- `SessionManager` class (lines 1027–1103) — methods: `aliases`, `on_session_switch`, `last_response`, `rename_alias`
- Module globals with thread-safe locks: `_active_project`, `_project_locked`, `_speak_queue`, `_send()`
- Single call site at line 1521 in `routing_loop`

**Needs building**:
- 6 handler functions (`_handle_switch_project`, `_handle_unlock`, `_handle_which_project`, `_handle_last_message`, `_handle_rename_session`, `_handle_pause`)
- `_COMMAND_HANDLERS` dispatch dict with `CommandHandler` type alias
- `logging` import + `logger` module-level variable (currently not imported)
- Refactored `_execute_cyrus_command()` using dispatch lookup + try/except

**Path discrepancy**: Issue references `cyrus2/` paths but actual source lives at project root (`/home/daniel/Projects/barf/cyrus/`). The `cyrus2/` directory contains only `pyproject.toml`. `cyrus_common.py` does not exist. This plan operates on root-level `cyrus_brain.py`.

**Actual function size**: Issue says "678–776 line monolith" but that's the original pre-refactor line range (331–1107) including ChatWatcher/PermissionWatcher/SessionManager. Actual `_execute_cyrus_command()` is ~69 lines. Refactor is still valuable for testability, extensibility, error handling, and complexity reduction.

## Approach

**Dispatch table pattern** — Replace the if/elif chain with a `dict[str, Callable]` mapping command type strings to small handler functions. Each handler has a uniform signature and returns spoken text (or `""` to suppress TTS). The dispatcher does a single lookup, wraps the call in try/except, and enqueues TTS if the handler returns non-empty text.

**Why this approach**:
- **Testability**: Each handler can be unit-tested independently with mock globals
- **Extensibility**: Adding a new command = writing a function + one dict entry
- **Error handling**: Single try/except in dispatcher replaces silent failures
- **Complexity**: Each handler CC ≤ 3 vs. the current monolithic chain

### Key Design Decisions

**D1. Handlers stay in `cyrus_brain.py`** — Every handler accesses brain-specific module globals (`_active_project`, `_project_locked`, `_speak_queue`, `_send`). Moving them to `cyrus_common.py` (which doesn't exist) would require injecting all state via callbacks for 5–15 line functions. If Issue 005 later extracts shared code, handler calls change from local to imported — trivial follow-up.

**D2. Uniform handler signature with `str` return**:
```python
def _handle_xxx(cmd: dict, spoken: str, session_mgr: "SessionManager",
                loop: asyncio.AbstractEventLoop) -> str:
```
Return `""` = handler already handled speech (or doesn't need any). This replaces `return` early-exit pattern.

**D3. Logging in handlers, prints untouched elsewhere** — New handler functions use `logging` only. Existing prints outside handlers left for Issue 010 scope.

**D4. Error handling in dispatcher, not each handler** — Single try/except wraps each handler call. `logger.exception()` includes full traceback.

**D5. No state object extraction** — YAGNI for 5–15 line functions in the same module as globals. Locks already provide thread safety. `unittest.mock.patch` handles test isolation.

**D6. Type-annotated dispatch table**:
```python
CommandHandler = Callable[[dict, str, "SessionManager", asyncio.AbstractEventLoop], str]
_COMMAND_HANDLERS: dict[str, CommandHandler] = { ... }
```

## Rules to Follow

- No `.claude/rules/` directory exists in the cyrus project
- Follow existing code patterns in `cyrus_brain.py`: thread-safe global access via locks, `asyncio.run_coroutine_threadsafe` for async calls from sync context
- Preserve all original behavior — no logic changes
- Use `ruff` for linting/formatting if available (`cyrus2/pyproject.toml` has ruff config)

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Implementation | `python-pro` agent (`.claude/agents/python-pro.md`) | Python 3.11+ specialist for the refactoring |
| Verification | Bash subagent | Run `py_compile`, ruff checks, and dispatch table validation |

## Prioritized Tasks

- [ ] **Add imports**: `import logging`, `from typing import Callable`, and `logger = logging.getLogger(__name__)` near top of `cyrus_brain.py`
- [ ] **Create 6 handler functions** immediately before `_execute_cyrus_command()` (before line 331):
  - `_handle_switch_project` — lock routing to named project (CC=2)
  - `_handle_unlock` — release project lock (CC=1)
  - `_handle_which_project` — report active project + lock status (CC=1)
  - `_handle_last_message` — replay last response via TTS (CC=2)
  - `_handle_rename_session` — rename session alias (CC=3)
  - `_handle_pause` — delegate pause to voice service (CC=1)
- [ ] **Create dispatch table** `_COMMAND_HANDLERS` with `CommandHandler` type alias after handlers
- [ ] **Refactor `_execute_cyrus_command()`** to use dispatch lookup + try/except + conditional TTS enqueue
- [ ] **Lint and format** with `ruff check` / `ruff format` (or `py_compile` fallback)
- [ ] **Verify behavior preservation**: dispatch table has all 6 types, all handlers callable with docstrings
- [ ] **Verify cyclomatic complexity** < 5 per function (all handlers CC ≤ 3, dispatcher CC = 3)

## Handler Implementations

### Command types (from current code lines 335–395):

| Command Type | Lines | CC | Globals Accessed |
|---|---|---|---|
| `switch_project` | 335–347 | 3→2 | `_active_project` (write), `_project_locked` (write) |
| `unlock` | 349–353 | 1 | `_project_locked` (write) |
| `which_project` | 355–362 | 1 | `_active_project` (read), `_project_locked` (read) |
| `last_message` | 364–375 | 2 | `_active_project` (read), `_speak_queue` (write) |
| `rename_session` | 377–390 | 3 | `_active_project` (read) |
| `pause` | 392–395 | 1 | none (sends via `_send`) |

**Tail behavior** (lines 397–398): `if spoken: asyncio.run_coroutine_threadsafe(_speak_queue.put(("", spoken)), loop)`. Handlers `last_message` and `pause` currently `return` early to skip this. In the new design, they return `""` instead.

### Exact handler code

See the 6 handler functions, dispatch table, and refactored dispatcher in the **Detailed Implementation** section below.

<details>
<summary>Detailed Implementation (click to expand)</summary>

#### Step 1: Add imports (after line 34, near existing imports)

```python
import logging
from typing import Callable

logger = logging.getLogger(__name__)
```

Note: `logging` is NOT currently imported. `from typing import Callable` is new.

#### Step 2: Handler functions (insert before line 331)

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

#### Step 3: Dispatch table (insert after handlers, before `_execute_cyrus_command`)

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

#### Step 4: Refactored dispatcher (replace lines 331–399)

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

</details>

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| `_execute_cyrus_command()` refactored into `_COMMAND_HANDLERS` dispatch dict | Verify `_COMMAND_HANDLERS` is a dict with 6 entries, dispatcher uses `.get()` lookup | verification script |
| Each handler < 50 lines, single command type | Verify longest handler (`_handle_rename_session`) is ~14 lines | code inspection |
| All original behavior preserved (no logic changes) | 1:1 comparison of handler logic vs original if/elif branches | code review + verification script |
| Unit tests for each handler (Issue 009) | **Deferred** — handlers have clean uniform signatures for testing. Test file creation is Issue 009 scope. | deferred |
| Cyclomatic complexity per function < 5 | `radon cc` or manual verification: all handlers CC ≤ 3, dispatcher CC = 3 | verification script |
| Error handling: specific exceptions logged, not silently swallowed | Verify try/except with `logger.exception()` in dispatcher, `logger.warning()` for unknown commands | code inspection |

**Note**: No pytest framework exists yet (Issue 018). The "unit tests for each handler" criterion explicitly defers to Issue 009. This plan makes handlers testable but does not create the test file.

## Validation (Backpressure)

- **Compile check**: `python -m py_compile cyrus_brain.py` must pass
- **Lint**: `ruff check cyrus_brain.py` must pass (or `py_compile` if ruff unavailable)
- **Format**: `ruff format cyrus_brain.py` must not produce errors
- **Dispatch table verification**: All 6 command types present, all handlers callable with docstrings
- **Complexity**: All handlers CC < 5 (verified via `radon cc` or manual inspection)
- **Behavior preservation**: Original if/elif branches map 1:1 to handler functions

## Files to Create/Modify

- **Modify**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py` — add imports, handler functions, dispatch table, refactor `_execute_cyrus_command()`

No new files needed. Test file creation is Issue 009 scope.

## Risk Notes

1. **Issues 005/006 still PLANNED**: All dependencies (`_resolve_project`, `_fast_command`, `SessionManager`, globals) remain inline in `cyrus_brain.py`. If 005 later extracts to `cyrus_common.py`, handler calls change from local to imported — trivial follow-up.

2. **Uniform signature with unused params**: Some handlers don't use all parameters (`_handle_unlock` ignores `cmd`, `session_mgr`). Intentional for dispatch table pattern. If ruff flags unused params, prefix with `_` in those specific handlers.

3. **`_send` vs `_send_threadsafe`**: `pause` handler uses `_send()` (async coroutine via `run_coroutine_threadsafe`), matching original code. `_send_threadsafe` is a sync wrapper used elsewhere.

4. **Logging configuration**: `logger = logging.getLogger(__name__)` works with any config. `main()` should configure `logging.basicConfig()` — that's Issue 010's scope.
