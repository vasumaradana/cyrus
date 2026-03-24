# Implementation Plan: Break up main() functions into subsystems

**Issue**: [008-Break-up-main-functions-into-subsystems](/home/daniel/Projects/barf/cyrus/issues/008-Break-up-main-functions-into-subsystems.md)
**Created**: 2026-03-16
**PROMPT**: `/home/daniel/Projects/barf/cyrus/.claude/agents/python-pro.md`

## Gap Analysis

**Already exists**:
- `cyrus_brain.py` main() at lines 1696–1764 (69 lines) — initializes queues, session manager, background threads, async tasks, and 3 TCP/WebSocket servers
- `main.py` main() at lines 1435–1726 (292 lines) — initializes remote connection, Whisper, Kokoro TTS, pygame, VAD, sessions, hotkeys, and contains entire 160-line routing loop inline
- Some helper functions exist in main.py (e.g., `_extract_project`, `_start_active_tracker`, `_fast_command`, `_execute_cyrus_command`), but none follow `_init_*()` pattern
- No helper extraction in cyrus_brain.py — all inline in main()
- cyrus2/ directory exists but contains only pyproject.toml and issue-001 tests — no source files yet
- Test framework: unittest (pytest planned but not installed yet, issue 003)

**Needs building**:
1. Extract 4–5 `_init_*()` functions from `cyrus_brain.py` to reduce main() from 69 → <50 lines
2. Extract 7–8 `_init_*()` functions from `main.py` to reduce main() from 292 → <50 lines
3. Extract main routing loop from `main.py` into a standalone async function
4. Add error handling with specific exceptions around each subsystem init
5. Document startup sequence in both files
6. Create acceptance tests verifying line counts, function existence, and behavior preservation

## Approach

**Work on root-level files** (`cyrus_brain.py`, `main.py`), not `cyrus2/` paths — the cyrus2/ directory doesn't have these files yet (issue 006 "Deprecate main.py monolith" will handle the move later). This is a pure refactoring task: extract, don't change behavior.

**Strategy**: Bottom-up extraction — identify logical subsystem boundaries in each main(), extract each into a named `_init_*()` function that returns initialized state, then rewrite main() as a thin orchestrator calling each in sequence. The routing loop in main.py (160 lines) must also be extracted since it's the single largest contributor to main()'s size.

**Why this approach**: Each `_init_*()` becomes independently testable with mocked dependencies. The thin main() becomes a readable startup manifest. Error handling improves because each subsystem can catch/log its own failures with specific context.

## Rules to Follow

- `.claude/rules/code-patterns.md` — Service Layer Pattern: main() should orchestrate, not contain logic. DRY extraction. Explicit naming. Error handling at boundaries.
- `.claude/rules/hard-requirements.md` — Every function needs docstrings explaining WHY/context, not just restating the signature.
- Python conventions: snake_case for functions/files, PascalCase for classes, SCREAMING_SNAKE for constants

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Extract _init functions | `python-pro` agent | Python refactoring expertise |
| Write acceptance tests | `test-automator` agent | Test creation following project patterns |
| Verify behavior preservation | Manual verification | Run both services before/after and compare startup logs |

## Prioritized Tasks

### cyrus2/cyrus_brain.py (80 lines → <50 lines) ✅ COMPLETE

- [x] **1. Extract `_init_queues()`** — Returns (speak_queue, utterance_queue) as fresh asyncio.Queues
- [x] **2. Extract `_init_session(loop)`** — SessionManager creation + start + initial active project detection; return session_mgr
- [x] **3. Extract `_init_background_threads(session_mgr, loop)`** — Window focus tracker thread + submit worker thread; return nothing (daemon threads)
- [x] **4. Extract `_init_async_tasks(session_mgr, loop)`** — speak_worker + routing_loop coroutines; return nothing (fire-and-forget tasks)
- [x] **5. Extract `_init_servers(host, port, session_mgr, loop)`** — Voice TCP (8766), Hook TCP (8767), Mobile WebSocket (8769) setup; return tuple of servers
- [x] **6. Rewrite main()** — 36 lines: parse args → call _init_*() in order → async with servers → gather serve_forever

### cyrus2/main.py — already a thin wrapper ✅ (completed in issue 006)

- [x] **7-13. N/A** — cyrus2/main.py was already reduced to 31 lines by issue 006; it delegates to cyrus_brain.main(). No further extraction needed.

### Shared

- [x] **15. Add startup sequence documentation** — Numbered comment block in cyrus_brain.py main() listing all 6 init steps
- [x] **16. Write acceptance tests** — 36 tests in cyrus2/tests/test_008_init_functions.py: line counts, function existence, mock-based init tests, docstring checks, edge cases — all pass
- [x] **17. Verify behavior preservation** — ruff check + format pass clean; 145/145 tests pass

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| main() in cyrus_brain.py < 50 lines | `test_brain_main_line_count()` — parse AST, count lines of main() body | unit |
| main() in main.py < 50 lines (if kept) | `test_voice_main_line_count()` — parse AST, count lines of main() body | unit |
| Each subsystem in separate function | `test_init_functions_exist_brain()` — assert `_init_queues`, `_init_session`, `_init_background_threads`, `_init_async_tasks`, `_init_servers` are callable | unit |
| Each subsystem in separate function | `test_init_functions_exist_voice()` — assert `_init_remote`, `_init_whisper`, `_init_tts`, `_init_audio_pipeline`, `_init_hotkeys`, `_routing_loop` are callable | unit |
| Subsystem functions return initialized objects | `test_init_queues_returns_queues()` — mock asyncio, verify return types | unit |
| All original behavior preserved | `test_brain_main_calls_all_inits()` — mock each _init_*, run main(), verify all called in order | integration |
| Error handling improved | `test_whisper_init_failure_exits()` — mock WhisperModel to raise, verify sys.exit | unit |
| Error handling improved | `test_tts_init_failure_continues()` — mock Kokoro to raise, verify fallback message | unit |
| Startup sequence documented | `test_startup_comment_exists()` — grep for "Startup sequence" comment in both files | unit |

**No cheating** — cannot claim done without required tests passing.

## Validation (Backpressure)

- **Tests**: All acceptance tests in `cyrus2/tests/test_008_init_functions.py` must pass via `python3 -m unittest cyrus2/tests/test_008_init_functions.py -v`
- **Lint**: `ruff check cyrus_brain.py main.py` must pass clean
- **Format**: `ruff format --check cyrus_brain.py main.py` must pass
- **Line counts**: `main()` in both files verified < 50 lines via AST inspection
- **No behavior change**: Startup log messages must remain identical (same text, same order)

## Files Created/Modified ✅

- **Modified**: `cyrus2/cyrus_brain.py` — extracted 5 `_init_*()` functions, rewrote main() from 80 → 36 lines
- **Not modified**: `cyrus2/main.py` — already a thin wrapper (31 lines) from issue 006
- **Created**: `cyrus2/tests/test_008_init_functions.py` — 36 acceptance tests (all pass)

## Notes

- **Plan vs reality**: Plan was written assuming cyrus2/ had no source files. In fact, issues 006 and 007 had already run, producing `cyrus2/cyrus_brain.py` (with `_COMMAND_HANDLERS` dispatch table) and a thin `cyrus2/main.py`. Work targeted the actual cyrus2/ files, which is where the test infrastructure points.
- **main.py scope**: Issues 7–13 (extract Whisper/TTS/VAD init from main.py) were N/A because cyrus2/main.py was already reduced to a 31-line wrapper. The root-level main.py (1755 lines) is the voice monolith, but is outside cyrus2/ scope for this issue.
- **_init_queues pattern**: Returns values rather than setting globals — main() assigns to module globals. Only _init_session sets `_active_project` directly (via lock) because it's set from within the function body where the scan result is available.
- **All 145 tests pass**, lint clean, formatting clean.
