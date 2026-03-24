---
id=010-Replace-prints-in-cyrus-brain-2
title=Replace all 44 print() calls in cyrus_brain.py with log.xyz() calls
state=COMPLETE
parent=010-Replace-prints-in-cyrus-brain
children=046,047,048,050,057,058,059,060,061,062,063,064,075,076
split_count=0
force_split=false
needs_interview=false
verify_count=2
total_input_tokens=131645
total_output_tokens=59
total_duration_seconds=422
total_iterations=3
run_count=3
---

# Replace all 44 print() calls in cyrus_brain.py with log.xyz() calls

## Sprint
Sprint 2 — Quality & Safety

## Priority
High

## Parent
010-Replace-prints-in-cyrus-brain

## References
- docs/16-logging-system.md — level-mapping rules
- cyrus2/cyrus_brain.py — file to modify
- plans/010-Replace-prints-in-cyrus-brain.md — detailed per-line mapping table

## Description
Replace all 44 remaining `print()` calls in `cyrus2/cyrus_brain.py` with the correct `log.xyz()` equivalents. Uses the detailed mapping table in the plan. Requires child 1 (boilerplate) to be complete first so `log` is defined. Does NOT touch the 19 existing `logging.xyz()` calls (that is child 3's scope).

## Blocked By
- 010-Replace-prints-in-cyrus-brain-1 — boilerplate must be added first

## Acceptance Criteria
- [x] All 44 `print()` calls removed from `cyrus2/cyrus_brain.py`
- [x] `[Brain]` prefix stripped from log messages (logger name replaces it)
- [x] `[!]` prefix stripped from log messages
- [x] 18 calls converted to `log.info(...)` per the mapping table
- [x] 10 calls converted to `log.error(...)` per the mapping table
- [x] 5 calls converted to `log.warning(...)` per the mapping table
- [x] 10 calls converted to `log.debug(...)` per the mapping table
- [x] All f-string arguments converted to `%s`-style lazy formatting
- [x] `exc_info=True` added to log calls inside exception handlers (lines 67-70, 616, 735, 774, 800, 1072)
- [x] Leading `\n` stripped from messages (logging adds its own newlines)
- [x] `end=" ", flush=True` from line 871 dropped (log handles line endings)
- [x] Lines 67-70 (two prints) combined into a single `log.error(...)` call
- [x] Lines 925-928 (multi-line f-string) flattened to a single `log.info(...)` call
- [x] `grep -c "print(" cyrus2/cyrus_brain.py` → 0
- [x] `ruff check cyrus2/cyrus_brain.py` passes

## Implementation Steps

Follow the detailed mapping table from `plans/010-Replace-prints-in-cyrus-brain.md` exactly.

### log.info() — 18 calls
| Line | Replacement |
|------|-------------|
| 490 | `log.info("%s", result.log_message)` |
| 785 | `log.info("Mobile client connected: %s", addr)` |
| 803-806 | `log.info("Mobile client disconnected: %s (close_code=%s, close_reason=%s)", addr, ws.close_code, ws.close_reason)` |
| 925-928 | `log.info("Brain answers: %s", spoken[:80] + ("..." if len(spoken) > 80 else ""))` |
| 946 | `log.info("You [%s]: %s", proj or "VS Code", message)` |
| 1010 | `log.info("Cyrus [%s] (hook): %s", proj or "Claude", preview)` |
| 1036 | `log.info("PostTool: %s", spoken)` |
| 1043 | `log.info("PostTool: %s", spoken)` |
| 1051 | `log.info("Notification: %s", spoken)` |
| 1058 | `log.info("PreCompact: %s (proj=%r)", spoken, proj)` |
| 1092 | `log.info("Voice service connected from %s", addr)` |
| 1111 | `log.info("Listening for wake word...")` |
| 1117 | `log.info("Voice service disconnected.")` |
| 1212 | `log.info("Listening for voice service on %s:%s", addr[0], addr[1])` |
| 1221 | `log.info("Listening for Claude hooks on %s:%s", hook_addr[0], hook_addr[1])` |
| 1231 | `log.info("Listening for mobile clients on %s:%s (WebSocket)", host, MOBILE_PORT)` |
| 1268 | `log.info("Waiting for voice to connect...")` |
| 1284 | `log.info("Cyrus Brain signing off.")` |

### log.error() — 10 calls
| Line | Replacement |
|------|-------------|
| 67-70 | `log.error("FATAL: UIAutomation still unavailable after cache clear (%s). Try: pip install --force-reinstall comtypes uiautomation", _e2, exc_info=True)` |
| 607 | `log.error("Extension error: %s", result.get("error"))` |
| 616 | `log.error("Companion extension error: %s", e, exc_info=True)` |
| 654 | `log.error("Claude chat input not found.")` |
| 676 | `log.error("VS Code window not found.")` |
| 735 | `log.error("Submit error: %s", e, exc_info=True)` |
| 774 | `log.error("Voice reader error: %s", e, exc_info=True)` |
| 800 | `log.error("Mobile client error: %s: %s", type(e).__name__, e, exc_info=True)` |
| 956 | `log.error("Could not find VS Code window.")` |
| 1072 | `log.error("Hook handler error: %s", e, exc_info=True)` |

### log.warning() — 5 calls
| Line | Replacement |
|------|-------------|
| 63 | `log.warning("Cleared corrupted comtypes cache, retrying...")` |
| 613 | `log.warning("Companion extension unavailable: %s", e)` |
| 630 | `log.warning("Companion extension unavailable -- falling back to UIA")` |
| 953 | `log.warning("Submit timed out.")` |
| 1024-1026 | `log.warning("No PermissionWatcher found for proj=%r, known=%s", proj, list(session_mgr._perm_watchers.keys()))` |

### log.debug() — 10 calls
| Line | Replacement |
|------|-------------|
| 510 | `log.debug("Active project: %s", proj)` |
| 863 | `log.debug("Conversation heard: %s", text)` |
| 866 | `log.debug("Ignored -- say 'Cyrus, ...' (heard: %s)", first)` |
| 871 | `log.debug("Wake word -- listening for command...")` |
| 885 | `log.debug("No command heard")` |
| 887 | `log.debug("Follow-up text: %s", text)` |
| 889 | `log.debug("No command heard (timeout)")` |
| 935 | `log.debug("Brain command: %s", ctype)` |
| 997 | `log.debug("Hook event=%s, cwd=%r, resolved_proj=%r", event, cwd, proj)` |
| 1016 | `log.debug("pre_tool received: tool=%s, proj=%r, cmd=%s", tool, proj, cmd[:60])` |

After all replacements:
1. Run `ruff check cyrus2/cyrus_brain.py` and fix any issues
2. Run `ruff format cyrus2/cyrus_brain.py`

## Files to Modify
- `cyrus2/cyrus_brain.py` — replace 44 print() calls

## Testing
```bash
# Verify zero prints remain
grep -c "print(" cyrus2/cyrus_brain.py
# Expected: 0

# Lint check
ruff check cyrus2/cyrus_brain.py
ruff format --check cyrus2/cyrus_brain.py
```

## Stage Log

### GROOMED — 2026-03-17 01:19:22Z

- **From:** NEW
- **Duration in stage:** 0s
- **Input tokens:** 54,312 (final context: 54,312)
- **Output tokens:** 8
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage

### PLANNED — 2026-03-17 01:21:56Z

- **From:** PLANNED
- **Duration in stage:** 239s
- **Input tokens:** 44,986 (final context: 44,986)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 22%
- **Model:** claude-opus-4-6
- **Trigger:** manual/plan

### BUILT — 2026-03-17 01:35:04Z

- **From:** BUILT
- **Duration in stage:** 113s
- **Input tokens:** 32,347 (final context: 32,347)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 16%
- **Model:** claude-sonnet-4-6
- **Trigger:** auto/build

### COMPLETE — 2026-03-19 18:27:05Z

- **From:** BUILT
- **Duration in stage:** 0s
- **Input tokens:** 0 (final context: 0)
- **Output tokens:** 0
- **Iterations:** 0
- **Model:** 
- **Trigger:** auto/verify
