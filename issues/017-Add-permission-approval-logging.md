---
id=017-Add-permission-approval-logging
title=Issue 017: Add permission approval logging
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=55241
total_output_tokens=4
total_duration_seconds=96
total_iterations=1
run_count=1
---

# Issue 017: Add permission approval logging

## Sprint
Sprint 2 — Quality & Safety

## Priority
High

## References
- docs/12-code-audit.md — H3 Security PermissionWatcher Auto-Clicks Allow

## Description
Add logging to the PermissionWatcher in `cyrus2/cyrus_brain.py:876–914` to record which permissions are being auto-approved. This provides security visibility when the system automatically clicks "Allow" in permission dialogs in response to a "yes" utterance.

## Blocked By
- Issue 010 (logging must be in place)

## Acceptance Criteria
- [ ] PermissionWatcher logs permission type being detected
- [ ] Permission name/description logged when "Allow" button is clicked
- [ ] Log includes timestamp and utterance that triggered approval
- [ ] Log includes dialog title or permission scope
- [ ] All log entries at INFO level (security-relevant events)
- [ ] No sensitive data exposed in logs (avoid full dialog text if it contains secrets)
- [ ] Log entries sufficient for audit trail of auto-approved permissions
- [ ] Existing PermissionWatcher functionality preserved
- [ ] No performance impact from logging

## Implementation Steps
1. Locate PermissionWatcher class in `cyrus2/cyrus_brain.py:876–914`
2. Identify where permission dialog is detected (likely looking for specific UI patterns)
3. Add logging before clicking "Allow":
   ```python
   log.info("Auto-approving permission: %s (detected: %s)", permission_name, dialog_title)
   ```
4. Include utterance context if available:
   ```python
   log.info("Permission '%s' auto-approved in response to: '%s'", permission_name, utterance)
   ```
5. Add logging for different permission types (file access, notification, etc.)
6. Include dialog title or control hierarchy in log for auditability
7. Ensure logs do not expose sensitive information (avoid logging full dialog content with secrets)
8. Test with various permission types and utterances

## Files to Create/Modify
- `cyrus2/cyrus_brain.py` — add logging to PermissionWatcher:876–914

## Testing
```bash
# Run and trigger permission dialog
python cyrus2/cyrus_brain.py &
# Perform action that triggers permission dialog (e.g., file access request)
# Say "yes" to trigger auto-approval
# Expected: log shows "Auto-approving permission: [type]"

# Check logs for permission audit trail
CYRUS_LOG_LEVEL=INFO python cyrus2/cyrus_brain.py 2>&1 | grep "Auto-approving"
# Expected: each permission approval logged with type and context

# Verify no sensitive data in logs
CYRUS_LOG_LEVEL=DEBUG python cyrus2/cyrus_brain.py 2>&1 | grep -i "password\|secret\|token"
# Expected: none (logging should not expose secrets)
```

## Stage Log

### GROOMED — 2026-03-11 18:21:53Z

- **From:** NEW
- **Duration in stage:** 96s
- **Input tokens:** 55,241 (final context: 55,241)
- **Output tokens:** 4
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
