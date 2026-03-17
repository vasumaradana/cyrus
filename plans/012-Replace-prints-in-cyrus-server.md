# Implementation Plan: Replace print() calls in cyrus_server.py

**Issue**: [012-Replace-prints-in-cyrus-server](/home/daniel/Projects/barf/cyrus/issues/012-Replace-prints-in-cyrus-server.md)
**Created**: 2026-03-16 (updated 2026-03-17)
**PROMPT**: `/home/daniel/Projects/barf/cyrus/prompts/PROMPT_plan.md`

## Gap Analysis

**Already exists**:
- `cyrus2/cyrus_server.py` — fully functional WebSocket server (207 lines) with exactly 4 `print()` calls at lines 127, 174, 179, 186
- `docs/16-logging-system.md` — complete logging design spec with print-to-log conversion rules, per-file changes table, output format specs
- `cyrus2/pyproject.toml` — Ruff config (E, F, W, I, UP, B rules, py310, line-length 88)
- Test infrastructure at `cyrus2/tests/` — 5 existing test files using unittest class-based pattern with `setUpClass`, `AC:` docstrings, assertion messages
- Tests add `cyrus2/` to `sys.path` and import modules directly (e.g., `import cyrus_brain`)

**Needs building**:
- Replace 4 `print()` calls with structured logging in `cyrus2/cyrus_server.py`
- Add `import logging` and `from cyrus2.cyrus_log import setup_logging` imports
- Add `log = logging.getLogger("cyrus.server")` after imports
- Add `setup_logging("cyrus")` at entry point (`main()`)
- Convert all f-strings to `%s`-style logging format strings
- Acceptance test file `cyrus2/tests/test_012_cyrus_server_logging.py`

**BLOCKERS**:
- **Issue 009** (Create cyrus_log module) — `cyrus2/cyrus_log.py` does **not exist yet**. State: PLANNED. Must complete first to provide `setup_logging()`. Step 1 below verifies this and fails early if unresolved.
- **`cyrus2/__init__.py`** does not exist — may be needed for `from cyrus2.cyrus_log import setup_logging`. However, existing test pattern adds `cyrus2/` to `sys.path` and imports directly (`import cyrus_brain`), so the import in production may use `from cyrus_log import setup_logging` if run from within `cyrus2/`. The issue text specifies `from cyrus2.cyrus_log`, so follow that exactly.

## Approach

**Strategy**: Straightforward 1:1 print-to-log replacement following the established conversion rules in `docs/16-logging-system.md`. This is the simplest of the print migration issues (only 4 calls).

**Why this approach**:
- The logging design doc already specifies exact mappings for each pattern type
- Only 4 print() calls — no ambiguity, no complex patterns
- Logger name `cyrus.server` is pre-specified in the per-file changes table
- All 4 prints use `[Brain]` prefix which gets replaced by the logger name in the format string

### The 4 Replacements

| Line | Current print() | Level | Replacement | Rationale |
|------|----------------|-------|-------------|-----------|
| 127 | `print(f"[Brain] Client connected: {addr}")` | `INFO` | `log.info("Client connected: %s", addr)` | Lifecycle event (connection) |
| 174 | `print(f"[Brain] [{project or '?'}] '{text[:50]}' → {decision['action']}")` | `DEBUG` | `log.debug("[%s] '%s' -> %s", project or "?", text[:50], decision["action"])` | Per-utterance routing decision |
| 179 | `print(f"[Brain] Client disconnected: {addr}")` | `INFO` | `log.info("Client disconnected: %s", addr)` | Lifecycle event (disconnection) |
| 186 | `print(f"[Brain] Listening on ws://{host}:{port}")` | `INFO` | `log.info("Listening on ws://%s:%s", host, port)` | Lifecycle event (startup) |

**Level assignments** per `docs/16-logging-system.md`:
- Connected/Listening/Disconnected = lifecycle events -> `INFO`
- Routing decisions, command dispatch = per-utterance flow -> `DEBUG`

**Note on line 174**: The `->` arrow in the original f-string uses a Unicode right arrow (`\u2192`). In the logging replacement, use a plain ASCII `->` for portability.

## Rules to Follow

- `.claude/skills/python-expert/AGENTS.md` — Python expert guidelines: type hints, PEP 8, docstrings, proper error handling. Applies because we're modifying Python source.
- `.claude/skills/python-testing/SKILL.md` — Testing patterns. Applies to writing acceptance tests.
- **Ruff compliance**: Code must pass `ruff check` and `ruff format` with pyproject.toml settings (E, F, W, I, UP, B; line-length 88; py310)
- **F-string -> %s conversion** — logging calls must use `%s` style, not f-strings (avoids string interpolation when log level is filtered)
- **Fix everything you see** — if any lint/type issues are encountered in the file, fix them

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Replace prints, add imports | Direct implementation | Only 4 replacements + 4 lines of imports/setup — too small for subagent |
| Write acceptance tests | Direct implementation | Follow existing unittest pattern from `test_001`, `test_007` |
| Lint check | `ruff` CLI | `ruff check cyrus2/cyrus_server.py && ruff format --check cyrus2/cyrus_server.py` |
| Compile check | `python3 -m py_compile` | Verify file is syntactically valid |

## Prioritized Tasks

- [x] **Step 1: Verify prerequisites** — Confirmed `cyrus2/cyrus_server.py` exists and `cyrus2/cyrus_log.py` exists (Issue 009 done).
- [x] **Step 2: Add imports** — Added `import logging` (stdlib block, alphabetical) and `from cyrus2.cyrus_log import setup_logging` (after websockets try/except).
- [x] **Step 3: Add logger definition** — Added `log = logging.getLogger("cyrus.server")` after imports, before Config section.
- [x] **Step 4: Add setup_logging call** — Added `setup_logging("cyrus")` as first line of `main()`, before argparse.
- [x] **Step 5: Replace 4 print() calls** — All 4 replaced: 3x `log.info()` (connected, disconnected, listening) + 1x `log.debug()` (routing decision). All f-strings converted to `%s`-style.
- [x] **Step 6: Verify no print() calls remain** — `grep -c "print(" cyrus_server.py` → 0.
- [x] **Step 7: Lint and format** — `ruff check`: All checks passed. `ruff format --check`: 1 file already formatted.
- [x] **Step 8: Compile check** — `python3 -m py_compile cyrus_server.py` → PASS.
- [x] **Step 9: Write acceptance tests** — Created `cyrus2/tests/test_012_cyrus_server_logging.py` (23 tests, all passing). Used source-text + AST analysis following test_011 pattern.

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| All 4 print() calls replaced | `test_no_print_calls_remain` — AST walk finds 0 `print()` calls | unit |
| `from cyrus2.cyrus_log import setup_logging` added | `test_setup_logging_imported` — AST/source check for import | unit |
| `import logging` added | `test_import_logging_present` — AST check for `import logging` | unit |
| `log = logging.getLogger("cyrus.server")` defined | `test_logger_defined` — AST check for getLogger assignment | unit |
| `setup_logging("cyrus")` called at startup | `test_setup_logging_called_in_main` — AST check that `main()` body starts with `setup_logging("cyrus")` | unit |
| Lifecycle events use log.info() | `test_info_calls_count` — AST walk finds 3 `log.info(...)` calls | unit |
| Routing/debug patterns use log.debug() | `test_debug_calls_count` — AST walk finds 1 `log.debug(...)` call | unit |
| F-strings converted to %s style | `test_no_fstring_in_log_calls` — AST check that no log call args are JoinedStr | unit |
| No new print() calls introduced | Same as first test | unit |
| File still has same functionality | `test_file_compiles` — `py_compile.compile()` succeeds | unit |
| No log.error() needed (no error patterns) | `test_no_error_calls` — AST check that 0 `log.error()` calls exist | unit |

**Testing approach**: Use AST (Abstract Syntax Tree) analysis to verify structural properties of the modified file, following the pattern established in `test_007_command_handlers.py`. This avoids needing to actually import/run the server (which requires websockets and a running event loop).

**No cheating** — cannot claim done without all required tests passing.

## Validation (Backpressure)

- **Compile**: `python3 -m py_compile cyrus2/cyrus_server.py`
- **No prints**: `grep -c "print(" cyrus2/cyrus_server.py` -> 0
- **Lint**: `ruff check cyrus2/cyrus_server.py`
- **Format**: `ruff format --check cyrus2/cyrus_server.py`
- **Imports present**: AST/grep checks for `import logging`, `from cyrus2.cyrus_log import setup_logging`, `logging.getLogger("cyrus.server")`
- **Setup called**: AST check for `setup_logging("cyrus")` in `main()` function
- **Tests pass**: `python -m unittest cyrus2/tests/test_012_cyrus_server_logging.py -v`

## Files to Create/Modify

- **Modify**: `cyrus2/cyrus_server.py` — add 4 import/setup lines, replace 4 print() calls with log calls
- **Create**: `cyrus2/tests/test_012_cyrus_server_logging.py` — acceptance-driven tests verifying all criteria via AST analysis

## Design Decisions

### D1. Log level for routing decision (line 174)
The per-utterance routing log (`'{text[:50]}' -> {decision['action']}`) is `DEBUG` not `INFO`. Per `docs/16-logging-system.md`: "Routing decisions, command dispatch, session scan -> DEBUG". This ensures production logs aren't flooded with per-message traffic while still being available with `CYRUS_LOG_LEVEL=DEBUG`.

### D2. setup_logging placement in main()
Called at the top of `main()` before argparse, because `main()` is the single entry point (called from `if __name__ == "__main__"` and potentially as a module entry point). This ensures logging is configured before any log calls execute, including inside `_serve()` and `handle_client()`.

### D3. No error-level logging needed
None of the 4 current print() calls are error patterns. The `except websockets.ConnectionClosed: pass` on line 176 silently handles expected disconnections — this is intentional behavior (not an error condition). No `log.error()` calls needed for this issue.

### D4. Logger name matches convention
`cyrus.server` follows the established hierarchy: `cyrus.brain`, `cyrus.voice`, `cyrus.server`, `cyrus.main`. All inherit from the root `cyrus` logger configured by `setup_logging("cyrus")`.

### D5. Unicode arrow replacement
The original line 174 uses a Unicode right arrow (`\u2192`). Replace with ASCII `->` in the log message for portability and consistency with log-grep patterns.

### D6. Test strategy: AST over runtime
Use AST (Abstract Syntax Tree) analysis in tests rather than runtime imports. This avoids importing `websockets` (which may not be installed in CI) and avoids needing to mock the async event loop. The `test_007_command_handlers.py` file establishes this AST-inspection pattern.

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Issue 009 not complete (no cyrus_log.py) | **Blocker** | **High** (currently true) | Step 1 fails early with clear message |
| `cyrus2/__init__.py` missing (import may fail at runtime) | Medium | Medium | Issue 009 should create it; flag if missing but don't block — AST tests don't need runtime import |
| websockets not installed in test env | Low | Medium | AST-based tests avoid runtime import entirely |
| Ruff format changes | Low | Low | Run `ruff format` and accept changes |
