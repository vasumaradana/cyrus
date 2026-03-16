# Implementation Plan: Fix file handle leak

**Issue**: [016-Fix-file-handle-leak](/home/daniel/Projects/barf/cyrus/issues/016-Fix-file-handle-leak.md)
**Created**: 2026-03-16
**PROMPT**: prompts/PROMPT_plan.md

## Gap Analysis

**Already exists**:
- `_open_companion_connection()` function at `cyrus_brain.py:1173` handles both Windows (TCP) and Unix (AF_UNIX) connections
- Caller `_submit_via_extension()` at line 1195 already wraps calls in try/except with `FileNotFoundError`, `ConnectionRefusedError`, `OSError`, and generic `Exception` handling
- One existing `with open(...)` usage in the file (line 50) for writing — establishes the pattern
- Test infrastructure exists using `unittest.TestCase` (see `cyrus2/tests/test_001_pyproject_config.py`)

**Needs building**:
- Replace bare `open(port_file).read().strip()` at line 1181 with `with` statement
- Add `FileNotFoundError` handling with diagnostic print (port file missing)
- Add `ValueError` handling with diagnostic print (invalid port number)
- Write acceptance-driven unit tests for the fixed function
- Create test file `cyrus2/tests/test_016_file_handle_leak.py`

## Approach

**Selected approach**: Wrap file read in `with` statement + targeted exception handling inside `_open_companion_connection`, then re-raise to let the existing caller decide recovery behavior.

**Why this approach**:
- The caller `_submit_via_extension` already handles `FileNotFoundError` gracefully (returns `False`, falls back to UIA). Re-raising preserves this behavior.
- Adding diagnostic `print(f"[Brain] ...")` messages inside `_open_companion_connection` provides visibility into *which* error occurred (port file missing vs invalid content), while the caller handles the recovery strategy.
- Using `print()` instead of `logging` — the entire `cyrus_brain.py` file uses `print(f"[Brain] ...")` for all output. No `logging` import exists. Matching existing codebase convention.
- `ValueError` for invalid port content would currently fall through to the generic `except Exception` in the caller with no useful message. Handling it specifically gives clear diagnostics.

## Rules to Follow

- No `.claude/rules/` files exist in the cyrus project
- Follow existing codebase patterns: `print(f"[Brain] ...")` for messaging, `with` for file handles

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Write tests | `python-pro` subagent | Python testing patterns, unittest mocking |
| Code review | `code-reviewer` subagent | Verify fix correctness |

## Prioritized Tasks

- [ ] Fix `cyrus_brain.py:1181` — wrap `open()` in `with` statement, add `FileNotFoundError` and `ValueError` handling with `print()` diagnostics, re-raise exceptions
- [ ] Write acceptance-driven tests in `cyrus2/tests/test_016_file_handle_leak.py` using `unittest.TestCase` + `unittest.mock` to verify: (a) valid port file reads correctly, (b) missing file raises `FileNotFoundError` with print output, (c) invalid content raises `ValueError` with print output, (d) file handle is always closed via mock verification
- [ ] Run tests and verify they pass

## Code Change Detail

### Current code (line 1181):
```python
port = int(open(port_file).read().strip())
```

### Fixed code:
```python
try:
    with open(port_file) as f:
        port = int(f.read().strip())
except FileNotFoundError:
    print(f"[Brain] Port file not found: {port_file}")
    raise
except ValueError:
    print(f"[Brain] Invalid port number in {port_file}")
    raise
```

**Key properties**:
- `with` ensures file handle closes in all paths (normal, `ValueError`, any other exception)
- `FileNotFoundError` logged with path for diagnostics, then re-raised (caller catches at line 1221)
- `ValueError` logged with path for diagnostics, then re-raised (caller catches at line 1227 generic handler)
- No change to return type, socket creation, or caller behavior
- No new imports needed

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| File handle wrapped in `with` statement | Verify `open()` return value has `__exit__` called (mock) | unit |
| Exception handling for missing/unreadable port file | Mock `open()` to raise `FileNotFoundError`, assert it propagates with print output | unit |
| Exception handling for invalid port number | Write non-numeric content, assert `ValueError` with print output | unit |
| Error messages logged appropriately | Capture stdout, verify `[Brain]` prefixed messages | unit |
| File handle always closes even on exception | Mock file object, verify `__exit__` called on `ValueError` path | unit |
| Existing port file reading functionality preserved | Write valid port number, verify correct `int` return and socket creation | unit |

## Validation (Backpressure)

- Tests: `python -m pytest cyrus2/tests/test_016_file_handle_leak.py -v` must pass
- Existing tests: `python -m pytest cyrus2/tests/ -v` must still pass
- Manual: verify `_open_companion_connection` function signature and behavior unchanged

## Files to Create/Modify

- `cyrus_brain.py` — fix file handle leak at line 1181 (replace 1 line with 7 lines)
- `cyrus2/tests/test_016_file_handle_leak.py` — new acceptance-driven test file (~80 lines)
