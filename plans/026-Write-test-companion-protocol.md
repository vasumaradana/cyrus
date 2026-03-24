# Plan: Issue 026 — Write test_companion_protocol.py (Tier 4)

## Status: COMPLETE

## Gap Analysis

### What Exists
- `cyrus2/tests/test_companion_protocol.py` — **fully implemented**, 16 passing tests
- `cyrus2/tests/conftest.py` — shared fixtures including `mock_socket` (defined locally in the test file, not conftest)
- `cyrus2/cyrus_brain.py` — `_submit_via_extension()` and `_open_companion_connection()` are the functions under test

### What Was Needed
All required tests were already present and passing at time of build phase execution.

## Prioritized Tasks

- [x] Create `cyrus2/tests/test_companion_protocol.py`
- [x] Add `mock_socket` fixture (defined locally in the test file)
- [x] Write encoding tests (~2 cases) — `TestMessageEncoding` (4 test cases via parametrize)
- [x] Write decoding tests (~2 cases) — `TestMessageDecoding` (3 test cases)
- [x] Write socket communication tests (~2 cases) — `TestSocketCommunication` (3 test cases)
- [x] Write protocol error handling tests (~2 cases) — `TestProtocolErrorHandling` (5 test cases)
- [x] Write `_open_companion_connection` connection path test — `TestOpenCompanionConnection` (1 test case)
- [x] Verify ruff lint passes
- [x] Verify all tests pass

## Acceptance-Driven Tests

| Acceptance Criterion | Test(s) | Status |
|---|---|---|
| File exists with 8+ test cases | 16 tests total | ✅ |
| Encoding: dict → JSON line with newline | `TestMessageEncoding::test_simple_dict_encodes_to_json_line`, `test_nested_and_special_chars_encode_correctly[×3]` | ✅ |
| Decoding: JSON bytes → dict | `TestMessageDecoding::test_valid_json_line_decodes_to_dict`, `test_json_line_with_extra_fields_decodes_fully` | ✅ |
| Socket communication: send/receive | `TestSocketCommunication` (3 tests), `TestMessageDecoding::test_submit_via_extension_reads_until_newline` | ✅ |
| Error handling: malformed JSON, disconnect, timeout | `TestProtocolErrorHandling` (5 tests covering FileNotFoundError, ConnectionRefusedError, empty recv, bad JSON, TimeoutError) | ✅ |
| All tests pass | `pytest tests/test_companion_protocol.py -v` → 16 passed | ✅ |

## Test Structure

```
TestMessageEncoding          (4 tests via parametrize)
  test_simple_dict_encodes_to_json_line
  test_nested_and_special_chars_encode_correctly[×3]

TestMessageDecoding          (3 tests)
  test_valid_json_line_decodes_to_dict
  test_json_line_with_extra_fields_decodes_fully
  test_submit_via_extension_reads_until_newline  ← multi-chunk recv

TestSocketCommunication      (3 tests)
  test_sendall_called_with_json_line_bytes
  test_successful_extension_response_returns_true
  test_extension_error_response_returns_false

TestProtocolErrorHandling    (5 tests)
  test_file_not_found_returns_false
  test_connection_refused_returns_false
  test_socket_disconnect_mid_recv_returns_false
  test_malformed_json_response_returns_false
  test_socket_timeout_exception_returns_false

TestOpenCompanionConnection  (1 test, Unix only)
  test_unix_socket_path_uses_tmp_dir
```

## Verification Checklist

- [x] `ruff check tests/test_companion_protocol.py` — All checks passed
- [x] `pytest tests/test_companion_protocol.py -v` — 16 passed in 0.02s
- [x] `pytest tests/ -v` — 648 passed, 25 subtests passed (full suite green)

## Files Created/Modified

- `cyrus2/tests/test_companion_protocol.py` — **pre-existing, verified complete**
- `cyrus2/plans/026-Write-test-companion-protocol.md` — this plan (new)

## Open Questions

None — all acceptance criteria met, all tests green.
