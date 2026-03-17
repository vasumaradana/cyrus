# Plan 021: Write test_fast_command.py (Tier 1)

## Status
**COMPLETE** — all tasks done, all tests passing.

## Gap Analysis

| What exists | What needs building |
|---|---|
| `_fast_command()` in `cyrus_common.py` — but returns complex nested dict `{"action": "command", "command": {"type": "..."}}` | Refactored `_fast_command()` returning flat `{"command": "<type>", ...params}` |
| No duration parsing for pause | "pause for N seconds" → `{"command": "pause", "duration": N}` |
| No password parsing for unlock | "unlock password" → `{"command": "unlock", "password": "..."}` |
| "switch_project" / "rename_session" type names | Simplified to "switch" / "rename" |
| No `test_fast_command.py` | `cyrus2/tests/test_fast_command.py` with 25+ cases |

## Prioritized Tasks

- [x] Refactor `_fast_command()` in `cyrus_common.py` to return flat dict
- [x] Add duration parsing for pause ("pause for N seconds")
- [x] Add password parsing for unlock ("unlock password")
- [x] Rename command types: "switch_project"→"switch", "rename_session"→"rename"
- [x] Rename field "new"→"name" in rename commands
- [x] Update `cyrus_brain.py` routing code for new flat dict format
- [x] Update `_COMMAND_HANDLERS` keys in `cyrus_brain.py`
- [x] Update `_handle_rename_session` to use `cmd.get("name")`
- [x] Make `_execute_cyrus_command` return spoken text (for conversation mode)
- [x] Restore `_conversation_active.set()` in routing (satisfies test_013)
- [x] Update `test_007_command_handlers.py` for new command type names
- [x] Create `cyrus2/tests/test_fast_command.py` with 25+ test cases
- [x] Fix ruff lint issues (line length, import sorting)

## Acceptance-Driven Tests

| Criterion | Test(s) | Status |
|---|---|---|
| 25+ test cases | Counted: 48 test methods across 7 classes | ✅ |
| pause happy + edge + invalid | `TestPauseCommand` (8 tests) | ✅ |
| unlock happy + edge | `TestUnlockCommand` (6 tests) | ✅ |
| which_project variations | `TestWhichProjectCommand` (4 tests) | ✅ |
| last_message variations | `TestLastMessageCommand` (4 tests) | ✅ |
| switch happy + edge + invalid | `TestSwitchCommand` (7 tests) | ✅ |
| rename happy + edge + invalid | `TestRenameCommand` (8 tests) | ✅ |
| Non-commands return None | `TestNonCommandStrings` (11 tests) | ✅ |
| All tests pass | `uv run pytest tests/` → 530 passed | ✅ |

## Files Modified

- `cyrus2/cyrus_common.py` — refactored `_fast_command()`
- `cyrus2/cyrus_brain.py` — updated routing, handlers, `_COMMAND_HANDLERS`, `_execute_cyrus_command`
- `cyrus2/tests/test_007_command_handlers.py` — updated command type names and field names

## Files Created

- `cyrus2/tests/test_fast_command.py` — 48 test cases for `_fast_command()`

## Key Decisions

1. **New return format**: `{"command": "<type>", ...params}` — flat dict, no nested `{"action": ..., "command": {...}}` wrapping
2. **Routing refactor**: `cyrus_brain.py` routing changed from action-based dispatch (`decision["action"]`) to null-check pattern (`if fast is not None`)
3. **Conversation mode**: `_execute_cyrus_command` now returns the spoken text so the routing layer can decide to call `_conversation_active.set()` for question responses
4. **`cyrus_server.py` not changed**: It has its own local `_fast_command` that still uses the old format because changing the server protocol requires knowing the client side

## Validation

```bash
cd cyrus2 && uv run pytest tests/ -v
# 530 passed, 0 warnings, 25 subtests passed

uv run ruff check tests/test_fast_command.py tests/test_007_command_handlers.py cyrus_common.py cyrus_brain.py
# All checks passed!
```

## Post-completion fix

After marking complete, a `RuntimeWarning: coroutine '_send' was never awaited` warning was
found during validation. Root cause: `test_007_command_handlers.py` pause tests call
`_handle_pause()` which evaluates `_send(...)` (creating a coroutine) before passing it to the
mocked `run_coroutine_threadsafe`. The mock discards the coroutine without awaiting → GC emits
warning during a later test.

Fix: added `_close_coro_side_effect()` helper in `test_007_command_handlers.py` and applied it
as `side_effect=_close_coro_side_effect` to all three `TestHandlePause` patch calls. All
530 tests now pass with 0 warnings.
