# Implementation Plan: Add permission approval logging

**Issue**: [017-Add-permission-approval-logging](/home/daniel/Projects/barf/cyrus/issues/017-Add-permission-approval-logging.md)
**Created**: 2026-03-16
**PROMPT**: `.claude/prompts/plan.md`

## Gap Analysis

**Already exists**:
- PermissionWatcher class in `cyrus2/cyrus_common.py:691-1171` (issue references `cyrus_brain.py:876-914` — code was refactored to cyrus_common.py in Issue 005)
- Rich context at all approval decision points: tool name, command text, project name, utterance text, hook pre-arm info
- Print-based tracing at key points: `arm_from_hook()`, `handle_response()` allow/deny, poll-loop detection
- Logging design spec at `docs/16-logging-system.md`
- Test infrastructure in `cyrus2/tests/` using unittest, class-based, "AC:" docstrings
- Mock pattern for Windows-only dependencies (comtypes, uiautomation, pyautogui, pyperclip)

**Needs building**:
- `import logging` + logger in `cyrus_common.py` (not currently imported)
- Structured INFO-level `log.info()` calls at 4 security-relevant points in PermissionWatcher
- Sensitive data filtering (truncate commands, avoid full dialog text)
- Acceptance tests for all 9 acceptance criteria

**Dependency note**: Issue 009 (`cyrus_log.py` module) and Issue 010 (replace prints in brain) are both PLANNED/GROOMED but NOT YET IMPLEMENTED. This issue adds `logging.getLogger()` calls that work standalone — they will produce output once `setup_logging("cyrus")` is called at an entry point (by Issue 009). Until then, Python's default lastResort handler silently drops INFO-level messages, satisfying "no performance impact" and "existing functionality preserved."

## Approach

Add structured audit logging **alongside** existing `print()` statements (print replacement is Issue 010's scope). Use a dedicated logger `cyrus.permission` for security audit filtering.

**Why this approach**:
- Preserves existing console feedback behavior (acceptance criterion: "Existing PermissionWatcher functionality preserved")
- Enables targeted log filtering via `cyrus.permission` logger name (e.g., `CYRUS_LOG_LEVEL=INFO python cyrus_brain.py 2>&1 | grep "cyrus.permission"`)
- Works without `cyrus_log.py` — logger hierarchy means messages route correctly once setup_logging() exists
- No performance impact — `log.info()` with `%s` formatting is lazy (no string interpolation unless handler is active)
- Additive change — when Issue 010 replaces prints, these audit logs remain as the security trail

**4 logging injection points**:
1. `arm_from_hook()` — permission requested via Claude hook
2. `handle_response()` allow branch — permission APPROVED
3. `handle_response()` deny branch — permission DENIED
4. Poll loop — permission dialog detected via UIA

**Sensitive data protection**:
- Truncate command text to 120 chars (matching existing TTS truncation)
- Log tool name and project name (not sensitive)
- Log utterance text (short voice responses like "yes"/"allow" — not sensitive)
- Do NOT log full dialog UIA tree text

## Rules to Follow

- `.claude/skills/python-expert/AGENTS.md` — Type hints, docstrings, proper error handling, PEP 8
- `docs/16-logging-system.md` — `%s` format (no f-strings in log calls), `logging.getLogger()` hierarchy, INFO level for lifecycle/security events
- `pyproject.toml` Ruff config — E, F, W, I, UP, B rules; line-length 88; py310 target
- Test conventions from `test_007_command_handlers.py` — unittest, mock Windows deps in sys.modules, Path-based sys.path setup

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Implementation | Direct edit | ~15 lines added to cyrus_common.py |
| Tests | Direct write | Follow test_007 mock pattern for Windows deps |
| Lint check | `ruff check cyrus2/cyrus_common.py` | Verify Ruff compliance |
| Run tests | `python -m pytest cyrus2/tests/test_017_permission_logging.py -v` | Verify acceptance |

## Prioritized Tasks

- [x] Add `import logging` and `log = logging.getLogger("cyrus.permission")` to `cyrus2/cyrus_common.py` (near PermissionWatcher class, after imports)
  - Note: `logging` already imported; used `_perm_log = logging.getLogger("cyrus.permission")` to avoid conflict with existing `log` variable
- [x] Add `log.info()` in `arm_from_hook()` — log permission requested via hook with tool, truncated cmd, project
- [x] Add `log.info()` in `handle_response()` allow branch — log APPROVED with announced cmd, utterance, project
- [x] Add `log.info()` in `handle_response()` deny branch — log DENIED with announced cmd, utterance, project
- [x] Add `log.info()` in poll loop permission detection — log dialog detected with cmd_label, project
- [x] Create `cyrus2/tests/test_017_permission_logging.py` with acceptance-driven tests (25 tests, all passing)
- [x] Run Ruff lint + format check (clean)
- [x] Run all existing tests to verify no regression (369 passed, 0 failures)

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| PermissionWatcher logs permission type being detected | `test_poll_detection_logs_permission_type` — set watcher state, trigger poll detection path, capture log output, verify tool/cmd in message | unit |
| Permission name/description logged when "Allow" clicked | `test_allow_response_logs_permission_name` — arm watcher, call handle_response("yes"), verify log contains permission cmd | unit |
| Log includes timestamp and utterance that triggered approval | `test_allow_log_includes_utterance` — call handle_response("yes"), verify log contains utterance text | unit |
| Log includes dialog title or permission scope | `test_hook_arm_logs_tool_and_cmd` — call arm_from_hook("Bash", "rm -rf /tmp"), verify log contains "Bash" and cmd | unit |
| All log entries at INFO level | `test_all_log_entries_are_info_level` — capture LogRecords, verify all are level INFO | unit |
| No sensitive data exposed in logs | `test_command_truncated_in_log` — arm with 200-char cmd, verify log truncates to 120 chars | unit |
| Log entries sufficient for audit trail | `test_audit_trail_completeness` — exercise approve + deny paths, verify all fields present (timestamp, tool, cmd, utterance, project, decision) | integration |
| Existing functionality preserved | `test_handle_response_still_returns_true` — verify handle_response behavior unchanged (returns True on allow/deny) | unit |
| No performance impact from logging | `test_logging_with_no_handler` — verify no error/exception when no handler configured | unit |

**No cheating** — cannot claim done without all required tests passing.

## Validation (Backpressure)

- **Tests**: `python -m pytest cyrus2/tests/test_017_permission_logging.py -v` — all tests pass
- **Lint**: `ruff check cyrus2/cyrus_common.py` — no violations
- **Format**: `ruff format --check cyrus2/cyrus_common.py` — already formatted
- **Existing tests**: `python -m pytest cyrus2/tests/ -v` — all existing tests still pass (no regression)

## Files to Create/Modify

- `cyrus2/cyrus_common.py` — add `import logging`, logger, and 4 `log.info()` calls in PermissionWatcher (~15 lines added)
- `cyrus2/tests/test_017_permission_logging.py` — **create new** (~150-200 lines, acceptance tests)

## Log Message Specification

```python
# In arm_from_hook() — permission requested
log.info(
    "Permission requested: tool=%s cmd=%s project=%s",
    tool, cmd[:120], self.project_name,
)

# In handle_response() — APPROVED
log.info(
    "Permission APPROVED: cmd=%s utterance=%r project=%s",
    self._announced, text.strip(), self.project_name,
)

# In handle_response() — DENIED
log.info(
    "Permission DENIED: cmd=%s utterance=%r project=%s",
    self._announced, text.strip(), self.project_name,
)

# In poll loop — dialog detected
log.info(
    "Permission dialog detected: cmd=%s project=%s",
    cmd_label, self.project_name,
)
```

## Key Decisions

1. **Logger name `cyrus.permission`** (not `cyrus.common`): Enables targeted filtering for security audit — `grep "cyrus.permission"` extracts only permission events from mixed log output.

2. **Additive logging, not print replacement**: Issue 010 owns print→log migration. This issue adds new security audit entries alongside existing print() calls. Both can coexist.

3. **`%s` format, no f-strings**: Per `docs/16-logging-system.md` — avoids string interpolation cost when log level is filtered out.

4. **Command truncation at 120 chars**: Matches existing TTS truncation in arm_from_hook(). Prevents sensitive data leakage from long commands.

5. **File location correction**: Issue says `cyrus_brain.py:876-914` but PermissionWatcher was moved to `cyrus_common.py:691-1171` during Issue 005 (Extract shared code). Plan targets the actual location.

6. **Test approach**: Mock Windows UIA deps (following test_007 pattern), manually set PermissionWatcher into pending state, call methods, capture log output via `logging.Handler` with StringIO stream. Tests verify real log output, not mock call counts.
