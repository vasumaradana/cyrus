# Plan 022: Write test_hook.py (Tier 2)

## Status: COMPLETE

## Gap Analysis

- **Exists**: `cyrus2/cyrus_hook.py` with `main()` entry point parsing 5 event types
- **Exists**: `cyrus2/tests/conftest.py` with `mock_send`, `mock_logger`, `mock_config` fixtures
- **Missing → Created**: `cyrus2/tests/test_hook.py` with 27 test cases

## Prioritized Tasks

- [x] Study `cyrus_hook.py` event dispatch logic (Stop, PreToolUse, PostToolUse, Notification, PreCompact)
- [x] Study `conftest.py` fixture API (mock_send, mock_logger, mock_config)
- [x] Write `cyrus2/tests/test_hook.py` with acceptance-driven tests
- [x] Validate: `pytest tests/test_hook.py -v` — all 27 tests pass

## Acceptance-Driven Tests

| Criterion | Test(s) | Status |
|-----------|---------|--------|
| 12+ test cases | 27 tests written | ✅ |
| Stop event coverage | `TestStopEvent` (4 tests) | ✅ |
| PreToolUse coverage | `TestPreToolUseEvent` (5 tests) | ✅ |
| PostToolUse coverage | `TestPostToolUseEvent` (6 tests) | ✅ |
| Notification coverage | `TestNotificationEvent` (3 tests) | ✅ |
| PreCompact coverage | `TestPreCompactEvent` (2 tests) | ✅ |
| _send() called correctly | `assert_called_once_with()` in every event test | ✅ |
| Invalid JSON handling | `test_malformed_json_exits_cleanly` | ✅ |
| Unknown event type | `test_unknown_event_type_does_not_send` | ✅ |
| Empty/whitespace input | `test_empty_input_exits_cleanly`, `test_whitespace_only_input_exits_cleanly` | ✅ |
| All tests pass | `pytest tests/test_hook.py -v` → 27 passed | ✅ |

## Files Created

- `cyrus2/tests/test_hook.py` (new) — 27 tests across 6 classes

## Implementation Notes

- `main()` calls `sys.exit(0)` on every path; tests catch `SystemExit` with `pytest.raises`
- Used `patch("cyrus_hook._send", mock_send)` + `patch("sys.stdin", StringIO(...))` helper
- `_run_main(payload, mock_send)` helper for dict payloads; `_run_main_raw(str, mock_send)` for invalid input
- `mock_send` fixture from `conftest.py` used as the patch target in all tests
- No real sockets opened in any test

## Validation

```
pytest tests/test_hook.py -v
# 27 passed in 0.02s
```

## Open Questions

None — implementation complete.
