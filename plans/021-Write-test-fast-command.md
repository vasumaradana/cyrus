# Plan 021: Write test_fast_command.py (Tier 1)

## Summary

Refactor `_fast_command()` to return a simpler dict format (per interview decisions), add duration/password parameter parsing, rename command types to shorter names, update all callers, then create `cyrus2/tests/test_fast_command.py` with 29 parametrized test cases covering all 6 command types plus non-command edge cases. Zero mocking — pure `str → dict|None` transform.

## Prerequisites

- **Issue 018** (conftest.py fixtures) — PLANNED, not yet built. This plan bootstraps the minimal test infrastructure if missing (directory, `__init__.py`, `pyproject.toml`). Tier 1 pure function tests need no fixtures from conftest.
- **Issue 005** (cyrus_common.py extraction) — PLANNED, not yet built. `_fast_command()` is still inline in `cyrus_brain.py`, `main.py`, and `cyrus_server.py`. Tests import from `cyrus_brain` directly. Issue 005 will eventually move it to `cyrus_common.py`.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/tests/test_fast_command.py` | Does not exist | Create with 29 test cases |
| `cyrus2/tests/` directory | Does not exist | Create (with `__init__.py`) |
| `cyrus2/pyproject.toml` | Does not exist | Create with pytest `pythonpath = [".."]` |
| Simpler return format | Returns `{"action": "command", "spoken": "", "message": "", "command": {"type": "pause"}}` | Refactor to `{"command": "pause"}` |
| Duration parsing for pause | Not implemented | Add regex branch for "pause for N seconds" |
| Password parsing for unlock | Not implemented | Add regex branch for "unlock <password>" |
| Command name `switch_project` | Used in all 3 files | Rename to `switch` |
| Command name `rename_session` | Used in `cyrus_brain.py` and `main.py` | Rename to `rename`, key `"new"` → `"name"` |
| Callers handle old format | `decision.get("action")`, `decision.get("command", {}).get("type")` | Update routing logic in all callers |

## Source Code Under Test

### `_fast_command(text: str) -> dict | None` — cyrus_brain.py:290-328

Current implementation with 7 regex branches returning complex dicts:

```python
def _fast_command(text: str) -> dict | None:
    t = text.lower().strip().rstrip(".,!?")

    # 1. pause/resume — fullmatch
    if re.fullmatch(r"pause|resume|stop listening|start listening", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "pause"}}

    # 2. unlock/auto — fullmatch
    if re.fullmatch(r"(un ?lock|auto|follow focus|auto(matic)? routing)", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "unlock"}}

    # 3. which project — search (substring)
    if re.search(r"\b(which|what)\b.{0,20}\b(project|session)\b", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "which_project"}}

    # 4. last message — fullmatch
    if re.fullmatch(r"(last|repeat|replay|again).{0,30}(message|response|said)?", t):
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "last_message"}}

    # 5. switch — 3 match patterns
    m = (re.match(r"(?:switch(?:ed)?(?: to)?|use|go to|open|activate)\s+(.+)", t)
         or re.match(r"make\s+(.+?)\s+(?:the\s+)?active", t)
         or re.match(r"(?:set|change)\s+(?:active\s+)?(?:project|session)\s+to\s+(.+)", t))
    if m:
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "switch_project", "project": m.group(1).strip()}}

    # 6. rename (current session) — 2 match patterns
    m = (re.match(r"(?:rename|relabel)\s+(?:this\s+)?(?:session\s+|window\s+)?to\s+(.+)", t)
         or re.match(r"call\s+this\s+(?:session\s+|window\s+)?(.+)", t))
    if m:
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "rename_session", "new": m.group(1).strip()}}

    # 7. rename (explicit old → new) — 1 match pattern
    m = re.match(r"(?:rename|relabel)\s+(.+?)\s+to\s+(.+)", t)
    if m:
        return {"action": "command", "spoken": "", "message": "",
                "command": {"type": "rename_session",
                            "old": m.group(1).strip(), "new": m.group(2).strip()}}

    return None
```

### Duplicates

- **`main.py:322-371`** — identical logic, includes docstring
- **`cyrus_server.py:69-97`** — stripped-down version: no `switch(?:ed)?` variant, no rename patterns

### Callers

**`cyrus_brain.py:1494-1522`** — routing logic:
```python
decision = _fast_command(text)
if decision is None:
    # build answer or forward decision dict
action = decision.get("action", "forward")
if action == "command":
    ctype = decision.get("command", {}).get("type", "")
    _execute_cyrus_command(ctype, decision.get("command", {}), spoken, ...)
```

**`main.py:1663-1703`** — same pattern plus remote brain fallback

**`cyrus_server.py:123-128`** — WebSocket handler, simpler routing

### `_execute_cyrus_command()` — cyrus_brain.py:331-399, main.py:374-451

Dispatches on `ctype` string: `"switch_project"`, `"unlock"`, `"which_project"`, `"last_message"`, `"rename_session"`, `"pause"`. Uses `cmd.get("project")`, `cmd.get("new")`, `cmd.get("old")`.

## Design Decisions

### 1. Refactor return format to flat dict

Per interview Q1: change from nested `{"action": "command", "spoken": "", "message": "", "command": {"type": "pause"}}` to flat `{"command": "pause"}`.

**Rationale:** The wrapping (`action`, `spoken`, `message`) is caller concern, not parser concern. `_fast_command()` is a pure regex classifier — it should return the classification, not a dispatch envelope. Callers build the envelope.

### 2. Add duration parsing for pause

Per interview Q2: "pause for 10 seconds" → `{"command": "pause", "duration": 10}`.

New regex branch before the simple pause fullmatch:
```python
m = re.fullmatch(r"pause\s+(?:for\s+)?(\d+)\s*(?:seconds?|sec|s|minutes?|min|m)?", t)
```

"pause xyz" (non-numeric) falls through to the simple fullmatch, which also fails → returns `None`.

### 3. Add password parsing for unlock

Per interview Q2: "unlock mypassword" → `{"command": "unlock", "password": "mypassword"}`.

New regex branch before the simple unlock fullmatch:
```python
m = re.fullmatch(r"un ?lock\s+(.+)", t)
```

Only matches `unlock <something>`. The bare `unlock`, `auto`, `follow focus` patterns still match the simple fullmatch.

### 4. Rename command types

Per interview Q3:
- `switch_project` → `switch`
- `rename_session` → `rename`
- Rename key `"new"` → `"name"` in rename results (matches issue spec)

### 5. Use `@pytest.mark.parametrize` throughout

One test function per command type + one for non-commands. Parametrize with `(input, expected)` tuples and descriptive IDs.

### 6. Import strategy

```python
from cyrus_brain import _fast_command
```

This triggers module-level imports (pygetwindow, comtypes, etc.). Tests run on the dev machine with all production deps installed.

### 7. Test naming convention

Parametrize IDs provide scenario context:
```
test_fast_command.py::test_pause[simple_pause] PASSED
test_fast_command.py::test_pause[with_duration_seconds] PASSED
test_fast_command.py::test_switch[switch_to_project] PASSED
```

### 8. Update all three file copies

All three copies (`cyrus_brain.py`, `main.py`, `cyrus_server.py`) get the same refactored `_fast_command()`. Callers and `_execute_cyrus_command()` updated in lockstep. Issue 005 will later deduplicate.

## Acceptance Criteria → Test Mapping

| AC | Requirement | Verification |
|---|---|---|
| AC1 | `cyrus2/tests/test_fast_command.py` exists with 25+ test cases | File exists, `pytest --collect-only` shows ≥29 items |
| AC2 | Each command type has 2-3 test cases | 3-5 parametrized cases per command type |
| AC3 | Commands tested: pause, unlock, which_project, last_message, switch, rename | 6 test functions, one per command type |
| AC4 | Non-command strings return None | `test_non_command` with 5 parametrized cases |
| AC5 | All tests pass: `pytest tests/test_fast_command.py -v` | Exit code 0 |
| AC6 | Test names indicate command type and scenario | Parametrize IDs are descriptive English slugs |

## Test Case Inventory

### `test_pause` — 5 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `simple_pause` | `"pause"` | `{"command": "pause"}` | Basic pause command |
| `resume` | `"resume"` | `{"command": "pause"}` | Resume triggers same pause toggle |
| `stop_listening` | `"stop listening"` | `{"command": "pause"}` | Alternate phrasing |
| `with_duration_seconds` | `"pause for 10 seconds"` | `{"command": "pause", "duration": 10}` | Duration parsing |
| `invalid_duration` | `"pause xyz"` | `None` | Non-numeric after pause → not a command |

### `test_unlock` — 4 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `simple_unlock` | `"unlock"` | `{"command": "unlock"}` | Basic unlock |
| `auto` | `"auto"` | `{"command": "unlock"}` | Shorthand |
| `follow_focus` | `"follow focus"` | `{"command": "unlock"}` | Alternate phrasing |
| `with_password` | `"unlock mypassword"` | `{"command": "unlock", "password": "mypassword"}` | Password parsing |

### `test_which_project` — 3 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `which_project` | `"which project"` | `{"command": "which_project"}` | Basic query |
| `what_session` | `"what session is this"` | `{"command": "which_project"}` | Alternate words |
| `what_project_am_i_on` | `"what project am i on"` | `{"command": "which_project"}` | Natural phrasing |

### `test_last_message` — 3 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `last_message` | `"last message"` | `{"command": "last_message"}` | Basic request |
| `repeat` | `"repeat"` | `{"command": "last_message"}` | Single-word variant |
| `again` | `"again"` | `{"command": "last_message"}` | Shortest variant |

### `test_switch` — 5 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `switch_to_project` | `"switch to myproject"` | `{"command": "switch", "project": "myproject"}` | Standard phrasing |
| `switch_without_to` | `"switch myproject"` | `{"command": "switch", "project": "myproject"}` | Omit "to" |
| `use_project` | `"use barf-ts"` | `{"command": "switch", "project": "barf-ts"}` | Alternate verb |
| `go_to_project` | `"go to my app"` | `{"command": "switch", "project": "my app"}` | Multi-word project name |
| `switch_alone` | `"switch"` | `None` | No target → not a command |

### `test_rename` — 5 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `rename_to_new` | `"rename to newname"` | `{"command": "rename", "name": "newname"}` | Rename current session |
| `rename_this_to` | `"rename this to newname"` | `{"command": "rename", "name": "newname"}` | Explicit "this" |
| `call_this` | `"call this newname"` | `{"command": "rename", "name": "newname"}` | Alternate phrasing |
| `rename_old_to_new` | `"rename oldname to newname"` | `{"command": "rename", "name": "newname", "old": "oldname"}` | Explicit old+new |
| `rename_alone` | `"rename"` | `None` | No target → not a command |

### `test_non_command` — 4 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `regular_conversation` | `"hello how are you"` | `None` | Normal speech |
| `partial_match_pausable` | `"pausable"` | `None` | fullmatch prevents substring match |
| `empty_string` | `""` | `None` | Edge case |
| `trailing_punctuation` | `"what is the weather?"` | `None` | Question without project/session keyword |

**Total: 29 test cases** (5 + 4 + 3 + 3 + 5 + 5 + 4)

## Refactored `_fast_command()` Target

After refactoring, the function in `cyrus_brain.py` should be:

```python
def _fast_command(text: str) -> dict | None:
    """Regex fast-path for obvious Cyrus meta-commands.

    Returns a flat command dict or None if the utterance
    should be sent to the LLM.
    """
    t = text.lower().strip().rstrip(".,!?")

    # pause with optional duration
    m = re.fullmatch(r"pause\s+(?:for\s+)?(\d+)\s*(?:seconds?|sec|s|minutes?|min|m)?", t)
    if m:
        return {"command": "pause", "duration": int(m.group(1))}
    if re.fullmatch(r"pause|resume|stop listening|start listening", t):
        return {"command": "pause"}

    # unlock with optional password
    m = re.fullmatch(r"un ?lock\s+(.+)", t)
    if m:
        return {"command": "unlock", "password": m.group(1).strip()}
    if re.fullmatch(r"(un ?lock|auto|follow focus|auto(matic)? routing)", t):
        return {"command": "unlock"}

    # which project
    if re.search(r"\b(which|what)\b.{0,20}\b(project|session)\b", t):
        return {"command": "which_project"}

    # last message
    if re.fullmatch(r"(last|repeat|replay|again).{0,30}(message|response|said)?", t):
        return {"command": "last_message"}

    # switch
    m = (re.match(r"(?:switch(?:ed)?(?: to)?|use|go to|open|activate)\s+(.+)", t)
         or re.match(r"make\s+(.+?)\s+(?:the\s+)?active", t)
         or re.match(r"(?:set|change)\s+(?:active\s+)?(?:project|session)\s+to\s+(.+)", t))
    if m:
        return {"command": "switch", "project": m.group(1).strip()}

    # rename current session
    m = (re.match(r"(?:rename|relabel)\s+(?:this\s+)?(?:session\s+|window\s+)?to\s+(.+)", t)
         or re.match(r"call\s+this\s+(?:session\s+|window\s+)?(.+)", t))
    if m:
        return {"command": "rename", "name": m.group(1).strip()}

    # rename explicit old → new
    m = re.match(r"(?:rename|relabel)\s+(.+?)\s+to\s+(.+)", t)
    if m:
        return {"command": "rename", "name": m.group(2).strip(), "old": m.group(1).strip()}

    return None
```

## Implementation Steps

### Step 1: Verify/create test infrastructure

```bash
cd /home/daniel/Projects/barf/cyrus

# Check if test infrastructure exists (from issue 018)
test -d cyrus2/tests/ && echo "OK: tests dir" || echo "MISSING: tests dir"
test -f cyrus2/tests/__init__.py && echo "OK: __init__" || echo "MISSING: __init__"
test -f cyrus2/pyproject.toml && echo "OK: pyproject.toml" || echo "MISSING: pyproject.toml"
```

If missing, create the minimal structure:

```bash
mkdir -p cyrus2/tests
touch cyrus2/tests/__init__.py
```

Create `cyrus2/pyproject.toml` with pytest config:

```toml
[tool.pytest.ini_options]
pythonpath = [".."]
testpaths = ["tests"]
```

### Step 2: Write test file (RED — tests will fail against current implementation)

Create `cyrus2/tests/test_fast_command.py` with all 29 parametrized test cases. Tests assert the **new** simplified return format. They will fail until the refactoring in Step 3.

```python
"""Tier 1 pure-function tests for _fast_command() meta-command routing.

Tests cover all 6 command types (pause, unlock, which_project, last_message,
switch, rename) plus non-command edge cases. Zero mocking — pure str → dict|None.
"""

from __future__ import annotations

import pytest

from cyrus_brain import _fast_command


@pytest.mark.parametrize(("text", "expected"), [...], ids=[...])
def test_pause(text: str, expected: dict | None) -> None:
    assert _fast_command(text) == expected

# ... one test function per command type + test_non_command ...
```

### Step 3: Refactor `_fast_command()` in `cyrus_brain.py` (GREEN — make tests pass)

Apply the refactored version from the "Refactored `_fast_command()` Target" section above. Changes:

1. **Return format**: flat `{"command": "..."}` instead of nested envelope
2. **New branch**: pause with duration (`pause for 10 seconds`)
3. **New branch**: unlock with password (`unlock mypassword`)
4. **Rename**: `"switch_project"` → `"switch"`, `"rename_session"` → `"rename"`, key `"new"` → `"name"`

### Step 4: Run tests — verify all 29 pass

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_fast_command.py -v
```

### Step 5: Update caller in `cyrus_brain.py` (~line 1494-1522)

The routing logic after `_fast_command()` must adapt to the new flat format:

```python
# Old pattern:
decision = _fast_command(text)
if decision is None:
    ...
action = decision.get("action", "forward")
if action == "command":
    ctype = decision.get("command", {}).get("type", "")
    _execute_cyrus_command(ctype, decision.get("command", {}), spoken, ...)

# New pattern:
fast = _fast_command(text)
if fast is not None:
    ctype = fast["command"]
    _execute_cyrus_command(ctype, fast, "", session_mgr, loop)
    _conversation_active = False
elif _is_answer_request(text):
    # ... answer handling (unchanged) ...
else:
    # ... forward handling (unchanged) ...
```

### Step 6: Update `_execute_cyrus_command()` in `cyrus_brain.py` (~line 331-399)

- Change `elif ctype == "switch_project":` → `elif ctype == "switch":`
- Change `elif ctype == "rename_session":` → `elif ctype == "rename":`
- Change `cmd.get("new", "")` → `cmd.get("name", "")`

### Step 7: Apply same refactoring to `main.py`

1. Refactor `_fast_command()` at `main.py:322-371` — same changes as Step 3
2. Update caller at `main.py:1663-1703` — same pattern as Step 5
3. Update `_execute_cyrus_command()` at `main.py:374-451` — same renames as Step 6

### Step 8: Apply same refactoring to `cyrus_server.py`

1. Refactor `_fast_command()` at `cyrus_server.py:69-97` — same changes as Step 3 (note: this version lacks rename patterns, which is fine)
2. Update caller at `cyrus_server.py:123-128` — adapt to new flat format

### Step 9: Final verification

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2

# All 29 tests pass
pytest tests/test_fast_command.py -v

# Verify test count
pytest tests/test_fast_command.py --collect-only -q | tail -1

# Run subsets per acceptance criteria
pytest tests/test_fast_command.py -k "pause" -v
pytest tests/test_fast_command.py -k "switch or rename" -v
pytest tests/test_fast_command.py -k "non_command" -v
```

## Files Created/Modified

| File | Action | Description |
|---|---|---|
| `cyrus2/tests/` | **Create** | Test directory |
| `cyrus2/tests/__init__.py` | **Create** | Package marker |
| `cyrus2/pyproject.toml` | **Create** | pytest config with `pythonpath = [".."]` |
| `cyrus2/tests/test_fast_command.py` | **Create** | 29 parametrized test cases across 7 test functions |
| `cyrus_brain.py` | **Modify** | Refactor `_fast_command()` return format + callers |
| `main.py` | **Modify** | Refactor `_fast_command()` return format + callers |
| `cyrus_server.py` | **Modify** | Refactor `_fast_command()` return format + callers |

## Import Risk

`cyrus_brain.py` has heavy module-level imports (pygetwindow, comtypes, pyautogui, pyperclip, uiautomation). If these aren't installed in the test environment, imports fail with `ModuleNotFoundError`.

**Mitigation:** Cyrus is a Windows desktop app and tests run on the dev machine with all deps installed. If imports fail:
1. First try `pip install -r requirements.txt`
2. If specific modules are unavailable, flag as STUCK — fixing module-level imports is a separate issue

## Risk: Caller Update Scope

The refactoring touches 3 files × (function + caller + executor) = 9 code locations. Missing one creates a runtime error (old code tries `.get("action")` on the new flat dict).

**Mitigation:** Steps 5-8 are explicit about every call site. The builder should grep for `_fast_command` and `"switch_project"` and `"rename_session"` after all changes to verify no references to the old format remain.
