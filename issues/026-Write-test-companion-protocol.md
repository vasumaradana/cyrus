# Issue 026: Write test_companion_protocol.py (Tier 4)

## Sprint
Sprint 3 — Test Suite

## Priority
Medium

## References
- [docs/14-test-suite.md — Tier 4: Integration Tests](../docs/14-test-suite.md#tier-4-integration-tests-heavier-mocking)
- `cyrus2/cyrus_companion.py` (IPC protocol, JSON line encoding/decoding)
- Extension communication protocol

## Description
Tier 4 integration tests for IPC (Inter-Process Communication) companion protocol. Mock TCP sockets to test JSON line protocol for message exchange between Cyrus and browser extension. Approximately 8 test cases covering message serialization, deserialization, socket I/O, and protocol error handling.

## Blocked By
- Issue 005 (cyrus_common.py foundation)
- Issue 018 (conftest.py fixtures)

## Acceptance Criteria
- [ ] `cyrus2/tests/test_companion_protocol.py` exists with 8+ test cases
- [ ] Tests verify message encoding to JSON lines (~2 cases): dict→JSON with newline
- [ ] Tests verify message decoding from JSON lines (~2 cases): JSON→dict parsing
- [ ] Tests verify socket communication (~2 cases): send/receive with mock sockets
- [ ] Tests verify protocol error handling (~2 cases): malformed JSON, connection loss, timeout
- [ ] All tests pass: `pytest tests/test_companion_protocol.py -v`

## Implementation Steps
1. Create `cyrus2/tests/test_companion_protocol.py`
2. Import companion protocol functions and socket mocking:
   ```python
   import json
   import socket
   from unittest.mock import Mock, MagicMock, patch
   from cyrus_companion import ProtocolEncoder, ProtocolDecoder  # or similar classes
   ```
3. Create conftest fixture for mock socket:
   ```python
   @pytest.fixture
   def mock_socket():
       sock = MagicMock(spec=socket.socket)
       sock.send.return_value = 100  # bytes sent
       sock.recv.return_value = b'{"type": "message"}\\n'
       return sock
   ```
4. Write encoding tests (~2 cases):
   - Dict with string fields → JSON line with trailing newline
   - Dict with nested objects → JSON serialized correctly
   - Special characters (quotes, newlines) → properly escaped
5. Write decoding tests (~2 cases):
   - JSON line with newline → parsed to dict
   - Multiple JSON lines in buffer → each parsed separately
   - Partial JSON (no newline) → buffered for next recv
6. Write socket send tests (~1 case):
   - send(message_dict) → socket.send() called with JSON bytes
   - Verify newline appended
   - Handle socket.send() partial writes
7. Write socket receive tests (~1 case):
   - recv() → parse JSON from socket.recv() buffer
   - Handle multiple messages in one recv() call
   - Verify socket.recv() called with buffer size
8. Write error handling tests (~2 cases):
   - Malformed JSON → decode error caught, logged, skipped
   - Socket disconnect (recv returns empty) → connection closed
   - Socket timeout exception → propagated or handled
   - Invalid message structure (missing required fields) → validation error
9. Use parametrize with (message_dict, expected_json_bytes) pairs for encoding
10. Use mock_socket fixture from conftest

## Files to Create/Modify
- `cyrus2/tests/test_companion_protocol.py` (new)
- Update `cyrus2/tests/conftest.py` to add mock_socket fixture if not present

## Testing
```bash
pytest cyrus2/tests/test_companion_protocol.py -v
pytest cyrus2/tests/test_companion_protocol.py::test_message_encoding -v
pytest cyrus2/tests/test_companion_protocol.py -k "decode or receive" -v
pytest cyrus2/tests/test_companion_protocol.py -k "error or malformed" -v
```
