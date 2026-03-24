# Implementation Plan: Replace print() calls in cyrus_brain.py

**Issue**: [010-Replace-prints-in-cyrus-brain](/home/daniel/Projects/barf/cyrus/issues/010-Replace-prints-in-cyrus-brain.md)
**Created**: 2026-03-16
**Updated**: 2026-03-16
**PROMPT**: PROMPT_plan

## Gap Analysis

**Already exists**:
- `import logging` at line 31
- 19 `logging.xyz()` calls (lines 309-472) using the **root logger** — introduced by Issues 007/008 (command dispatch & init functions refactors). These already use `%s`-style formatting.
- Tests directory at `cyrus2/tests/` with 5 unittest-based test files (test_001, test_004, test_007, test_008, test_deprecation)
- Ruff config in `pyproject.toml` (py310, line-length 88, rules E/F/W/I/UP/B)
- Logging design spec in `docs/16-logging-system.md` with exact format and conversion rules

**Needs building**:
- Add `from cyrus2.cyrus_log import setup_logging` import
- Add `log = logging.getLogger("cyrus.brain")` definition after imports
- Add `setup_logging("cyrus")` call as first line in `main()` (line 1239)
- Replace 44 `print()` calls with appropriate `log.xyz()` calls (43 log calls — lines 67-70 combine into one)
- Convert 19 existing `logging.xyz()` root-logger calls to use the named `log` logger
- Convert all f-string arguments to `%s`-style lazy formatting
- Add `exc_info=True` to logging calls inside exception handlers
- Write acceptance tests in `cyrus2/tests/test_010_print_replacement.py`

**Count discrepancy**: Issue says 66 prints but file has 44. The difference is the 19 `logging.*()` calls added by Issues 007/008 — originally those were prints too. Combined scope: 44 prints + 19 logging = 63 call sites to update.

**BLOCKER**: Issue 009 (Create cyrus_log module) is PLANNED, not BUILT. `cyrus2/cyrus_log.py` does not exist yet. This plan can be written now but building should wait until 009 is complete. If 009 is still incomplete at build time, the builder must create a minimal `cyrus_log.py` stub to unblock.

## Approach

Mechanical print-to-logging conversion following the mapping rules from `docs/16-logging-system.md`:

1. **Add boilerplate** — imports and logger definition at module top, `setup_logging()` in main
2. **Replace 44 print() calls** — categorize each by prefix/context, apply the correct log level
3. **Convert 19 existing logging.xyz() -> log.xyz()** — switch from root logger to named logger
4. **Fix formatting** — convert f-strings to `%s` lazy format for all log calls
5. **Handle exceptions** — add `exc_info=True` where inside except blocks
6. **Test** — verify no print() remains, verify log output format, verify functionality preserved

**Why this approach**: Mechanical replacement is safest — every print becomes a logging call at the appropriate level, preserving all existing messages. No behavior changes except output destination (stdout -> stderr) and format. The `[Brain]`/`[!]`/`[Hook]` prefixes are stripped because the logger name (`cyrus.brain`) replaces them in the format string.

## Rules to Follow

- `.claude/rules/` — **Empty** (no project-specific rules exist yet)
- `docs/16-logging-system.md` — **Canonical conversion rules** (authoritative reference for level mapping)
- `.claude/skills/python-expert/AGENTS.md` — Proper error handling (CRITICAL), no bare except, context managers

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Print replacement | `python-expert` skill | Python logging best practices, error handling patterns |
| Linting | `python-linting` skill | `ruff check` + `ruff format` compliance after changes |
| Testing | `python-testing` skill | unittest class-based tests with AC docstrings |
| Implementation | `python-pro` agent | Senior Python dev for production-ready logging code |
| Refactoring | `refactoring-specialist` agent | Systematic code transformation with safety guarantees |

## Prioritized Tasks

- [ ] 1. **Handle blocker**: Verify `cyrus2/cyrus_log.py` exists (Issue 009). If missing, create minimal stub:
  ```python
  import logging, sys, os
  def setup_logging(name: str = "cyrus") -> logging.Logger:
      level_name = os.environ.get("CYRUS_LOG_LEVEL", "INFO").upper()
      level = getattr(logging, level_name, logging.INFO)
      fmt = "[{name}] {levelname:.1s} {message}"
      if level <= logging.DEBUG:
          fmt = "{asctime} [{name}] {levelname:.1s} {message}"
      handler = logging.StreamHandler(sys.stderr)
      handler.setFormatter(logging.Formatter(fmt, style="{", datefmt="%H:%M:%S"))
      root = logging.getLogger(name)
      root.setLevel(level)
      root.addHandler(handler)
      root.propagate = False
      return root
  ```

- [ ] 2. **Add imports and logger boilerplate** at top of `cyrus2/cyrus_brain.py`:
  - Add `from cyrus2.cyrus_log import setup_logging` after existing imports (after line 91)
  - Add `log = logging.getLogger("cyrus.brain")` after the imports section
  - Add `setup_logging("cyrus")` as first executable line in `main()` (line 1239, before arg parsing)

- [ ] 3. **Replace 44 print() calls** with categorized log calls (see detailed table below)

- [ ] 4. **Convert 19 existing logging.xyz() calls to log.xyz()** (lines 309-472)
  - `logging.debug(...)` -> `log.debug(...)`
  - `logging.info(...)` -> `log.info(...)`
  - `logging.warning(...)` -> `log.warning(...)`
  - `logging.exception(...)` -> `log.exception(...)`
  - These already use `%s` formatting — no format changes needed

- [ ] 5. **Convert all f-strings in new log calls to %s-style lazy formatting**
  - e.g., `print(f"[Brain] Active project: {proj}")` -> `log.debug("Active project: %s", proj)`
  - For multi-variable f-strings, use multiple `%s` placeholders
  - For `%r` repr formatting: use `%r` placeholder where the original used `!r`

- [ ] 6. **Handle special cases**:
  - Lines 67-70: Multi-line error -> combine into single `log.error("FATAL: UIAutomation still unavailable after cache clear (%s). Try: pip install --force-reinstall comtypes uiautomation", _e2, exc_info=True)`
  - Line 490: `print(result.log_message)` -> `log.info("%s", result.log_message)` (dynamic message)
  - Line 871: `print("...", end=" ", flush=True)` -> `log.debug("...")` (drop end/flush — logging handles newlines)
  - Lines 925-928: Multi-line f-string -> flatten to single `log.info(...)` call

- [ ] 7. **Run linting and fix any issues**:
  - `ruff check cyrus2/cyrus_brain.py`
  - `ruff format cyrus2/cyrus_brain.py`

- [ ] 8. **Write acceptance tests** in `cyrus2/tests/test_010_print_replacement.py`

- [ ] 9. **Run full test suite and verify**:
  - `python -m pytest cyrus2/tests/ -v`
  - `grep -c "print(" cyrus2/cyrus_brain.py` -> expect 0

## Detailed Print-to-Log Mapping (44 calls)

### log.info() — 18 calls (lifecycle events, state changes, status)

| Line | Current | Replacement | Notes |
|------|---------|-------------|-------|
| 490 | `print(result.log_message)` | `log.info("%s", result.log_message)` | Dynamic message |
| 785 | `print(f"[Brain] Mobile client connected: {addr}")` | `log.info("Mobile client connected: %s", addr)` | Connected |
| 803-806 | `print(f"[Brain] Mobile client disconnected: {addr} (close_code=...)")` | `log.info("Mobile client disconnected: %s (close_code=%s, close_reason=%s)", addr, ws.close_code, ws.close_reason)` | Lifecycle |
| 925-928 | `print("\n[Brain answers] " f"{spoken[:80]}...")` | `log.info("Brain answers: %s", spoken[:80] + ("..." if len(spoken) > 80 else ""))` | Flatten multi-line |
| 946 | `print(f"\nYou [{proj or 'VS Code'}]: {message}")` | `log.info("You [%s]: %s", proj or "VS Code", message)` | User input |
| 1010 | `print(f"\nCyrus [{proj or 'Claude'}] (hook): {preview}")` | `log.info("Cyrus [%s] (hook): %s", proj or "Claude", preview)` | Hook response |
| 1036 | `print(f"\n[PostTool] {spoken}")` | `log.info("PostTool: %s", spoken)` | Post-tool |
| 1043 | `print(f"\n[PostTool] {spoken}")` | `log.info("PostTool: %s", spoken)` | Post-tool |
| 1051 | `print(f"\n[Notification] {spoken}")` | `log.info("Notification: %s", spoken)` | Notification |
| 1058 | `print(f"\n[PreCompact] {spoken} (proj={proj!r})")` | `log.info("PreCompact: %s (proj=%r)", spoken, proj)` | Lifecycle |
| 1092 | `print(f"[Brain] Voice service connected from {addr}")` | `log.info("Voice service connected from %s", addr)` | Connected |
| 1111 | `print("[Brain] Listening for wake word...")` | `log.info("Listening for wake word...")` | Listening |
| 1117 | `print("[Brain] Voice service disconnected.")` | `log.info("Voice service disconnected.")` | Lifecycle |
| 1212 | `print(f"[Brain] Listening for voice service on {addr[0]}:{addr[1]}")` | `log.info("Listening for voice service on %s:%s", addr[0], addr[1])` | Listening |
| 1221 | `print(f"[Brain] Listening for Claude hooks on {hook_addr[0]}:{hook_addr[1]}")` | `log.info("Listening for Claude hooks on %s:%s", hook_addr[0], hook_addr[1])` | Listening |
| 1231 | `print(f"[Brain] Listening for mobile clients on {host}:{MOBILE_PORT} (WebSocket)")` | `log.info("Listening for mobile clients on %s:%s (WebSocket)", host, MOBILE_PORT)` | Listening |
| 1268 | `print("[Brain] Waiting for voice to connect...")` | `log.info("Waiting for voice to connect...")` | Lifecycle |
| 1284 | `print("\nCyrus Brain signing off.")` | `log.info("Cyrus Brain signing off.")` | Shutdown |

### log.error() — 10 calls (errors, [!] prefix, except messages)

| Line | Current | Replacement | exc_info | Notes |
|------|---------|-------------|----------|-------|
| 67-70 | Two prints: FATAL + Try pip install | `log.error("FATAL: UIAutomation still unavailable after cache clear (%s). Try: pip install --force-reinstall comtypes uiautomation", _e2, exc_info=True)` | True | Combine 2 prints into 1 log call; in except block |
| 607 | `print(f"[Brain] Extension error: {result.get('error')}")` | `log.error("Extension error: %s", result.get("error"))` | no | Not in except |
| 616 | `print(f"[Brain] Companion extension error: {e}")` | `log.error("Companion extension error: %s", e, exc_info=True)` | True | In broad except block |
| 654 | `print("[!] Claude chat input not found.")` | `log.error("Claude chat input not found.")` | no | [!] prefix |
| 676 | `print("[!] VS Code window not found.")` | `log.error("VS Code window not found.")` | no | [!] prefix |
| 735 | `print(f"[Brain] Submit error: {e}")` | `log.error("Submit error: %s", e, exc_info=True)` | True | In except |
| 774 | `print(f"[Brain] Voice reader error: {e}")` | `log.error("Voice reader error: %s", e, exc_info=True)` | True | In except |
| 800 | `print(f"[Brain] Mobile client error: {type(e).__name__}: {e}")` | `log.error("Mobile client error: %s: %s", type(e).__name__, e, exc_info=True)` | True | In except |
| 956 | `print("-> Could not find VS Code window.\n")` | `log.error("Could not find VS Code window.")` | no | Error condition |
| 1072 | `print(f"[Brain] Hook handler error: {e}")` | `log.error("Hook handler error: %s", e, exc_info=True)` | True | In except |

### log.warning() — 5 calls (fallbacks, timeouts, retries)

| Line | Current | Replacement | exc_info | Notes |
|------|---------|-------------|----------|-------|
| 63 | `print("[Brain] Cleared corrupted comtypes cache, retrying...")` | `log.warning("Cleared corrupted comtypes cache, retrying...")` | no | Cleared cache pattern |
| 613 | `print(f"[Brain] Companion extension unavailable: {e}")` | `log.warning("Companion extension unavailable: %s", e)` | no | Fallback path (ConnectionRefused/OSError — expected) |
| 630 | `print("[Brain] Companion extension unavailable -- falling back to UIA")` | `log.warning("Companion extension unavailable -- falling back to UIA")` | no | Fallback |
| 953 | `print("-> Submit timed out.\n")` | `log.warning("Submit timed out.")` | no | Timeout |
| 1024-1026 | `print(f"[pre_tool] No PermissionWatcher found for proj={proj!r}, known=...")` | `log.warning("No PermissionWatcher found for proj=%r, known=%s", proj, list(session_mgr._perm_watchers.keys()))` | no | Unexpected state |

### log.debug() — 10 calls (routing, dispatch, scan)

| Line | Current | Replacement | Notes |
|------|---------|-------------|-------|
| 510 | `print(f"[Brain] Active project: {proj}")` | `log.debug("Active project: %s", proj)` | Window tracking/scan |
| 863 | `print(f"[conversation] heard: '{text}'")` | `log.debug("Conversation heard: %s", text)` | Routing |
| 866 | `print(f"(ignored -- say 'Cyrus, ...' \| heard: '{first}')")` | `log.debug("Ignored -- say 'Cyrus, ...' (heard: %s)", first)` | Routing |
| 871 | `print("(wake word -- listening for command...)", end=" ", flush=True)` | `log.debug("Wake word -- listening for command...")` | Routing; drop end/flush |
| 885 | `print("(no command heard)")` | `log.debug("No command heard")` | Routing |
| 887 | `print(f"'{text}'")` | `log.debug("Follow-up text: %s", text)` | Routing |
| 889 | `print("(no command heard)")` | `log.debug("No command heard (timeout)")` | Routing |
| 935 | `print(f"\n[Brain command] {ctype}")` | `log.debug("Brain command: %s", ctype)` | Command dispatch |
| 997 | `print(f"[Hook] event={event}, cwd={cwd!r}, resolved_proj={proj!r}")` | `log.debug("Hook event=%s, cwd=%r, resolved_proj=%r", event, cwd, proj)` | Hook dispatch |
| 1016 | `print(f"[pre_tool] Received: tool={tool}, proj={proj!r}, cmd={cmd[:60]}")` | `log.debug("pre_tool received: tool=%s, proj=%r, cmd=%s", tool, proj, cmd[:60])` | Pre-tool dispatch |

## Acceptance-Driven Tests

Test file: `cyrus2/tests/test_010_print_replacement.py`

Pattern: unittest class-based with AC docstrings, AST-based static analysis (following test_007, test_008 patterns). Mock Windows modules before import.

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| All print() calls replaced | `test_no_print_calls_remain` — grep source for `print(`, expect 0 | unit (static) |
| `from cyrus2.cyrus_log import setup_logging` added | `test_setup_logging_import_exists` — check import in AST | unit (static) |
| `import logging` present | `test_logging_import_exists` — check import in AST | unit (static) |
| `log = logging.getLogger("cyrus.brain")` defined | `test_named_logger_defined` — check source for getLogger call | unit (static) |
| `setup_logging("cyrus")` in main() | `test_setup_logging_called_in_main` — parse main() body via AST | unit (static) |
| `[Brain]` prefix -> log.info() | `test_no_brain_prefix_in_source` — verify no `[Brain]` in log messages | unit (static) |
| `[!]` prefix -> log.error() | `test_no_error_prefix_in_source` — verify no `[!]` in log messages | unit (static) |
| Fallback/timeout/retry -> log.warning() | `test_fallback_patterns_use_warning` — spot-check key lines via AST | unit (static) |
| Routing/dispatch/scan -> log.debug() | `test_routing_patterns_use_debug` — spot-check key lines via AST | unit (static) |
| Exception handlers use exc_info=True | `test_except_blocks_use_exc_info` — AST walk: find log calls in except blocks, verify exc_info kwarg | unit (static) |
| F-strings converted to %s style | `test_no_fstrings_in_log_calls` — AST: check log.xyz() call args are not JoinedStr (f-string) nodes | unit (static) |
| File has same functionality | `test_module_imports_cleanly` — import cyrus_brain without errors (mock Windows deps) | integration |
| No new print() introduced | Same as `test_no_print_calls_remain` | unit (static) |
| No root logger usage | `test_no_root_logger_calls` — grep for `logging.info(`, `logging.debug(`, etc.; expect 0 | unit (static) |

**No cheating** — cannot claim done without all required tests passing.

## Validation (Backpressure)

- **Tests**: `python -m pytest cyrus2/tests/test_010_print_replacement.py -v`
- **Lint**: `ruff check cyrus2/cyrus_brain.py`
- **Format**: `ruff format --check cyrus2/cyrus_brain.py`
- **Full suite**: `python -m pytest cyrus2/tests/ -v`
- **Zero prints**: `grep -c "print(" cyrus2/cyrus_brain.py` -> expect 0
- **Zero root logger**: `grep -c "logging\.\(debug\|info\|warning\|error\|exception\)" cyrus2/cyrus_brain.py` -> expect 0

## Files to Create/Modify

- `cyrus2/cyrus_log.py` — **create if missing** (Issue 009 blocker stub, ~15 lines)
- `cyrus2/cyrus_brain.py` — replace 44 print() calls + convert 19 logging.xyz() -> log.xyz() + add imports/boilerplate
- `cyrus2/tests/test_010_print_replacement.py` — **new** — acceptance tests (~120-180 lines)

## Risks & Notes

- **Blocker**: Issue 009 must be complete first. If `cyrus_log.py` doesn't exist at build time, create a minimal stub matching the spec in `docs/16-logging-system.md`.
- **Count discrepancy**: The issue says 66 prints; actual count is 44. The remaining 19 were already converted to `logging.*()` by prior issues. The plan handles both groups (44 + 19 = 63 total).
- **No behavior change**: All log messages are preserved (minus prefix tags like `[Brain]`). Output moves from stdout to stderr. Format changes to `[cyrus.brain] I message` style.
- **print() with end/flush**: Line 871 uses `end=" ", flush=True` — logging doesn't support these. Drop them; the message is complete without trailing space.
- **Leading newlines**: Several prints have `\n` prefix (lines 925, 935, 946, 1010, 1036, 1043, 1051, 1058). Strip these — logging adds its own line breaks.
