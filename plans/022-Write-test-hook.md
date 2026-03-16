# Plan 022: Write test_hook.py (Tier 2)

## Summary

Create `cyrus2/tests/test_hook.py` with 17 parametrized test cases covering all five hook event types dispatched by `cyrus_hook.main()`. Mock `sys.stdin` with `StringIO` and patch `cyrus_hook._send` with the `mock_send` fixture from conftest. Verify correct message dispatch for valid events and silent no-op for malformed input, unknown events, and empty stdin.

## Prerequisites

- **Issue 018** (state: PLANNED) — creates `cyrus2/tests/` directory, `conftest.py` with `mock_send` fixture, `pytest.ini`, and `requirements-dev.txt`. If not yet built when the builder runs, create the minimal structure (see Step 1).

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/tests/test_hook.py` | Does not exist | Create with 17 test cases |
| `cyrus2/tests/` directory | Does not exist (created by issue 018) | Verify exists; create if missing |
| `conftest.py` with `mock_send` | Does not exist (created by issue 018) | Verify exists; create if missing |
| `cyrus_hook.py` importable | Source at cyrus root (`cyrus_hook.py`) | Import via `pythonpath = ..` in pytest config |
| `pytest tests/test_hook.py -v` passes | No tests exist | All 17 cases green |

## Source Code Under Test

### `_send(msg: dict) -> None` — cyrus_hook.py:19-24

TCP socket sender to `localhost:8767`. Silently swallows all exceptions. This function is what we **patch** — never called during tests.

### `main()` — cyrus_hook.py:27-93

Entry point. Reads JSON from `sys.stdin` via `json.load(sys.stdin)`, extracts `hook_event_name` and `cwd`, dispatches to `_send()` based on event type. Always calls `sys.exit(0)` at line 93 (including after successful dispatch).

**Event dispatch summary:**

| Event | Condition to send | Message shape |
|---|---|---|
| `Stop` | `last_assistant_message` non-empty after strip | `{"event": "stop", "text": ..., "cwd": ...}` |
| `PreToolUse` | Always (all tool types) | `{"event": "pre_tool", "tool": ..., "command": ..., "cwd": ...}` |
| `PostToolUse` Bash | `exit_code != 0` OR `stderr`/`error` non-empty | `{"event": "post_tool", "tool": "Bash", "command": ..., "exit_code": ..., "error": error[:200], "cwd": ...}` |
| `PostToolUse` Edit/Write/MultiEdit/NotebookEdit | Always | `{"event": "post_tool", "tool": ..., "file_path": ..., "cwd": ...}` |
| `PostToolUse` other tools (Read, WebSearch, etc.) | **Never** — silently ignored | N/A |
| `Notification` | `message` non-empty after strip | `{"event": "notification", "message": ..., "cwd": ...}` |
| `PreCompact` | Always | `{"event": "pre_compact", "trigger": ..., "cwd": ...}` |

**Silent no-ops:** Invalid JSON, unknown event types, empty stdin, and PostToolUse for non-Bash/non-editor tools all exit cleanly without calling `_send()`.

**Key detail — Bash error truncation:** The `error` field in PostToolUse Bash messages is truncated to 200 characters (`error[:200]`). Test payloads use short strings so this doesn't affect expected values, but builders should be aware.

## Design Decisions

### 1. Test helper `_run_hook(payload_json, mock_send)`

`main()` always calls `sys.exit(0)` (line 93), even on success. Every test must catch `SystemExit`. A shared helper patches `sys.stdin` and `cyrus_hook._send`, calls `main()` inside `pytest.raises(SystemExit)`, and returns cleanly:

```python
def _run_hook(payload_json: str, mock_send) -> None:
    with patch("sys.stdin", StringIO(payload_json)), \
         patch("cyrus_hook._send", mock_send):
        with pytest.raises(SystemExit):
            main()
```

### 2. Use `mock_send` fixture from conftest

The `mock_send` fixture (defined in plan 018) is a callable `MockSend` class that records each `msg` dict in `.messages`. This avoids socket I/O and gives direct access to dispatched payloads for assertion. If conftest doesn't exist yet, the builder creates a minimal inline version.

### 3. Parametrize by event group, not one giant table

Each event type gets its own `@pytest.mark.parametrize` test function with descriptive IDs. This gives clear pytest output:

```
test_hook.py::test_stop_event[valid_text] PASSED
test_hook.py::test_stop_event[empty_message] PASSED
test_hook.py::test_pre_tool_use[bash_command] PASSED
test_hook.py::test_post_tool_use[bash_stderr_on_success] PASSED
test_hook.py::test_error_cases[malformed_json] PASSED
```

### 4. Raw JSON strings, not dicts

The helper takes a raw JSON string (not a dict) so we can test malformed JSON and empty input. For valid cases, use `json.dumps(payload_dict)`.

### 5. Assertion pattern

- **Sent:** `assert len(mock_send.messages) == 1` then `assert mock_send.messages[0] == expected_dict`
- **Not sent:** `assert len(mock_send.messages) == 0`

## Acceptance Criteria → Test Mapping

| AC | Requirement | Verification |
|---|---|---|
| AC1 | `cyrus2/tests/test_hook.py` exists with 12+ test cases | File exists, `pytest --collect-only` shows 17 items |
| AC2 | Tests cover event types: Stop, PreToolUse, PostToolUse, Notification, PreCompact | 5 test functions, one per event type + error group |
| AC3 | Tests verify `_send()` called with correct arguments | Every "sends" test asserts `mock_send.messages[0] == expected` |
| AC4 | Invalid JSON handling | `test_error_cases[malformed_json]` — _send not called |
| AC5 | Unknown event type handling | `test_error_cases[unknown_event]` — _send not called |
| AC6 | Empty/whitespace-only input handling | `test_error_cases[empty_input]` + `test_stop_event[whitespace_only]` |
| AC7 | All tests pass: `pytest tests/test_hook.py -v` | Exit code 0, 17 passed |

## Test Case Inventory

### `test_stop_event` — 3 cases

| ID | Input payload | Expected `_send` call | Rationale |
|---|---|---|---|
| `valid_text` | `{"hook_event_name": "Stop", "last_assistant_message": "Done.", "cwd": "/proj"}` | `{"event": "stop", "text": "Done.", "cwd": "/proj"}` | Basic Stop dispatch |
| `empty_message` | `{"hook_event_name": "Stop", "last_assistant_message": "", "cwd": "/proj"}` | NOT called | Empty text after strip → skip |
| `whitespace_only` | `{"hook_event_name": "Stop", "last_assistant_message": "   \n  ", "cwd": "/proj"}` | NOT called | Whitespace-only strips to empty → skip |

### `test_pre_tool_use` — 4 cases

| ID | Input payload | Expected `_send` call | Rationale |
|---|---|---|---|
| `bash_command` | `{"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": "/proj"}` | `{"event": "pre_tool", "tool": "Bash", "command": "ls -la", "cwd": "/proj"}` | Bash extracts `command` field |
| `edit_file` | `{"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "/src/app.py"}, "cwd": "/proj"}` | `{"event": "pre_tool", "tool": "Edit", "command": "/src/app.py", "cwd": "/proj"}` | Edit extracts `file_path` |
| `read_file` | `{"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "/readme.md"}, "cwd": "/proj"}` | `{"event": "pre_tool", "tool": "Read", "command": "/readme.md", "cwd": "/proj"}` | Read extracts `file_path` |
| `unknown_tool` | `{"hook_event_name": "PreToolUse", "tool_name": "WebSearch", "tool_input": {"query": "test"}, "cwd": "/proj"}` | `{"event": "pre_tool", "tool": "WebSearch", "command": "", "cwd": "/proj"}` | Unrecognized tool → empty command (still sends) |

### `test_post_tool_use` — 4 cases

| ID | Input payload | Expected `_send` call | Rationale |
|---|---|---|---|
| `bash_failure` | `{"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "make build"}, "tool_response": {"exit_code": 1, "stderr": "error: missing file"}, "cwd": "/proj"}` | `{"event": "post_tool", "tool": "Bash", "command": "make build", "exit_code": 1, "error": "error: missing file", "cwd": "/proj"}` | Bash failure (non-zero exit) sends error info |
| `bash_stderr_on_success` | `{"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "pip install foo"}, "tool_response": {"exit_code": 0, "stderr": "DEPRECATION: pip legacy"}, "cwd": "/proj"}` | `{"event": "post_tool", "tool": "Bash", "command": "pip install foo", "exit_code": 0, "error": "DEPRECATION: pip legacy", "cwd": "/proj"}` | Exit 0 + stderr still sends (condition is `exit_code != 0 or error`) |
| `bash_success` | `{"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "echo hi"}, "tool_response": {"exit_code": 0}, "cwd": "/proj"}` | NOT called | Bash success (exit 0, no stderr/error) → skip |
| `edit_file` | `{"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": "/src/app.py"}, "tool_response": {}, "cwd": "/proj"}` | `{"event": "post_tool", "tool": "Edit", "file_path": "/src/app.py", "cwd": "/proj"}` | Edit always sends with `file_path` |

### `test_notification` — 2 cases

| ID | Input payload | Expected `_send` call | Rationale |
|---|---|---|---|
| `valid_message` | `{"hook_event_name": "Notification", "message": "Task complete", "cwd": "/proj"}` | `{"event": "notification", "message": "Task complete", "cwd": "/proj"}` | Basic notification dispatch |
| `empty_message` | `{"hook_event_name": "Notification", "message": "", "cwd": "/proj"}` | NOT called | Empty message after strip → skip |

### `test_pre_compact` — 1 case

| ID | Input payload | Expected `_send` call | Rationale |
|---|---|---|---|
| `valid_trigger` | `{"hook_event_name": "PreCompact", "trigger": "manual", "cwd": "/proj"}` | `{"event": "pre_compact", "trigger": "manual", "cwd": "/proj"}` | Basic PreCompact dispatch |

### `test_error_cases` — 3 cases

| ID | Stdin content | Expected `_send` call | Rationale |
|---|---|---|---|
| `malformed_json` | `"not valid json {{"` | NOT called | `json.load` raises → caught at line 30 → `sys.exit(0)` |
| `unknown_event` | `{"hook_event_name": "FutureEvent", "cwd": "/proj"}` | NOT called | Falls through all elif branches → `sys.exit(0)` |
| `empty_input` | `""` | NOT called | Empty stdin → `json.load` raises → `sys.exit(0)` |

**Total: 17 test cases** (3 + 4 + 4 + 2 + 1 + 3) — exceeds the 12+ requirement.

## Implementation Steps

### Step 1: Verify test infrastructure exists

```bash
cd /home/daniel/Projects/barf/cyrus

# Check issue 018 artifacts
test -d cyrus2/tests/ && echo "OK: tests dir" || echo "MISSING: tests dir"
test -f cyrus2/tests/__init__.py && echo "OK: __init__" || echo "MISSING: __init__"
test -f cyrus2/tests/conftest.py && echo "OK: conftest" || echo "MISSING: conftest"
test -f cyrus2/pytest.ini && echo "OK: pytest.ini" || echo "MISSING: pytest.ini"
```

If `cyrus2/tests/` doesn't exist, create the minimal structure:

```bash
mkdir -p cyrus2/tests
touch cyrus2/tests/__init__.py
```

If `conftest.py` doesn't exist, create a minimal version with only `mock_send`:

```python
"""Minimal conftest — mock_send fixture for hook tests."""

import pytest


@pytest.fixture
def mock_send():
    class MockSend:
        def __init__(self):
            self.messages: list[dict] = []
        def __call__(self, msg: dict) -> None:
            self.messages.append(msg)
        def reset(self) -> None:
            self.messages.clear()
    return MockSend()
```

If `pytest.ini` doesn't exist **or** exists but is missing `pythonpath`, create/update it:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
pythonpath = ..
```

**Note:** Plan 018's `pytest.ini` does NOT include `pythonpath = ..`. If issue 018 was already built, the builder must add `pythonpath = ..` to the existing `pytest.ini`. This line is critical — it adds the cyrus root to `sys.path` so `from cyrus_hook import main` resolves correctly from inside `cyrus2/tests/`.

### Step 2: Create `cyrus2/tests/test_hook.py`

Write all 17 test cases. Structure:

```python
"""Tier 2 hook parsing tests for cyrus_hook.py.

Tests cover event dispatch for Stop, PreToolUse, PostToolUse, Notification,
PreCompact events, plus error handling for invalid JSON, unknown events,
and empty input.

Mocking strategy:
    - sys.stdin → StringIO with JSON payload
    - cyrus_hook._send → mock_send fixture (records dispatched dicts)
    - main() always calls sys.exit(0) → caught with pytest.raises(SystemExit)
"""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest

from cyrus_hook import main


def _run_hook(payload_json: str, mock_send) -> None:
    """Feed raw JSON to main() with _send patched."""
    with patch("sys.stdin", StringIO(payload_json)), \
         patch("cyrus_hook._send", mock_send):
        with pytest.raises(SystemExit):
            main()


# --- Stop event ---

@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param(
            {"hook_event_name": "Stop", "last_assistant_message": "Done.", "cwd": "/proj"},
            {"event": "stop", "text": "Done.", "cwd": "/proj"},
            id="valid_text",
        ),
        pytest.param(
            {"hook_event_name": "Stop", "last_assistant_message": "", "cwd": "/proj"},
            None,
            id="empty_message",
        ),
        pytest.param(
            {"hook_event_name": "Stop", "last_assistant_message": "   \n  ", "cwd": "/proj"},
            None,
            id="whitespace_only",
        ),
    ],
)
def test_stop_event(mock_send, payload: dict, expected: dict | None) -> None:
    _run_hook(json.dumps(payload), mock_send)
    if expected is None:
        assert len(mock_send.messages) == 0
    else:
        assert mock_send.messages == [expected]


# --- PreToolUse event ---
# (similar parametrize pattern for 4 cases — see Test Case Inventory)


# --- PostToolUse event ---
# (similar parametrize pattern for 4 cases — see Test Case Inventory)


# --- Notification event ---
# (similar parametrize pattern for 2 cases — see Test Case Inventory)


# --- PreCompact event ---
# (single case — see Test Case Inventory)


# --- Error cases ---
# (3 cases: malformed_json, unknown_event, empty_input — raw strings, not json.dumps)
```

**Key notes for the builder:**

- Every test function takes `mock_send` as first arg (conftest fixture).
- For "not sent" cases, use `expected = None` and assert `len(mock_send.messages) == 0`.
- For "sent" cases, assert `mock_send.messages == [expected_dict]` (exact match, single call).
- Error cases use raw strings for `payload_json`, not `json.dumps()`.
- The `_run_hook` helper handles the `SystemExit` catch so test bodies stay clean.
- The `test_error_cases` function should use a slightly different parametrize shape: `(stdin_content, expected)` where `stdin_content` is a raw string and `expected` is always `None`.

### Step 3: Run tests and iterate

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_hook.py -v
```

Expected: 17 tests pass. If any fail, trace the input through `main()` step by step and adjust expected values.

### Step 4: Verify test count

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_hook.py --collect-only -q | tail -1
```

Expected: `17 tests collected`

### Step 5: Run subset commands from acceptance criteria

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_hook.py::test_stop_event -v
pytest tests/test_hook.py -k "error or invalid" -v
pytest tests/test_hook.py -k "pre_tool" -v
pytest tests/test_hook.py -k "post_tool" -v
```

All should pass independently.

## Import Risk

`cyrus_hook.py` imports only stdlib modules (`json`, `os`, `socket`, `sys`). **No import risk** — unlike Tier 1 tests that import `cyrus_brain` (with heavy deps like torch/numpy), hook tests have zero external dependencies. This makes them the safest tier to run.

## Files Created/Modified

| File | Action | Description |
|---|---|---|
| `cyrus2/tests/test_hook.py` | **Create** | 17 parametrized test cases across 6 test functions |
| `cyrus2/tests/` directory | **Verify** | Must exist (from issue 018); create if missing |
| `cyrus2/tests/__init__.py` | **Verify** | Must exist (from issue 018); create if missing |
| `cyrus2/tests/conftest.py` | **Verify** | Must have `mock_send` fixture; create minimal if missing |
| `cyrus2/pytest.ini` | **Verify/Update** | Must have `pythonpath = ..`; create if missing, add line if present without it |
