# Plan 026: Write test_companion_protocol.py (Tier 4)

## Summary

Create `cyrus2/tests/test_companion_protocol.py` with 10 parametrized test cases covering the JSON line-delimited IPC protocol between Brain and the Companion Extension. Mock TCP/Unix sockets to test message encoding, decoding, send/receive cycles, and error handling. Tests are self-contained — they do **not** import from `cyrus_brain.py` (which has heavy Windows-only dependencies: `comtypes`, `pyautogui`, `uiautomation`). Instead, they test the protocol logic directly against the spec in `docs/06-networking-and-protocols.md`.

## Prerequisites

- **Issue 018** (state: PLANNED) — creates `cyrus2/tests/` directory, `conftest.py`, `pytest.ini`, and `requirements-dev.txt`. If not yet built when the builder runs, create the minimal structure (see Step 1).

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/tests/test_companion_protocol.py` | Does not exist | Create with 10 test cases |
| `cyrus2/tests/` directory | Does not exist (created by issue 018) | Verify exists; create if missing |
| `conftest.py` with `mock_socket` | Does not exist (created by issue 018) | Verify exists; add `mock_socket` fixture if missing |
| `pytest tests/test_companion_protocol.py -v` passes | No tests exist | All 10 cases green |

## Source Code Under Test

### Import Constraint

`cyrus_brain.py` imports `comtypes`, `pyautogui`, `pyperclip`, `pygetwindow`, `uiautomation`, and `websockets` at module level (lines 35–42). These are Windows-specific or heavy dependencies unavailable in the test environment. **Do not import `cyrus_brain`.**

Instead, the tests define lightweight protocol helper functions that replicate the exact encoding/decoding logic from `cyrus_brain.py` lines 1207–1216 and the extension's `handleConnection()` / `end()` (extension.ts lines 168–208).

### Protocol Specification (from docs/06-networking-and-protocols.md)

**Transport**: TCP on Windows (port from discovery file), Unix socket on Linux/macOS. Both use the same JSON protocol.

**Request (Brain → Extension):**
```json
{"text": "fix the bug in auth.py\n\n[Voice mode: ...]"}\n
```

**Response (Extension → Brain):**
```json
{"ok": true, "method": "enter-key-win32"}\n
```
Or on error:
```json
{"ok": false, "error": "Missing or empty text field"}\n
```

**Encoding**: `json.dumps(msg) + "\n"` → encode to UTF-8 bytes (`cyrus_brain.py:1209`)
**Sending**: `socket.sendall(encoded_bytes)` (`cyrus_brain.py:1209`)
**Receiving**: Loop `socket.recv(4096)` until `b"\n"` found in buffer (`cyrus_brain.py:1210–1215`)
**Decoding**: `json.loads(raw.decode("utf-8").strip())` (`cyrus_brain.py:1216`)

### Brain Client Functions (reference — not imported)

**`_submit_via_extension(text)`** — `cyrus_brain.py:1195–1229`:
1. Sanitize workspace name: `re.sub(r'[^\w\-]', '_', proj or "default")[:40]`
2. Open socket via `_open_companion_connection(safe)`
3. Send: `s.sendall((json.dumps({"text": text}) + "\n").encode("utf-8"))`
4. Receive loop: buffer `s.recv(4096)` until `b"\n"` found (or empty chunk = disconnect)
5. Parse: `json.loads(raw.decode("utf-8").strip())`
6. Return `True` if `result.get("ok")` else `False`
7. Catch: `FileNotFoundError` → `False`, `ConnectionRefusedError`/`OSError` → `False`, generic `Exception` → `False`

**`_open_companion_connection(safe)`** — `cyrus_brain.py:1173–1192`:
- Windows: read port from file, TCP connect to `127.0.0.1:{port}`, timeout=10
- Unix: connect to `/tmp/cyrus-companion-{safe}.sock`, timeout=10

### Extension Server (reference — TypeScript, not importable)

**`handleConnection(socket)`** — `extension.ts:168–201`:
- Buffers incoming data until `\n`
- Parses JSON, validates `text` field is non-empty string
- On invalid JSON: replies `{"ok": false, "error": "Invalid JSON"}\n`
- On missing/empty text: replies `{"ok": false, "error": "Missing or empty text field"}\n`
- On success: calls `submitText()`, replies with result

**`end(socket, result)`** — `extension.ts:204–208`:
- `socket.end(JSON.stringify(result) + '\n')`

## Design Decisions

### 1. Self-contained protocol helpers

Define four small functions in the test file that match the Brain's protocol logic exactly:

```python
def encode_message(msg: dict) -> bytes:
    """Encode dict → JSON line bytes. Matches cyrus_brain.py:1209."""
    return (json.dumps(msg) + "\n").encode("utf-8")

def decode_message(data: bytes) -> dict:
    """Decode JSON line bytes → dict. Matches cyrus_brain.py:1216."""
    return json.loads(data.decode("utf-8").strip())

def send_message(sock: socket.socket, msg: dict) -> None:
    """Send JSON line over socket. Matches cyrus_brain.py:1209."""
    sock.sendall(encode_message(msg))

def recv_message(sock: socket.socket, bufsize: int = 4096) -> dict:
    """Receive JSON line from socket. Matches cyrus_brain.py:1210-1216."""
    raw = b""
    while b"\n" not in raw:
        chunk = sock.recv(bufsize)
        if not chunk:
            raise ConnectionError("Connection closed before complete message")
        raw += chunk
    return json.loads(raw.decode("utf-8").strip())
```

These are tested directly, then used by higher-level socket I/O tests.

### 2. `mock_socket` fixture

A `MagicMock(spec=socket.socket)` with configurable `send`, `sendall`, and `recv` behavior. Add to `conftest.py` (or create inline if conftest is missing):

```python
@pytest.fixture
def mock_socket():
    sock = MagicMock(spec=socket.socket)
    sock.recv.return_value = b'{"ok": true, "method": "enter-key"}\n'
    sock.sendall.return_value = None
    return sock
```

### 3. Multi-chunk recv simulation

For tests that verify buffering, configure `mock_socket.recv.side_effect` with a list of partial chunks. The `recv_message()` loop must accumulate them until `\n` is found.

### 4. No import of cyrus_brain

Tests are 100% stdlib — `json`, `socket`, `unittest.mock`. Zero external dependencies, zero import risk. The protocol helpers are verified against the spec, not against the implementation (which can't be imported).

### 5. Parametrize encoding/decoding, separate functions for socket/error tests

Encoding and decoding are parametrized with `(input, expected)` pairs. Socket I/O and error handling get individual test functions since they require different mock setups.

## Acceptance Criteria → Test Mapping

| AC | Requirement | Verification |
|---|---|---|
| AC1 | `cyrus2/tests/test_companion_protocol.py` exists with 8+ test cases | File exists, `pytest --collect-only` shows 10 items |
| AC2 | Tests verify message encoding to JSON lines (~2 cases) | `test_encode_message` — 3 parametrized cases |
| AC3 | Tests verify message decoding from JSON lines (~2 cases) | `test_decode_message` — 2 parametrized cases |
| AC4 | Tests verify socket communication (~2 cases) | `test_send_message` + `test_recv_message` + `test_recv_multi_chunk` |
| AC5 | Tests verify protocol error handling (~2 cases) | `test_recv_malformed_json` + `test_recv_connection_closed` + `test_recv_socket_timeout` |
| AC6 | All tests pass: `pytest tests/test_companion_protocol.py -v` | Exit code 0, 10 passed |

## Test Case Inventory

### `test_encode_message` — 3 cases (parametrized)

| ID | Input dict | Expected bytes | Rationale |
|---|---|---|---|
| `simple_text` | `{"text": "hello"}` | `b'{"text": "hello"}\n'` | Basic Brain→Extension request |
| `nested_object` | `{"text": "fix bug", "meta": {"voice": True}}` | `b'{"text": "fix bug", "meta": {"voice": true}}\n'` | Nested dict serialized correctly, Python `True` → JSON `true` |
| `special_chars` | `{"text": "line1\nline2\t\"quoted\""}` | JSON-escaped `\n`, `\t`, `\"` in bytes with trailing newline | Special characters properly escaped inside JSON |

### `test_decode_message` — 2 cases (parametrized)

| ID | Input bytes | Expected dict | Rationale |
|---|---|---|---|
| `success_response` | `b'{"ok": true, "method": "enter-key-win32"}\n'` | `{"ok": True, "method": "enter-key-win32"}` | Standard Extension→Brain success reply |
| `error_response` | `b'{"ok": false, "error": "Missing or empty text field"}\n'` | `{"ok": False, "error": "Missing or empty text field"}` | Standard Extension→Brain error reply |

### `test_send_message` — 1 case

| Input | Assertion | Rationale |
|---|---|---|
| `send_message(mock_socket, {"text": "hello"})` | `mock_socket.sendall.assert_called_once_with(b'{"text": "hello"}\n')` | Verify sendall called with correctly encoded bytes |

### `test_recv_message` — 1 case

| Mock setup | Expected result | Rationale |
|---|---|---|
| `mock_socket.recv.return_value = b'{"ok": true, "method": "enter-key"}\n'` | `{"ok": True, "method": "enter-key"}` | Single recv returns complete message |

### `test_recv_multi_chunk` — 1 case

| Mock setup | Expected result | Rationale |
|---|---|---|
| `mock_socket.recv.side_effect = [b'{"ok": tr', b'ue, "method":', b' "enter-key"}\n']` | `{"ok": True, "method": "enter-key"}` | Message arrives in 3 chunks; recv_message buffers until `\n` |

### `test_recv_malformed_json` — 1 case

| Mock setup | Expected behavior | Rationale |
|---|---|---|
| `mock_socket.recv.return_value = b'not valid json\n'` | `pytest.raises(json.JSONDecodeError)` | Extension sends garbage; decoder raises |

### `test_recv_connection_closed` — 1 case

| Mock setup | Expected behavior | Rationale |
|---|---|---|
| `mock_socket.recv.return_value = b''` | `pytest.raises(ConnectionError, match="Connection closed")` | Empty recv = peer closed socket before sending complete message |

### `test_recv_socket_timeout` — 1 case (bonus — exceeds 8 minimum)

| Mock setup | Expected behavior | Rationale |
|---|---|---|
| `mock_socket.recv.side_effect = socket.timeout("timed out")` | `pytest.raises(socket.timeout)` | Socket timeout propagates (Brain sets 10s timeout) |

**Total: 10 test cases** (3 + 2 + 1 + 1 + 1 + 1 + 1 + 1 = 11 parametrized inputs across 8 test functions) — exceeds the 8+ requirement.

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

If `conftest.py` doesn't exist, create a minimal version with `mock_socket`:

```python
"""Minimal conftest — shared fixtures for Cyrus protocol tests."""

import socket
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_socket():
    """MagicMock socket with default success response."""
    sock = MagicMock(spec=socket.socket)
    sock.recv.return_value = b'{"ok": true, "method": "enter-key"}\n'
    sock.sendall.return_value = None
    return sock
```

If `conftest.py` exists but lacks `mock_socket`, add the fixture.

If `pytest.ini` doesn't exist, create it:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

**Note:** Unlike plan 022 (which needs `pythonpath = ..` to import `cyrus_hook.py`), this test file does NOT import any project modules. No `pythonpath` needed. However, if `pytest.ini` already exists with `pythonpath = ..` (from issue 022), leave it.

### Step 2: Create `cyrus2/tests/test_companion_protocol.py`

Write all 10 test cases. Structure:

```python
"""Tier 4 integration tests for the Companion Extension IPC protocol.

Tests cover JSON line encoding/decoding, socket send/receive, and protocol
error handling for the Brain <-> Extension communication channel.

Protocol spec: docs/06-networking-and-protocols.md § Brain <-> Companion Extension
Implementation reference: cyrus_brain.py:1195-1229 (_submit_via_extension)

These tests do NOT import cyrus_brain (heavy Windows-only dependencies).
Instead, they test the protocol logic directly via lightweight helpers that
replicate the exact encoding/decoding behavior.

Mocking strategy:
    - socket.socket → MagicMock(spec=socket.socket) via mock_socket fixture
    - No network I/O — all socket calls are mocked
"""

from __future__ import annotations

import json
import socket
from unittest.mock import MagicMock

import pytest


# ── Protocol helpers (match cyrus_brain.py encoding/decoding exactly) ─────────


def encode_message(msg: dict) -> bytes:
    """Encode dict → JSON line bytes. Matches cyrus_brain.py:1209."""
    return (json.dumps(msg) + "\n").encode("utf-8")


def decode_message(data: bytes) -> dict:
    """Decode JSON line bytes → dict. Matches cyrus_brain.py:1216."""
    return json.loads(data.decode("utf-8").strip())


def send_message(sock: socket.socket, msg: dict) -> None:
    """Send JSON line over socket. Matches cyrus_brain.py:1209."""
    sock.sendall(encode_message(msg))


def recv_message(sock: socket.socket, bufsize: int = 4096) -> dict:
    """Receive JSON line from socket with buffering. Matches cyrus_brain.py:1210-1216."""
    raw = b""
    while b"\n" not in raw:
        chunk = sock.recv(bufsize)
        if not chunk:
            raise ConnectionError("Connection closed before complete message")
        raw += chunk
    return json.loads(raw.decode("utf-8").strip())


# ── Encoding tests ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("msg", "expected"),
    [
        pytest.param(
            {"text": "hello"},
            b'{"text": "hello"}\n',
            id="simple_text",
        ),
        pytest.param(
            {"text": "fix bug", "meta": {"voice": True}},
            b'{"text": "fix bug", "meta": {"voice": true}}\n',
            id="nested_object",
        ),
        pytest.param(
            {"text": 'line1\nline2\t"quoted"'},
            json.dumps({"text": 'line1\nline2\t"quoted"'}).encode("utf-8") + b"\n",
            id="special_chars",
        ),
    ],
)
def test_encode_message(msg: dict, expected: bytes) -> None:
    result = encode_message(msg)
    assert result == expected
    assert result.endswith(b"\n")


# ── Decoding tests ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param(
            b'{"ok": true, "method": "enter-key-win32"}\n',
            {"ok": True, "method": "enter-key-win32"},
            id="success_response",
        ),
        pytest.param(
            b'{"ok": false, "error": "Missing or empty text field"}\n',
            {"ok": False, "error": "Missing or empty text field"},
            id="error_response",
        ),
    ],
)
def test_decode_message(data: bytes, expected: dict) -> None:
    result = decode_message(data)
    assert result == expected


# ── Socket send test ──────────────────────────────────────────────────────────


def test_send_message(mock_socket) -> None:
    send_message(mock_socket, {"text": "hello"})
    mock_socket.sendall.assert_called_once_with(b'{"text": "hello"}\n')


# ── Socket receive tests ─────────────────────────────────────────────────────


def test_recv_message(mock_socket) -> None:
    mock_socket.recv.return_value = b'{"ok": true, "method": "enter-key"}\n'
    result = recv_message(mock_socket)
    assert result == {"ok": True, "method": "enter-key"}
    mock_socket.recv.assert_called_once_with(4096)


def test_recv_multi_chunk(mock_socket) -> None:
    mock_socket.recv.side_effect = [
        b'{"ok": tr',
        b'ue, "method":',
        b' "enter-key"}\n',
    ]
    result = recv_message(mock_socket)
    assert result == {"ok": True, "method": "enter-key"}
    assert mock_socket.recv.call_count == 3


# ── Error handling tests ─────────────────────────────────────────────────────


def test_recv_malformed_json(mock_socket) -> None:
    mock_socket.recv.return_value = b"not valid json\n"
    with pytest.raises(json.JSONDecodeError):
        recv_message(mock_socket)


def test_recv_connection_closed(mock_socket) -> None:
    mock_socket.recv.return_value = b""
    with pytest.raises(ConnectionError, match="Connection closed"):
        recv_message(mock_socket)


def test_recv_socket_timeout(mock_socket) -> None:
    mock_socket.recv.side_effect = socket.timeout("timed out")
    with pytest.raises(socket.timeout):
        recv_message(mock_socket)
```

**Key notes for the builder:**

- All protocol helpers are defined at the top of the test file — no external imports needed.
- The `mock_socket` fixture comes from conftest (Step 1). Each test that modifies `.recv` does so locally.
- `test_encode_message` verifies both content equality AND trailing newline.
- `test_recv_multi_chunk` sets `recv.side_effect` to a list — each call pops the next chunk.
- Error tests use `pytest.raises` with match strings where appropriate.
- The `special_chars` encoding test uses `json.dumps()` to compute expected bytes dynamically, avoiding hand-escaping mistakes.

### Step 3: Run tests and iterate

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_companion_protocol.py -v
```

Expected: 10 tests pass (3 encoding + 2 decoding + 1 send + 2 recv + 3 error). If any fail, trace through the protocol logic step by step and adjust.

### Step 4: Verify test count

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_companion_protocol.py --collect-only -q | tail -1
```

Expected: `10 tests collected`

### Step 5: Run subset commands from acceptance criteria

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_companion_protocol.py::test_encode_message -v
pytest tests/test_companion_protocol.py -k "decode or receive" -v
pytest tests/test_companion_protocol.py -k "error or malformed" -v
```

All should pass independently.

## Import Risk

Zero. All imports are stdlib: `json`, `socket`, `unittest.mock`. No external dependencies at all. This is the safest approach — avoids the `cyrus_brain.py` import chain entirely.

## Roundtrip Verification

The encode/decode tests together verify roundtrip integrity:
- `encode_message(msg)` produces bytes, `decode_message(those_bytes)` returns the original `msg`.
- The send/recv tests verify this works over a mock socket.
- The multi-chunk test proves the buffering loop handles fragmentation.

This matches the real behavior: Brain encodes + sendall, Extension recv + decodes (and vice versa for the response).

## Files Created/Modified

| File | Action | Description |
|---|---|---|
| `cyrus2/tests/test_companion_protocol.py` | **Create** | 10 test cases across 8 test functions |
| `cyrus2/tests/` directory | **Verify** | Must exist (from issue 018); create if missing |
| `cyrus2/tests/__init__.py` | **Verify** | Must exist (from issue 018); create if missing |
| `cyrus2/tests/conftest.py` | **Verify/Update** | Must have `mock_socket` fixture; create minimal or add fixture if missing |
| `cyrus2/pytest.ini` | **Verify** | Must exist (from issue 018); create if missing |
