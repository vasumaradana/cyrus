# Implementation Plan: Replace print() calls in cyrus_server.py

**Issue**: [012-Replace-prints-in-cyrus-server](/home/daniel/Projects/barf/cyrus/issues/012-Replace-prints-in-cyrus-server.md)
**Created**: 2026-03-16
**PROMPT**: `/home/daniel/Projects/barf/cyrus/prompts/PROMPT_plan.md`

## Gap Analysis

**Already exists**:
- `cyrus_server.py` at project root (~167 lines) — fully functional WebSocket server with 4 `print()` calls
- `docs/16-logging-system.md` — complete logging design with print-to-log conversion rules, per-file change table, output format specs
- `cyrus2/pyproject.toml` — project config (Issue 001 complete)

**Needs building**:
- Replace 4 `print()` calls with structured logging in `cyrus2/cyrus_server.py`
- Add `import logging` and `from cyrus2.cyrus_log import setup_logging` imports
- Add `log = logging.getLogger("cyrus.server")` after imports
- Add `setup_logging("cyrus")` at entry point (`main()`)
- Convert all f-strings to `%s`-style logging format strings

**BLOCKERS**:
- **Issue 009** (Create cyrus_log module) — `cyrus2/cyrus_log.py` does not exist yet. State: PLANNED. Must complete first to provide `setup_logging()`.
- **Implicit: Issue 002** (Run ruff autofix/format → copy files to cyrus2/) — `cyrus2/cyrus_server.py` does not exist yet; current file is at root level `cyrus_server.py`. The issue references `cyrus2/cyrus_server.py` as the target file.

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
| 104 | `print(f"[Brain] Client connected: {addr}")` | `INFO` | `log.info("Client connected: %s", addr)` | Lifecycle event (connection) |
| 139 | `print(f"[Brain] [{project or '?'}] '{text[:50]}' → {decision['action']}")` | `DEBUG` | `log.debug("[%s] '%s' → %s", project or "?", text[:50], decision["action"])` | Per-utterance routing decision |
| 144 | `print(f"[Brain] Client disconnected: {addr}")` | `INFO` | `log.info("Client disconnected: %s", addr)` | Lifecycle event (disconnection) |
| 150 | `print(f"[Brain] Listening on ws://{host}:{port}")` | `INFO` | `log.info("Listening on ws://%s:%s", host, port)` | Lifecycle event (startup) |

**Level assignments** per `docs/16-logging-system.md`:
- Connected/Listening/Disconnected = lifecycle events → `INFO`
- Routing decisions, command dispatch = per-utterance flow → `DEBUG`

## Rules to Follow

No `.claude/rules/` files exist in this project (directory is empty).

General principles from project conventions:
- **Fix everything you see** — if any lint/type issues are encountered, fix them
- **F-string → %s conversion** — logging calls must use `%s` style, not f-strings (avoids string interpolation when log level is filtered)

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Replace prints, add imports | `python-pro` subagent | Idiomatic Python logging patterns |
| Verify no remaining prints | `qa-expert` subagent | Grep-based verification |
| Lint check | `ruff` (CLI tool) | Ensure modified file passes ruff check + format |

## Prioritized Tasks

- [ ] **Step 1: Verify prerequisites** — Confirm `cyrus2/cyrus_server.py` exists (Issue 002 done) and `cyrus2/cyrus_log.py` exists (Issue 009 done). If blocked, fail early with clear message.
- [ ] **Step 2: Add imports** — Add `import logging` and `from cyrus2.cyrus_log import setup_logging` at top of `cyrus2/cyrus_server.py`, after existing imports.
- [ ] **Step 3: Add logger definition** — Add `log = logging.getLogger("cyrus.server")` after the import block.
- [ ] **Step 4: Add setup_logging call** — Add `setup_logging("cyrus")` as first line of `main()` function (before argparse).
- [ ] **Step 5: Replace 4 print() calls** — Apply the 4 replacements from the table above. Convert all f-strings to `%s`-style logging format.
- [ ] **Step 6: Verify no print() calls remain** — `grep -n "print(" cyrus2/cyrus_server.py` should return 0 matches.
- [ ] **Step 7: Lint and format** — Run `ruff check cyrus2/cyrus_server.py` and `ruff format --check cyrus2/cyrus_server.py`.
- [ ] **Step 8: Compile check** — `python3 -m py_compile cyrus2/cyrus_server.py`.
- [ ] **Step 9: Write acceptance tests** — Create test file verifying all acceptance criteria (imports present, logger defined, no prints, setup_logging called).

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| All 4 print() calls replaced | `grep -c "print(" cyrus2/cyrus_server.py` returns 0 | verification |
| `from cyrus2.cyrus_log import setup_logging` added | `grep "from cyrus2.cyrus_log import setup_logging" cyrus2/cyrus_server.py` matches | verification |
| `import logging` added | `grep "^import logging" cyrus2/cyrus_server.py` matches | verification |
| `log = logging.getLogger("cyrus.server")` defined | `grep 'logging.getLogger("cyrus.server")' cyrus2/cyrus_server.py` matches | verification |
| `setup_logging("cyrus")` called at startup | `grep 'setup_logging("cyrus")' cyrus2/cyrus_server.py` matches | verification |
| Lifecycle events use log.info() | `grep "log.info" cyrus2/cyrus_server.py` returns 3 matches (connected, disconnected, listening) | verification |
| Routing/debug patterns use log.debug() | `grep "log.debug" cyrus2/cyrus_server.py` returns 1 match (routing decision) | verification |
| F-strings converted to %s style | `grep 'log\.\w*(f"' cyrus2/cyrus_server.py` returns 0 matches | verification |
| No new print() calls introduced | `grep -c "print(" cyrus2/cyrus_server.py` returns 0 | verification |
| File still has same functionality | `python3 -m py_compile cyrus2/cyrus_server.py` succeeds | integration |

**No cheating** — cannot claim done without all verification passing.

## Validation (Backpressure)

- **Compile**: `python3 -m py_compile cyrus2/cyrus_server.py`
- **No prints**: `grep -c "print(" cyrus2/cyrus_server.py` → 0
- **Lint**: `ruff check cyrus2/cyrus_server.py`
- **Format**: `ruff format --check cyrus2/cyrus_server.py`
- **Imports present**: grep checks for `import logging`, `from cyrus2.cyrus_log import setup_logging`, `logging.getLogger("cyrus.server")`
- **Setup called**: grep for `setup_logging("cyrus")` in `main()` function

## Files to Create/Modify

- **Modify**: `cyrus2/cyrus_server.py` — add 4 import/setup lines, replace 4 print() calls with log calls
- **Create**: `cyrus2/tests/test_012_cyrus_server_logging.py` — acceptance-driven tests verifying all criteria

## Design Decisions

### D1. Log level for routing decision (line 139)
The per-utterance routing log (`'{text[:50]}' → {decision['action']}`) is `DEBUG` not `INFO`. Per docs/16-logging-system.md: "Routing decisions, command dispatch, session scan → DEBUG". This ensures production logs aren't flooded with per-message traffic while still being available with `CYRUS_LOG_LEVEL=DEBUG`.

### D2. setup_logging placement in main()
Called at the top of `main()` before argparse, because `main()` is the single entry point (called from `if __name__ == "__main__"` and potentially as a module entry point). This ensures logging is configured before any log calls execute, including the `_serve()` function.

### D3. No error-level logging needed
None of the 4 current print() calls are error patterns. The `except websockets.ConnectionClosed: pass` on line 141 silently handles expected disconnections — this is intentional (not an error condition). No `log.error()` calls needed for this issue.

### D4. Logger name matches convention
`cyrus.server` follows the established hierarchy: `cyrus.brain`, `cyrus.voice`, `cyrus.server`, `cyrus.main`. All inherit from the root `cyrus` logger configured by `setup_logging("cyrus")`.

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Issue 009 not complete (no cyrus_log.py) | **Blocker** | **High** (currently true) | Step 1 fails early with clear message |
| Issue 002 not complete (no cyrus2/cyrus_server.py) | **Blocker** | **High** (currently true) | Step 1 fails early with clear message |
| `cyrus2/__init__.py` missing (import fails) | Medium | Medium | Issue 009 should create it; if not, add as part of this issue |
| websockets import at runtime | None | None | Already handled by existing try/except on line 37 |
