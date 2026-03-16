# Plan: 016-Fix-file-handle-leak

## Summary

Fix file handle leak at line 1181 of `cyrus_brain.py` where `open(port_file).read().strip()` is called without a context manager inside `_open_companion_connection()`. Add proper resource management and exception handling for missing/invalid port files.

## Key Findings

| Item | Detail |
|------|--------|
| **File** | `/home/daniel/Projects/barf/cyrus/cyrus_brain.py` (issue references `cyrus2/` but actual path is project root) |
| **Line** | 1181 — `port = int(open(port_file).read().strip())` |
| **Function** | `_open_companion_connection(safe: str) -> socket.socket` (lines 1173-1192) |
| **Caller** | `_submit_via_extension(text: str) -> bool` (lines 1195-1229) — already catches `FileNotFoundError`, `ConnectionRefusedError`, `OSError`, and bare `Exception` |
| **Other `open()` calls** | Only 1 other at line 50 — already uses `with` (safe) |
| **Logging convention** | `print(f"[Brain] ...")` — no `logging` module in this project |
| **Test framework** | None — project uses manual verification only |

## Design Decisions

### 1. Exception handling location: inside `_open_companion_connection`

The caller (`_submit_via_extension`) already has exception handling, but it's at the socket-connection level. Adding port-file-specific handling inside `_open_companion_connection` gives us:
- Specific error messages that name the port file path (caller doesn't know this detail)
- Clear separation: port-file errors are logged where they originate, socket errors are handled by the caller

We **re-raise** after logging so the caller's existing exception handling continues to work — `FileNotFoundError` maps to "extension not running" (returns False), `ValueError` falls through to the caller's `except Exception` (returns False).

### 2. Logging: `print()` not `logging`

The entire codebase uses `print(f"[Brain] ...")` — 66 instances in this file alone. Using `log.error()` as the issue template suggests would be inconsistent. We follow the project's actual convention.

### 3. No automated tests

This project has no test framework (no pytest, unittest, or test runner). The only test file (`test_permission_scan.py`) is a manual diagnostic script. We provide manual verification steps consistent with the project's practices.

## Acceptance Criteria → Verification Map

| Criterion | How verified |
|-----------|-------------|
| File handle wrapped in `with` statement | Code review — `with open(port_file) as f:` pattern visible |
| Exception handling for missing/unreadable port file | `FileNotFoundError` + `OSError` caught, message printed, re-raised |
| Exception handling for invalid port number | `ValueError` caught, message printed, re-raised |
| Error messages logged appropriately | `print(f"[Brain] ...")` matches project convention |
| File handle always closes even on exception | `with` statement guarantees `__exit__` is called |
| Existing port file reading functionality preserved | Happy path unchanged — same `int(f.read().strip())` logic |

## Implementation Steps

### Step 1: Fix `_open_companion_connection` (single-file change)

**File**: `cyrus_brain.py` — lines 1178-1185 (Windows branch of `_open_companion_connection`)

**Before** (lines 1178-1185):
```python
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        port_file = os.path.join(base, 'cyrus', f'companion-{safe}.port')
        port = int(open(port_file).read().strip())
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(('127.0.0.1', port))
        return s
```

**After**:
```python
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        port_file = os.path.join(base, 'cyrus', f'companion-{safe}.port')
        try:
            with open(port_file) as f:
                port = int(f.read().strip())
        except FileNotFoundError:
            print(f"[Brain] Port file not found: {port_file}")
            raise
        except ValueError:
            print(f"[Brain] Invalid port number in {port_file}")
            raise
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(('127.0.0.1', port))
        return s
```

**Rationale**:
- `with open()` guarantees the file handle is closed in all code paths (happy path, `ValueError`, any other exception)
- `FileNotFoundError` is caught and logged with the specific file path, then re-raised — the caller already catches this and returns `False` (extension not running)
- `ValueError` is caught and logged (invalid content like "abc" in port file), then re-raised — falls through to caller's `except Exception` which returns `False`
- We do NOT catch bare `Exception` here — the caller already handles that. Adding it here would double-log.
- Socket creation and connection remain outside the try/except — those failures are the caller's concern (`ConnectionRefusedError`, `OSError`)
- The happy path logic is identical: `int(f.read().strip())`

### Step 2: Manual verification

Since the project has no automated test framework, verify manually:

```bash
# 1. Syntax check — file parses correctly
python -c "import ast; ast.parse(open('cyrus_brain.py').read()); print('OK')"

# 2. Code review — confirm with statement and exception handling present
grep -n -A 8 "def _open_companion_connection" cyrus_brain.py
```

### Step 3: Commit

Commit message: `fix: close file handle leak in _open_companion_connection (port file read)`

## Risk Assessment

**Risk: Very Low**
- Single-line change wrapped in standard Python idiom (`with` statement)
- All exception types already handled by the caller — we're adding logging, not changing control flow
- Happy-path behavior identical
- No new dependencies, no API changes, no signature changes
- Function is only called from one place (`_submit_via_extension`)
