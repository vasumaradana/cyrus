---
id=007-Break-up-execute-cyrus-command-into-dispatch-table
title=Issue 007: Break up execute_cyrus_command into dispatch table
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=59225
total_output_tokens=8
total_duration_seconds=154
total_iterations=1
run_count=1
---

# Issue 007: Break up execute_cyrus_command into dispatch table

## Sprint
Cyrus 2.0 Rewrite — Sprint 1

## Priority
Critical

## References
- docs/12-code-audit.md — C1 (god functions, 678–776 lines)

## Description
`_execute_cyrus_command()` is a 678–776 line monolith with deeply nested if/elif chains handling 6+ command types. Impossible to test, debug, or extend in isolation. Refactor into a dispatch table mapping command names to small, testable handler functions.

## Blocked By
- Issue 005 (Extract shared code first, so function exists in cyrus_common.py)

## Acceptance Criteria
- [ ] `_execute_cyrus_command()` refactored into dispatch dict `_COMMAND_HANDLERS`
- [ ] Each handler is < 50 lines and handles a single command type
- [ ] All original behavior preserved (no logic changes)
- [ ] Unit tests added for each handler (Issue 009)
- [ ] Complexity reduced: cyclomatic complexity per function < 5
- [ ] Error handling improved: specific exceptions logged instead of silently swallowed

## Implementation Steps

1. **Identify all command types** in current `_execute_cyrus_command()` (cyrus_brain.py:331–1107):
   - `"switch_project"` / `"switch to"` — lock routing to a project
   - `"unlock"` / `"auto"` — release project lock
   - `"which_project"` — report current active project
   - `"last_message"` — replay last response
   - `"pause"` / `"listening"` — toggle listening state
   - Any regex-based fast commands (Issue 006 extracts `_fast_command()`)

2. **Create handler functions** in `cyrus2/cyrus_common.py` (or `cyrus_brain.py` if brain-specific):
   ```python
   def _handle_switch_project(text, alias_map, state):
       """Parse 'switch to [name]' and lock routing to that project."""
       # Extracted logic from old function
       pass

   def _handle_unlock(state):
       """Release project lock, return to auto-follow mode."""
       pass

   def _handle_which_project(state, tts_queue):
       """Report current active project."""
       pass

   def _handle_last_message(state, tts_queue):
       """Replay the last response in active session."""
       pass

   def _handle_pause(state):
       """Toggle listening pause state."""
       pass
   ```

3. **Create the dispatch table** in `cyrus_common.py` or `cyrus_brain.py`:
   ```python
   _COMMAND_HANDLERS = {
       "switch_project": _handle_switch_project,
       "unlock": _handle_unlock,
       "which_project": _handle_which_project,
       "last_message": _handle_last_message,
       "pause": _handle_pause,
   }
   ```

4. **Refactor `_execute_cyrus_command()`** to use the dispatch table:
   ```python
   def _execute_cyrus_command(cmd, args, state, tts_queue):
       """Execute a Cyrus command using dispatch table."""
       handler = _COMMAND_HANDLERS.get(cmd)
       if not handler:
           return False  # Not a Cyrus command
       try:
           handler(args, state, tts_queue)
           return True
       except Exception as e:
           logging.exception(f"Error executing command '{cmd}': {e}")
           return False
   ```

5. **Extract parameter state object** that handlers receive:
   - Should include: active_project, aliases, conversation_active, etc.
   - Handlers modify state via passed-in dict or by returning new state
   - Avoids global variable access

6. **Add logging** to each handler:
   - Log command received: `logging.debug(f"Executing {cmd} with args {args}")`
   - Log result: `logging.info(f"Command {cmd} completed successfully")`
   - Log errors: `logging.exception()` instead of silent fail

7. **Update call site** in routing logic:
   - Replace long if/elif chain with: `_execute_cyrus_command(cmd, args, state, tts_queue)`

8. **Remove** the old monolithic `_execute_cyrus_command()` definition

## Files to Create/Modify
- Modify: `cyrus2/cyrus_common.py` (add handler functions and dispatch table)
- Modify: `cyrus2/cyrus_brain.py` (use dispatch table instead of inline logic)
- Create: `cyrus2/test_command_handlers.py` (unit tests, Issue 009)

## Testing
- Unit test each handler independently: `pytest test_command_handlers.py::test_handle_switch_project`
- Integration test: utterance → command detection → handler execution → state change
- Verify no regression: all 6 command types still work correctly
- Run linter: `pylint cyrus_common.py` (no new issues)
- Check cyclomatic complexity: each handler < 5 (use `radon cc -a`)

## Stage Log

### GROOMED — 2026-03-11 18:09:38Z

- **From:** NEW
- **Duration in stage:** 154s
- **Input tokens:** 59,225 (final context: 59,225)
- **Output tokens:** 8
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
