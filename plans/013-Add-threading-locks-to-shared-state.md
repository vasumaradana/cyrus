# Implementation Plan: Add threading locks to shared state

**Issue**: [013-Add-threading-locks-to-shared-state](/home/daniel/Projects/barf/cyrus/issues/013-Add-threading-locks-to-shared-state.md)
**Created**: 2026-03-16
**PROMPT**: PROMPT_plan

## Gap Analysis

**Already exists**:
- `import threading` at line 36 of `cyrus_brain.py` and line 17 of `cyrus_common.py`
- `_active_project_lock` (threading.Lock) at line 103 of `cyrus_brain.py` — already protects `_active_project`
- `_project_locked_lock` (threading.Lock) at line 107 — already protects `_project_locked`
- `_voice_lock` (asyncio.Lock) at line 125 — already protects `_voice_writer`
- All 6 target variables exist and are used across multiple threads

**Needs building**:
- `threading.Lock` for `_chat_input_cache` (defined in cyrus_common.py:122)
- `threading.Lock` for `_chat_input_coords` (defined in cyrus_common.py:125, imported into cyrus_brain.py)
- `threading.Lock` for `_vscode_win_cache` (cyrus_brain.py:104)
- `threading.Lock` for `_mobile_clients` (cyrus_brain.py:118)
- `threading.Lock` for `_whisper_prompt` (cyrus_brain.py:110)
- Convert `_conversation_active` from `bool` to `threading.Event` (cyrus_brain.py:109)
- Wrap ALL reads/writes of these 6 variables with lock contexts
- Acceptance-driven tests

## Approach

**Two-file approach** (pragmatic, avoids circular imports):
- Variables in `cyrus_common.py` (`_chat_input_cache`, `_chat_input_coords`) get their locks defined **alongside them in cyrus_common.py**, exported for use in cyrus_brain.py
- Variables in `cyrus_brain.py` (`_vscode_win_cache`, `_mobile_clients`, `_whisper_prompt`, `_conversation_active`) get locks defined in cyrus_brain.py

**Why not "move all to cyrus_brain.py"** (interview answer): Moving `_chat_input_cache` and `_chat_input_coords` to cyrus_brain.py creates a circular import — cyrus_brain.py imports from cyrus_common.py, and the ChatWatcher/PermissionWatcher classes in cyrus_common.py directly access these module globals. Refactoring to constructor injection is a separate issue's scope. The pragmatic approach achieves the same safety goal.

**`_mobile_clients` lock strategy**: This variable is only accessed from async code (same event loop thread), but the issue requires a threading.Lock. Since the lock regions contain `await` calls in `_send()`, we use a copy-under-lock pattern: snapshot the set under lock, send without lock, update dead set under lock.

**`_conversation_active` conversion**: Replace `bool` with `threading.Event`. Remove from `global` declarations (Event methods don't reassign the variable). Map: `if _conversation_active:` → `.is_set()`, `= True` → `.set()`, `= False` → `.clear()`.

## Rules to Follow

- `.claude/rules/` — directory is empty, no project-specific rules
- Follow existing code patterns: threading.Lock for new locks, consistent `with lock:` style matching `_active_project_lock` usage

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Implementation | `python-expert` skill | Python threading best practices |
| Testing | `python-testing` skill | unittest patterns matching test_007/test_008 |
| Code review | `code-reviewer` agent | Verify no deadlocks in lock ordering |

## Prioritized Tasks

- [x] **1. Add locks in `cyrus_common.py`** — Define `_chat_input_cache_lock` and `_chat_input_coords_lock` as module-level `threading.Lock()` after the variable definitions (after line 125). Export them.
- [x] **2. Wrap accesses in `cyrus_common.py`** — Wrap all reads/writes to `_chat_input_cache` and `_chat_input_coords` in ChatWatcher.start() poll function and PermissionWatcher._scan() with `with lock:` blocks.
- [x] **3. Add locks in `cyrus_brain.py`** — Define `_vscode_win_cache_lock`, `_mobile_clients_lock`, `_whisper_prompt_lock` as module-level `threading.Lock()`. Convert `_conversation_active` from `bool` to `threading.Event()` (initially cleared).
- [x] **4. Import new locks from cyrus_common into cyrus_brain.py** — Added `_chat_input_coords_lock` to the import block (only `_chat_input_coords_lock` needed; `_chat_input_cache_lock` is only accessed in cyrus_common).
- [x] **5. Wrap `_vscode_win_cache` accesses** — In `_submit_to_vscode_impl()`: wrap `.get()` read, `.pop()` write, and `[proj] = win` write in small `with _vscode_win_cache_lock:` blocks. Do NOT hold lock during sleep/UIA operations.
- [x] **6. Wrap `_whisper_prompt` accesses** — In `on_whisper_prompt` closure: wrap the assignment under lock. In `handle_voice_connection`: read under lock into a local, then use the local.
- [x] **7. Wrap `_mobile_clients` accesses** — In `_send()`: copy-under-lock pattern (snapshot set, iterate without lock, update dead under lock). In `handle_mobile_ws`: wrap `.add()` and `.discard()` under lock.
- [x] **8. Convert `_conversation_active` to threading.Event** — Replaced definition. Removed from `global` declarations in `voice_reader` and `routing_loop`. Replaced all reads with `.is_set()`. Replaced writes with `.set()`/`.clear()`.
- [x] **9. Write acceptance-driven tests** — Created `cyrus2/tests/test_013_threading_locks.py` (52 tests: AST structural checks + runtime threading tests with mocked Windows deps).
- [x] **10. Run tests and lint** — All 301 tests pass, ruff lint/format clean, no regressions.

## Variable Access Map (Complete)

### `_chat_input_cache` (cyrus_common.py:122) — Lock: `_chat_input_cache_lock`
| Location | Type | Context |
|----------|------|---------|
| cyrus_common.py:886 | WRITE | PermissionWatcher._scan() background thread |

### `_chat_input_coords` (cyrus_common.py:125) — Lock: `_chat_input_coords_lock`
| Location | Type | Context |
|----------|------|---------|
| cyrus_common.py:589 | READ | ChatWatcher poll thread |
| cyrus_common.py:597-600 | WRITE | ChatWatcher poll thread |
| cyrus_common.py:604 | READ | ChatWatcher poll thread |
| cyrus_common.py:883 | READ | PermissionWatcher poll thread |
| cyrus_common.py:890-893 | WRITE | PermissionWatcher poll thread |
| cyrus_brain.py:637 | READ | submit thread (busy-wait loop) |
| cyrus_brain.py:639 | READ | submit thread |
| cyrus_brain.py:650 | WRITE | submit thread |

### `_vscode_win_cache` (cyrus_brain.py:104) — Lock: `_vscode_win_cache_lock`
| Location | Type | Context |
|----------|------|---------|
| cyrus_brain.py:658 | READ | submit thread |
| cyrus_brain.py:665 | WRITE | submit thread |
| cyrus_brain.py:679 | WRITE | submit thread |

### `_conversation_active` (cyrus_brain.py:109) — Convert to `threading.Event`
| Location | Type | Context |
|----------|------|---------|
| cyrus_brain.py:857 | READ | routing_loop (async, event loop thread) |
| cyrus_brain.py:930 | WRITE | routing_loop |
| cyrus_brain.py:939 | WRITE | routing_loop |
| cyrus_brain.py:961 | WRITE | routing_loop |

### `_whisper_prompt` (cyrus_brain.py:110) — Lock: `_whisper_prompt_lock`
| Location | Type | Context |
|----------|------|---------|
| cyrus_brain.py:266 | WRITE | on_whisper_prompt (SessionManager background thread) |
| cyrus_brain.py:1096-1097 | READ | handle_voice_connection (async) |

### `_mobile_clients` (cyrus_brain.py:118) — Lock: `_mobile_clients_lock`
| Location | Type | Context |
|----------|------|---------|
| cyrus_brain.py:149 | READ | _send (async) |
| cyrus_brain.py:161 | READ | _send (async) |
| cyrus_brain.py:166 | WRITE | _send (async) |
| cyrus_brain.py:783 | WRITE | handle_mobile_ws (async) |
| cyrus_brain.py:802 | WRITE | handle_mobile_ws (async) |

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| `import threading` in cyrus_brain.py | AST check for threading import | unit (static) |
| Lock created for `_chat_input_cache` | `isinstance(cyrus_common._chat_input_cache_lock, threading.Lock)` | unit |
| Lock created for `_vscode_win_cache` | `isinstance(cyrus_brain._vscode_win_cache_lock, threading.Lock)` | unit |
| Lock created for `_chat_input_coords` | `isinstance(cyrus_common._chat_input_coords_lock, threading.Lock)` | unit |
| Lock created for `_mobile_clients` | `isinstance(cyrus_brain._mobile_clients_lock, threading.Lock)` | unit |
| Lock created for `_whisper_prompt` | `isinstance(cyrus_brain._whisper_prompt_lock, threading.Lock)` | unit |
| `_conversation_active` is threading.Event | `isinstance(cyrus_brain._conversation_active, threading.Event)` | unit |
| All reads/writes wrapped in `with lock:` | AST analysis: check every Name access to locked vars is inside a With block | unit (static) |
| `.is_set()` used for _conversation_active reads | AST/grep: no bare `if _conversation_active:` or `_conversation_active ==` | unit (static) |
| `.set()`/`.clear()` used for _conversation_active writes | AST/grep: no `_conversation_active = True/False` | unit (static) |
| No deadlocks introduced | Lock ordering consistent; no nested locks | unit (static) |
| All existing functionality preserved | Existing test_007 and test_008 still pass | regression |

## Validation (Backpressure)

- **Tests**: `python -m pytest cyrus2/tests/test_013_threading_locks.py -v` must pass
- **Regression**: `python -m pytest cyrus2/tests/ -v` must pass (all existing tests)
- **Lint**: `ruff check cyrus2/` must pass
- **Format**: `ruff format --check cyrus2/` must pass

## Deadlock Prevention Rules

1. **No nested locks** — Never hold two locks simultaneously. Each lock protects a small, fast operation.
2. **No blocking operations under lock** — Never `time.sleep()`, `await`, or UIA calls inside a `with lock:` block.
3. **Copy-under-lock for iteration** — When iterating a locked collection (e.g., `_mobile_clients`), copy under lock, iterate outside.
4. **Minimal critical sections** — Lock only the read/write, not surrounding logic.

## Files to Create/Modify

- `cyrus2/cyrus_common.py` — Add `_chat_input_cache_lock` and `_chat_input_coords_lock`; wrap 7 access sites
- `cyrus2/cyrus_brain.py` — Add 3 locks + convert `_conversation_active` to Event; import 2 locks from common; wrap ~15 access sites
- `cyrus2/tests/test_013_threading_locks.py` — New acceptance-driven test file (~200-300 lines)
