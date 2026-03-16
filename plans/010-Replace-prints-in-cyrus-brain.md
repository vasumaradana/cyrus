# Plan 010: Replace print() calls in cyrus_brain.py

## Summary

Replace all 66 `print()` calls in `cyrus_brain.py` with structured `logging` calls. Add `import logging`, `from cyrus2.cyrus_log import setup_logging`, define `log = logging.getLogger("cyrus.brain")` after imports, and call `setup_logging("cyrus")` in `main()`. Convert f-strings to `%s`-style logging. Map each print to the correct log level per docs/16-logging-system.md.

## Dependencies

- **Issue 009** — `cyrus2/cyrus_log.py` must exist with `setup_logging()` function. Plan 009 is complete; module may or may not be built yet. If absent, this issue cannot be verified at runtime.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `import logging` | Not present | Add after `import socket` |
| `from cyrus2.cyrus_log import setup_logging` | Not present | Add after stdlib imports |
| `log = logging.getLogger("cyrus.brain")` | Not present | Add after all imports, before config block |
| `setup_logging("cyrus")` in `main()` | Not present | Add as first line of `main()` body after arg parsing |
| 66 `print()` calls | All use bare `print()` with `[Brain]`/`[!]` prefixes | Convert per mapping table below |
| f-string arguments | All use f-strings | Convert to `%s`-style lazy formatting |
| Exception handlers | Print `e` or bare except | Add `exc_info=True` where appropriate |

## Design Decisions

### D1. Import location

`import logging` goes with stdlib imports (after `import socket`). `from cyrus2.cyrus_log import setup_logging` goes after third-party imports (after the `uiautomation` try/except block, before `from collections import deque`). The logger definition `log = logging.getLogger("cyrus.brain")` goes immediately after the import block, before the `# ── Configuration ──` section.

### D2. Module-level prints (lines 52, 57, 58)

Three `print()` calls fire at import time during the `uiautomation` try/except recovery. At this point, `setup_logging()` hasn't been called yet (it runs in `main()`). The `log` variable _is_ defined (module-level, after imports), and Python's `logging.lastResort` handler (stderr, WARNING+) will catch WARNING and ERROR messages. This means:
- Line 52 (`log.warning(...)`) — works via lastResort
- Lines 57-58 (`log.error(...)`) — works via lastResort

The format won't match the configured format (no `[cyrus.brain]` prefix), but these only fire on corrupted comtypes cache — an edge case. This is acceptable: once `main()` starts, all subsequent log calls use the configured format.

### D3. `end=" "` and `flush=True` on line 1474

`print("(wake word — listening for command...)", end=" ", flush=True)` uses `end=" "` to keep the cursor on the same line for a follow-up print on line 1488. Logging doesn't support inline continuations — each log call is a complete line. Convert both to independent `log.debug()` calls. The visual "same-line" behavior is a cosmetic feature that only matters for human terminal watching; structured logging is cleaner.

### D4. Leading `\n` in print strings

Many prints start with `\n` for visual separation (e.g., `print(f"\n[Permission] ..."`). Drop the `\n` prefix — logging adds its own line termination, and timestamps (in DEBUG mode) provide visual structure. The logger name and level prefix make messages identifiable without blank-line separators.

### D5. `exc_info=True` policy

Per the issue's acceptance criterion: "Exception handlers using broad `except` → `log.error("context", exc_info=True)` or `log.debug(..., exc_info=True)`". Apply `exc_info=True` to all broad `except Exception` handlers that log. For narrow exception handlers (e.g., `except (ConnectionRefusedError, OSError)`), use `exc_info=True` at debug level — add a separate `log.debug("...", exc_info=True)` if the primary log call is warning-level, so tracebacks appear only in DEBUG mode.

### D6. `setup_logging()` placement in `main()`

The issue says "called once in `main()` before any logging". Place it after `argparse` but before `SessionManager` creation, since `SessionManager.start()` spawns threads that log immediately.

### D7. `[Brain]` prefix removal

The `[Brain]` prefix was an ad-hoc convention. The logger name `cyrus.brain` now provides this context in the structured format `[cyrus.brain] I ...`. Strip `[Brain] ` from all message strings. Similarly strip `[!] ` (replaced by ERROR level).

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC1 | All 66 `print()` calls replaced | `grep -c "print(" cyrus_brain.py` → 0 |
| AC2 | `from cyrus2.cyrus_log import setup_logging` added | `grep "from cyrus2.cyrus_log" cyrus_brain.py` → match |
| AC3 | `import logging` added | `grep "^import logging" cyrus_brain.py` → match |
| AC4 | `log = logging.getLogger("cyrus.brain")` defined | `grep 'getLogger("cyrus.brain")' cyrus_brain.py` → match |
| AC5 | `setup_logging("cyrus")` in `main()` | `grep 'setup_logging("cyrus")' cyrus_brain.py` → match |
| AC6 | `[Brain]` → `log.info()` | Visual review of converted lines |
| AC7 | `[!]` → `log.error()` | Lines 1267, 1287 use `log.error()` |
| AC8 | Fallback/timeout/retry → `log.warning()` | Lines 52, 1225, 1239, 1537, 1540 use `log.warning()` |
| AC9 | Routing/dispatch/scan → `log.debug()` | Lines 560, 623, 1050, 1466, 1469, etc. use `log.debug()` |
| AC10 | Exception handlers → `exc_info=True` | Lines 563, 936, 1228, 1346, 1382, 1407, 1644 include `exc_info=True` |
| AC11 | f-strings → `%s` style | All log calls use `log.level("msg: %s", var)` |
| AC12 | No new `print()` introduced | Same grep verification as AC1 |
| AC13 | Functionality unchanged | File structure, function signatures, logic flow all preserved |

## Complete Print-to-Log Mapping (all 66 calls)

### Module-level import block (3 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 52 | `print("[Brain] Cleared corrupted comtypes cache, retrying...")` | `log.warning("Cleared corrupted comtypes cache, retrying...")` | WARNING |
| 57 | `print(f"[Brain] FATAL: UIAutomation still unavailable after cache clear ({_e2}).")` | `log.error("FATAL: UIAutomation still unavailable after cache clear: %s", _e2)` | ERROR |
| 58 | `print("[Brain] Try: pip install --force-reinstall comtypes uiautomation")` | `log.error("Try: pip install --force-reinstall comtypes uiautomation")` | ERROR |

### `_execute_cyrus_command()` (7 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 344 | `print(f"[Brain] {spoken}")` | `log.info("%s", spoken)` | INFO |
| 347 | `print(f"[Brain] {spoken}")` | `log.warning("%s", spoken)` | WARNING |
| 353 | `print("[Brain] Routing unlocked.")` | `log.info("Routing unlocked.")` | INFO |
| 362 | `print(f"[Brain] {spoken}")` | `log.info("%s", spoken)` | INFO |
| 375 | `print(f"[Brain] {spoken}")` | `log.info("%s", spoken)` | INFO |
| 387 | `print(f"[Brain] {proj} → alias '{new_name}'")` | `log.info("%s → alias '%s'", proj, new_name)` | INFO |
| 390 | `print(f"[Brain] {spoken}")` | `log.info("%s", spoken)` | INFO |

### `ChatWatcher.start()` poll thread (5 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 544 | `print(f"[Brain] {label}Connected to Claude Code chat panel.")` | `log.info("%sConnected to Claude Code chat panel.", label)` | INFO |
| 560–561 | `print(f"[Brain] {label}Chat input coords cached: {_chat_input_coords.get(self.project_name)}")` | `log.debug("%sChat input coords cached: %s", label, _chat_input_coords.get(self.project_name))` | DEBUG |
| 563 | `print(f"[Brain] {label}Coords cache error: {e}")` | `log.warning("%sCoords cache error: %s", label, e, exc_info=True)` | WARNING |
| 614 | `print(f"\nCyrus [{self.project_name or 'Claude'}]: {preview}")` | `log.info("Cyrus [%s]: %s", self.project_name or "Claude", preview)` | INFO |
| 623–624 | `print(f"[queued: {self.project_name}] {len(self._pending_queue)} message(s) waiting")` | `log.debug("[queued: %s] %d message(s) waiting", self.project_name, len(self._pending_queue))` | DEBUG |

### `PermissionWatcher.arm_from_hook()` (1 call)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 872 | `print(f"\n[Permission/hook] {prefix}{tool}: {cmd}")` | `log.info("[Permission/hook] %s%s: %s", prefix, tool, cmd)` | INFO |

### `PermissionWatcher.handle_response()` (2 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 881 | `print(f"[Brain] → Allowing command ({self.project_name or 'session'})")` | `log.info("Allowing command (%s)", self.project_name or "session")` | INFO |
| 904 | `print(f"[Brain] → Cancelling command ({self.project_name or 'session'})")` | `log.info("Cancelling command (%s)", self.project_name or "session")` | INFO |

### `PermissionWatcher.handle_prompt_response()` (3 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 923 | `print(f"[Brain] → Dismissed prompt ({self.project_name or 'session'})")` | `log.info("Dismissed prompt (%s)", self.project_name or "session")` | INFO |
| 934 | `print(f"[Brain] → Prompt answered: {text!r}")` | `log.info("Prompt answered: %r", text)` | INFO |
| 936 | `print(f"[Brain] Prompt input error: {e}")` | `log.error("Prompt input error: %s", e, exc_info=True)` | ERROR |

### `PermissionWatcher.start()` poll thread (2 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 984 | `print(f"\n[Permission] {prefix}Claude wants to run: {cmd_label}")` | `log.info("[Permission] %sClaude wants to run: %s", prefix, cmd_label)` | INFO |
| 1007 | `print(f"\n[Input Prompt] {prompt}")` | `log.info("[Input Prompt] %s", prompt)` | INFO |

### `SessionManager` (3 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1050 | `print(f"[Brain] Flushed {n} queued response(s) from {proj}")` | `log.debug("Flushed %d queued response(s) from %s", n, proj)` | DEBUG |
| 1064 | `print(f"[Brain] Session detected: {proj}  (say \"switch to {alias}\")")` | `log.info("Session detected: %s  (say \"switch to %s\")", proj, alias)` | INFO |
| 1101 | `print(f'[Brain] {len(self._chat_watchers)} sessions: {names}')` | `log.info("%d sessions: %s", len(self._chat_watchers), names)` | INFO |

### `_start_active_tracker()` (1 call)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1123 | `print(f"[Brain] Active project: {proj}")` | `log.info("Active project: %s", proj)` | INFO |

### `_submit_via_extension()` (3 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1219 | `print(f"[Brain] Extension error: {result.get('error')}")` | `log.error("Extension error: %s", result.get("error"))` | ERROR |
| 1225 | `print(f"[Brain] Companion extension unavailable: {e}")` | `log.warning("Companion extension unavailable: %s", e)` | WARNING |
| 1228 | `print(f"[Brain] Companion extension error: {e}")` | `log.error("Companion extension error: %s", e, exc_info=True)` | ERROR |

### `_submit_to_vscode_impl()` (3 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1239 | `print("[Brain] Companion extension unavailable — falling back to UIA")` | `log.warning("Companion extension unavailable — falling back to UIA")` | WARNING |
| 1267 | `print("[!] Claude chat input not found.")` | `log.error("Claude chat input not found.")` | ERROR |
| 1287 | `print("[!] VS Code window not found.")` | `log.error("VS Code window not found.")` | ERROR |

### `_submit_worker()` (1 call)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1346 | `print(f"[Brain] Submit error: {e}")` | `log.error("Submit error: %s", e, exc_info=True)` | ERROR |

### `voice_reader()` (1 call)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1382 | `print(f"[Brain] Voice reader error: {e}")` | `log.error("Voice reader error: %s", e, exc_info=True)` | ERROR |

### `handle_mobile_ws()` (3 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1392 | `print(f"[Brain] Mobile client connected: {addr}")` | `log.info("Mobile client connected: %s", addr)` | INFO |
| 1407 | `print(f"[Brain] Mobile client error: {type(e).__name__}: {e}")` | `log.error("Mobile client error: %s: %s", type(e).__name__, e, exc_info=True)` | ERROR |
| 1410–1411 | `print(f"[Brain] Mobile client disconnected: {addr} (close_code={ws.close_code}, close_reason={ws.close_reason})")` | `log.info("Mobile client disconnected: %s (close_code=%s, close_reason=%s)", addr, ws.close_code, ws.close_reason)` | INFO |

### `routing_loop()` (11 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1466 | `print(f"[conversation] heard: '{text}'")` | `log.debug("Conversation heard: '%s'", text)` | DEBUG |
| 1469 | `print(f"(ignored — say 'Cyrus, ...' \| heard: '{first}')")` | `log.debug("Ignored — say 'Cyrus, ...' \| heard: '%s'", first)` | DEBUG |
| 1474 | `print("(wake word — listening for command...)", end=" ", flush=True)` | `log.debug("Wake word — listening for command...")` | DEBUG |
| 1486 | `print("(no command heard)")` | `log.debug("No command heard")` | DEBUG |
| 1488 | `print(f"'{text}'")` | `log.debug("Follow-up heard: '%s'", text)` | DEBUG |
| 1490 | `print("(no command heard)")` | `log.debug("No command heard")` | DEBUG |
| 1513 | `print(f"\n[Brain answers] {spoken[:80]}{'...' if len(spoken) > 80 else ''}")` | `log.info("Brain answers: %s", spoken[:80] + ("..." if len(spoken) > 80 else ""))` | INFO |
| 1520 | `print(f"\n[Brain command] {ctype}")` | `log.debug("Brain command: %s", ctype)` | DEBUG |
| 1530 | `print(f"\nYou [{proj or 'VS Code'}]: {message}")` | `log.info("You [%s]: %s", proj or "VS Code", message)` | INFO |
| 1537 | `print("→ Submit timed out.\n")` | `log.warning("Submit timed out.")` | WARNING |
| 1540 | `print("→ Could not find VS Code window.\n")` | `log.warning("Could not find VS Code window.")` | WARNING |

### `handle_hook_connection()` (9 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1578 | `print(f"[Hook] event={event}, cwd={cwd!r}, resolved_proj={proj!r}")` | `log.debug("[Hook] event=%s, cwd=%r, resolved_proj=%r", event, cwd, proj)` | DEBUG |
| 1591 | `print(f"\nCyrus [{proj or 'Claude'}] (hook): {preview}")` | `log.info("Cyrus [%s] (hook): %s", proj or "Claude", preview)` | INFO |
| 1597 | `print(f"[pre_tool] Received: tool={tool}, proj={proj!r}, cmd={cmd[:60]}")` | `log.debug("[pre_tool] Received: tool=%s, proj=%r, cmd=%s", tool, proj, cmd[:60])` | DEBUG |
| 1604–1605 | `print(f"[pre_tool] No PermissionWatcher found for proj={proj!r}, known={list(...)}")` | `log.warning("[pre_tool] No PermissionWatcher found for proj=%r, known=%s", proj, list(session_mgr._perm_watchers.keys()))` | WARNING |
| 1614 | `print(f"\n[PostTool] {spoken}")` | `log.info("[PostTool] %s", spoken)` | INFO |
| 1621 | `print(f"\n[PostTool] {spoken}")` | `log.info("[PostTool] %s", spoken)` | INFO |
| 1629 | `print(f"\n[Notification] {spoken}")` | `log.info("[Notification] %s", spoken)` | INFO |
| 1636 | `print(f"\n[PreCompact] {spoken} (proj={proj!r})")` | `log.info("[PreCompact] %s (proj=%r)", spoken, proj)` | INFO |
| 1644 | `print(f"[Brain] Hook handler error: {e}")` | `log.error("Hook handler error: %s", e, exc_info=True)` | ERROR |

### `handle_voice_connection()` (3 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1661 | `print(f"[Brain] Voice service connected from {addr}")` | `log.info("Voice service connected from %s", addr)` | INFO |
| 1680 | `print("[Brain] Listening for wake word...")` | `log.info("Listening for wake word...")` | INFO |
| 1686 | `print(f"[Brain] Voice service disconnected.")` | `log.info("Voice service disconnected.")` | INFO |

### `main()` (4 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1740 | `print(f"[Brain] Listening for voice service on {addr[0]}:{addr[1]}")` | `log.info("Listening for voice service on %s:%s", addr[0], addr[1])` | INFO |
| 1748 | `print(f"[Brain] Listening for Claude hooks on {hook_addr[0]}:{hook_addr[1]}")` | `log.info("Listening for Claude hooks on %s:%s", hook_addr[0], hook_addr[1])` | INFO |
| 1756 | `print(f"[Brain] Listening for mobile clients on {args.host}:{MOBILE_PORT} (WebSocket)")` | `log.info("Listening for mobile clients on %s:%s (WebSocket)", args.host, MOBILE_PORT)` | INFO |
| 1757 | `print("[Brain] Waiting for voice to connect...")` | `log.info("Waiting for voice to connect...")` | INFO |

### `__main__` block (1 call)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 1773 | `print("\nCyrus Brain signing off.")` | `log.info("Cyrus Brain signing off.")` | INFO |

**Total: 66 calls** (3 + 7 + 5 + 1 + 2 + 3 + 2 + 3 + 1 + 3 + 1 + 3 + 1 + 1 + 3 + 11 + 9 + 3 + 4 + 1 = 66 ✓)

## Implementation Steps

### Step 1: Add imports and logger definition

**File**: `cyrus_brain.py`

1. Add `import logging` after `import socket` (line 33):

```python
import socket
import logging
```

2. Add `from cyrus2.cyrus_log import setup_logging` after the `uiautomation` try/except block, before `from collections import deque` (between lines 59 and 60):

```python
    raise
from cyrus2.cyrus_log import setup_logging
from collections import deque
```

3. Add logger definition after the import block, before `# ── Configuration ──` (line 62):

```python
from collections import deque

log = logging.getLogger("cyrus.brain")

# ── Configuration ──────────────────────────────────────────────────────────────
```

### Step 2: Add `setup_logging()` call in `main()`

In `main()`, add `setup_logging("cyrus")` after argparse and before queue/session setup:

```python
    args = parser.parse_args()

    setup_logging("cyrus")

    _speak_queue     = asyncio.Queue()
```

### Step 3: Convert module-level prints (lines 52, 57, 58)

These 3 prints fire at import time. Convert using the `log` variable (defined at module level after imports).

### Step 4: Convert `_execute_cyrus_command()` prints (7 calls)

Lines 344, 347, 353, 362, 375, 387, 390.

### Step 5: Convert `ChatWatcher.start()` prints (5 calls)

Lines 544, 560–561, 563, 614, 623–624. Note the multiline print at 560–561 and 623–624.

### Step 6: Convert `PermissionWatcher` prints (8 calls)

- `arm_from_hook()`: line 872
- `handle_response()`: lines 881, 904
- `handle_prompt_response()`: lines 923, 934, 936
- `start()`: lines 984, 1007

### Step 7: Convert `SessionManager` prints (3 calls)

Lines 1050, 1064, 1101.

### Step 8: Convert `_start_active_tracker()` print (1 call)

Line 1123.

### Step 9: Convert `_submit_via_extension()` and `_submit_to_vscode_impl()` prints (6 calls)

Lines 1219, 1225, 1228, 1239, 1267, 1287.

### Step 10: Convert `_submit_worker()` and `voice_reader()` prints (2 calls)

Lines 1346, 1382.

### Step 11: Convert `handle_mobile_ws()` prints (3 calls)

Lines 1392, 1407, 1410–1411.

### Step 12: Convert `routing_loop()` prints (11 calls)

Lines 1466, 1469, 1474, 1486, 1488, 1490, 1513, 1520, 1530, 1537, 1540.

### Step 13: Convert `handle_hook_connection()` prints (9 calls)

Lines 1578, 1591, 1597, 1604–1605, 1614, 1621, 1629, 1636, 1644.

### Step 14: Convert `handle_voice_connection()` prints (3 calls)

Lines 1661, 1680, 1686.

### Step 15: Convert `main()` and `__main__` prints (5 calls)

Lines 1740, 1748, 1756, 1757, 1773.

### Step 16: Verify — zero print() calls remaining

```bash
cd /home/daniel/Projects/barf/cyrus
grep -cn "print(" cyrus_brain.py
```

Expected: `0` matches.

### Step 17: Verify — all required patterns present

```bash
cd /home/daniel/Projects/barf/cyrus
grep -n "from cyrus2.cyrus_log import setup_logging" cyrus_brain.py
grep -n "^import logging" cyrus_brain.py
grep -n 'getLogger("cyrus.brain")' cyrus_brain.py
grep -n 'setup_logging("cyrus")' cyrus_brain.py
```

All four must match exactly one line each.

### Step 18: Verify — syntax check

```bash
cd /home/daniel/Projects/barf/cyrus
python3 -m py_compile cyrus_brain.py 2>&1 || true
```

If Windows-only imports cause errors (comtypes, uiautomation), that's expected on non-Windows — the important thing is no `SyntaxError`.

## Risk Assessment

**Low risk.** Mechanical conversion of print→log. No logic changes, no new behavior, no API changes.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Import-time log calls have no handler | Unformatted output for comtypes recovery | Very low | Python `lastResort` handler covers WARNING+; these are edge-case messages |
| Typo in `%s` format string | Runtime `TypeError` on first log call | Low | Mapping table above is exhaustive; grep verification catches mismatches |
| `cyrus_log.py` not built yet (Issue 009) | `ImportError` at runtime | Medium | Issue is blocked by 009; builder should verify 009 is complete before build |
| `exc_info=True` adds unexpected traceback verbosity | Longer log output | Very low | Only on ERROR-level exceptions; this is the desired behavior per spec |
