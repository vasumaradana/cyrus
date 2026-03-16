# Plan 017: Add permission approval logging

## Summary

Add structured INFO-level logging to the `PermissionWatcher` class in `cyrus_brain.py` so every auto-approved (or denied) permission produces an audit-quality log entry. The core change is: (a) store the tool name and command as instance variables when a permission becomes pending, and (b) emit rich `log.info()` calls in `handle_response()` that include tool, command, utterance, project, and outcome.

## Dependencies

- **Issue 009** (Create `cyrus2/cyrus_log.py`) — must be COMPLETE. Provides `setup_logging()`.
- **Issue 010** (Replace prints in `cyrus_brain.py`) — must be COMPLETE. Converts all 66 `print()` calls to `log.*()` calls and adds `log = logging.getLogger("cyrus.brain")` at module top.

By build time, `cyrus_brain.py` will already have:
```python
import logging
log = logging.getLogger("cyrus.brain")
```

All existing `print()` calls will already be `log.info()` / `log.error()` / etc. This plan builds on that foundation.

## Gap Analysis

| Acceptance Criterion | Current State (post-010) | Action Needed |
|---|---|---|
| Logs permission type being detected | `arm_from_hook()` logs detection but without structured tool field | Add `self._perm_tool` instance var; log tool name at detection |
| Permission name/description logged on Allow click | `handle_response()` logs "Allowing command (project)" — no tool/cmd | Store `_perm_tool` and `_perm_cmd`; include in log call |
| Timestamp in log | Automatic from logging module at INFO level | No action — `[cyrus.brain] I ...` format includes no timestamp at INFO; DEBUG mode adds `HH:MM:SS` prefix. Acceptable per docs/16 |
| Utterance that triggered approval | Not logged anywhere | Add `text` parameter to log calls in `handle_response()` |
| Dialog title / permission scope | `_announced` and `cmd` hold scope info but not logged at approval time | Log `_perm_cmd` (represents scope/description) |
| All entries at INFO level | Post-010 uses `log.info()` for these | Ensure new calls also use `log.info()` |
| No sensitive data exposed | `cmd` could contain paths — already truncated to 120 chars | Keep truncation; don't log raw UIA dialog text |
| Audit trail sufficient | Missing: tool, command, utterance, source, outcome as structured fields | Add all fields to log messages |
| Existing functionality preserved | N/A | Change is additive — only adds/enhances log calls |
| No performance impact | N/A | `log.info()` is negligible |

**Key gap**: `handle_response(text)` doesn't have access to the tool name or command. `arm_from_hook(tool, cmd)` receives them but doesn't store them. The polling loop in `start()` computes `tool_label` and `cmd_label` as locals. Two new instance variables (`_perm_tool`, `_perm_cmd`) bridge this gap.

## Design Decisions

### D1. New instance variables: `_perm_tool` and `_perm_cmd`

When permission becomes pending (in `arm_from_hook()` or the `start()` polling loop), store the tool name and command so `handle_response()` can log them. Cleared when permission resolves.

This is preferable to parsing `self._announced` (which uses the format `"hook:{cmd}"`) because structured fields are cleaner for audit logs.

### D2. Enhance existing log calls, don't duplicate

Issue 010 will have converted the existing prints in `handle_response()` to basic `log.info()` calls like:
```python
log.info("Allowing command (%s)", self.project_name or "session")
```

This plan REPLACES those with richer messages:
```python
log.info(
    "Permission APPROVED: tool=%s cmd=%s utterance=%r project=%s",
    self._perm_tool, self._perm_cmd, text, self.project_name or "session",
)
```

### D3. Log at detection AND at resolution

Two log events per permission:
1. **Detection** — when dialog is first noticed (in `arm_from_hook()` or `start()` polling)
2. **Resolution** — when user approves or denies (in `handle_response()`)

This gives the audit trail a start→end pair for each permission event.

### D4. Truncation for security

Commands are truncated to 120 characters (matching existing `arm_from_hook()` pattern). The user utterance is logged as `%r` (repr) which escapes special characters. No raw UIA dialog text is logged.

### D5. Timeout logging

When a pending permission times out (>20s without response), log a WARNING. This captures cases where permissions expired without user action — security-relevant.

## Acceptance Criteria to Test Mapping

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC1 | Logs permission type being detected | Grep `handle_response` for `log.info` containing `_perm_tool` |
| AC2 | Permission name/description logged on Allow click | Check log message includes `_perm_cmd` field |
| AC3 | Log includes timestamp and utterance | Timestamp is automatic from logging; check `text` is in log.info args |
| AC4 | Log includes dialog title or permission scope | `_perm_cmd` is the permission scope (tool command/path) |
| AC5 | All log entries at INFO level | All new calls use `log.info()` (except timeout which is `log.warning()`) |
| AC6 | No sensitive data exposed in logs | `_perm_cmd` truncated to 120 chars; no raw dialog text |
| AC7 | Log entries sufficient for audit trail | Each entry has: outcome, tool, cmd, utterance, project |
| AC8 | Existing PermissionWatcher functionality preserved | No behavioral changes — only log call modifications |
| AC9 | No performance impact from logging | `log.info()` calls are O(1) string formatting |

## Implementation Steps

### Step 1: Add instance variables to `__init__`

**File**: `cyrus_brain.py` — `PermissionWatcher.__init__()` (around line 656)

Add two new instance variables after the existing `_announced` line:

```python
self._perm_tool         = ""      # tool name for audit log (set when pending)
self._perm_cmd          = ""      # command/scope for audit log (set when pending)
```

**Verify**: No syntax errors, class still initializes.

### Step 2: Store tool/cmd in `arm_from_hook()`

**File**: `cyrus_brain.py` — `arm_from_hook()` (around line 859)

After `self._pending = True`, add:
```python
self._perm_tool = tool
self._perm_cmd  = cmd[:120] if cmd else tool
```

The existing detection log (converted from `print(f"\n[Permission/hook] ...")` by Issue 010) should be enhanced to:
```python
log.info(
    "Permission detected: tool=%s cmd=%s project=%s source=hook",
    tool, cmd[:120] if cmd else tool, self.project_name or "session",
)
```

### Step 3: Store tool/cmd in `start()` polling loop

**File**: `cyrus_brain.py` — `start()` inner `poll()` function, where `_pending` transitions to `True` (around line 964)

After `self._pending = True` and after `tool_label`/`cmd_label` are computed, add:
```python
self._perm_tool = tool_label or "unknown"
self._perm_cmd  = cmd_label
```

The existing detection log (converted from `print(f"\n[Permission] ...")` by Issue 010) should be enhanced to:
```python
log.info(
    "Permission detected: tool=%s cmd=%s project=%s source=UIA",
    self._perm_tool, self._perm_cmd, self.project_name or "session",
)
```

### Step 4: Enhance `handle_response()` — APPROVE path

**File**: `cyrus_brain.py` — `handle_response()`, inside the `if words & self.ALLOW_WORDS:` block (around line 880)

Replace the existing log call (post-010: `log.info("Allowing command (%s)", ...)`) with:
```python
log.info(
    "Permission APPROVED: tool=%s cmd=%s utterance=%r project=%s",
    self._perm_tool or "unknown",
    self._perm_cmd or "unknown",
    text,
    self.project_name or "session",
)
```

At the end of the block where `_pending` and `_allow_btn` are cleared, also clear:
```python
self._perm_tool = ""
self._perm_cmd  = ""
```

### Step 5: Enhance `handle_response()` — DENY path

**File**: `cyrus_brain.py` — `handle_response()`, inside the `if words & self.DENY_WORDS:` block (around line 903)

Replace the existing log call (post-010: `log.info("Cancelling command (%s)", ...)`) with:
```python
log.info(
    "Permission DENIED: tool=%s cmd=%s utterance=%r project=%s",
    self._perm_tool or "unknown",
    self._perm_cmd or "unknown",
    text,
    self.project_name or "session",
)
```

At the end of the block, also clear:
```python
self._perm_tool = ""
self._perm_cmd  = ""
```

### Step 6: Add timeout logging in `start()` polling loop

**File**: `cyrus_brain.py` — `start()` inner `poll()` function, where pending times out after 20s (around line 997)

Before or after clearing `_pending` and `_allow_btn`, add:
```python
log.warning(
    "Permission TIMEOUT: tool=%s cmd=%s project=%s (no response after 20s)",
    self._perm_tool or "unknown",
    self._perm_cmd or "unknown",
    self.project_name or "session",
)
self._perm_tool = ""
self._perm_cmd  = ""
```

### Step 7: Verify manually

Run the system and trigger permission dialogs:

```bash
# Start Cyrus with INFO logging (default)
python cyrus_brain.py

# Trigger a permission dialog (e.g., Bash tool usage in Claude Code)
# Say "yes" to approve

# Check logs for audit trail entries:
# Expected output pattern:
#   [cyrus.brain] I Permission detected: tool=Bash cmd=npm test project=myproject source=hook
#   [cyrus.brain] I Permission APPROVED: tool=Bash cmd=npm test utterance='yes' project=myproject
```

```bash
# Verify no sensitive data leaks
CYRUS_LOG_LEVEL=DEBUG python cyrus_brain.py 2>&1 | grep -iE "password|secret|token|key"
# Expected: no matches (commands are truncated, no raw dialog text logged)
```

### Step 8: Code review checklist

- [ ] All new log calls use `log.info()` (or `log.warning()` for timeout)
- [ ] `_perm_tool` and `_perm_cmd` initialized in `__init__`
- [ ] `_perm_tool` and `_perm_cmd` set in both `arm_from_hook()` and `start()` polling
- [ ] `_perm_tool` and `_perm_cmd` cleared in both APPROVE and DENY paths of `handle_response()`
- [ ] `_perm_tool` and `_perm_cmd` cleared on timeout
- [ ] Command truncated to 120 chars in all paths
- [ ] Utterance logged as `%r` (repr) — escapes special characters
- [ ] No raw UIA dialog text logged
- [ ] No behavioral changes to click/keyboard/escape logic
- [ ] `%s` formatting used (not f-strings) per logging convention

## Risk Assessment

**Low risk.** Additive-only changes to an existing class. No behavioral modifications.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Issue 010 not complete at build time | `log` variable undefined; all new calls crash | Low (blocked-by enforced) | Builder checks for `log = logging.getLogger(...)` at top of file |
| `_perm_tool`/`_perm_cmd` not cleared on all paths | Stale data in next permission's log | Low | Explicit clear in APPROVE, DENY, and TIMEOUT paths |
| Utterance contains secrets user spoke | Logged as `%r` in audit trail | Very low | Utterance is user's yes/no voice command — not sensitive data |
| Thread safety of new instance vars | Python GIL protects simple attribute writes | None | Same threading model as existing `_pending`/`_allow_btn` |

## Files Modified

- `cyrus_brain.py` — `PermissionWatcher` class only:
  - `__init__()` — 2 new instance variables
  - `arm_from_hook()` — 2 lines to store vars + enhance log call
  - `handle_response()` — replace 2 log calls with richer versions, add 4 lines to clear vars
  - `start()` polling loop — 2 lines to store vars + enhance detection log + add timeout log
