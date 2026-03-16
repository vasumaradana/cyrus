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

### cyrus_brain.py (69 lines → <50 lines)

- [ ] **1. Extract `_init_queues()`** — Create speak_queue, utterance_queue; return both + event loop
- [ ] **2. Extract `_init_session(loop)`** — SessionManager creation + start + initial active project detection; return session_mgr
- [ ] **3. Extract `_init_background_threads(session_mgr, loop)`** — Window focus tracker thread + submit worker thread; return nothing (daemon threads)
- [ ] **4. Extract `_init_async_tasks(session_mgr, loop)`** — speak_worker + routing_loop coroutines; return nothing (fire-and-forget tasks)
- [ ] **5. Extract `_init_servers(host, port, session_mgr, loop)`** — Voice TCP (8766), Hook TCP (8767), Mobile WebSocket (8769) setup; return tuple of servers
- [ ] **6. Rewrite main()** — ~20 lines: parse args → call _init_*() in order → async with servers → gather serve_forever

### main.py (292 lines → <50 lines)

- [ ] **7. Extract `_init_remote(args)`** — Remote brain WebSocket connection with fallback; return (remote_url, remote_ws) or set globals
- [ ] **8. Extract `_init_whisper()`** — GPU detection + WhisperModel loading; return whisper_model
- [ ] **9. Extract `_init_tts()`** — Kokoro TTS loading with CUDA/CPU fallback + Edge TTS fallback; set _kokoro global
- [ ] **10. Extract `_init_audio_pipeline(loop)`** — pygame.mixer, ThreadPoolExecutor, TTS queue, VAD loop thread, session manager, active project, TTS worker task, window tracker thread; return (utterance_queue, session_mgr, whisper_executor)
- [ ] **11. Extract `_init_hotkeys(loop)`** — Define toggle_pause/stop_speech/read_clipboard callbacks + register F7/F8/F9; return nothing
- [ ] **12. Extract `_routing_loop(utterance_queue, whisper_model, session_mgr, loop)`** — The entire while True loop (lines 1566–1725) into its own async function
- [ ] **13. Rewrite main()** — ~30 lines: parse args → call _init_*() in order → startup_sequence → drain queue → await _routing_loop

### Shared

- [ ] **14. Add error handling** — Wrap each _init_*() call in main() with try/except, log specific subsystem failure, exit(1) for critical failures (VAD, Whisper), warn-and-continue for optional (TTS fallback, hotkeys)
- [ ] **15. Add startup sequence documentation** — Comment block in each main() listing numbered init order
- [ ] **16. Write acceptance tests** — Line count checks, function existence checks, mock-based init tests
- [ ] **17. Verify behavior preservation** — Run ruff lint + format, manual smoke test startup logs

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

## Files to Create/Modify

- **Modify**: `cyrus_brain.py` — extract 5 `_init_*()` functions, rewrite main() as thin orchestrator
- **Modify**: `main.py` — extract 6 `_init_*()` functions + `_routing_loop()`, rewrite main() as thin orchestrator
- **Create**: `cyrus2/tests/test_008_init_functions.py` — acceptance test suite (unittest, following test_001 pattern)

## Notes

- The `cyrus2/` directory path in the issue's "Files to Create/Modify" refers to the future modular layout. Since issue 006 (Deprecate main.py monolith) hasn't run yet, we work directly on the root-level files.
- `main.py` main() contains ~8 globals set via `global` declarations. The _init_*() functions will need to either set these globals or return values for main() to assign. Prefer returning values where possible; use globals only where required by existing callback patterns (e.g., `_kokoro` is referenced by TTS functions throughout the file).
- The routing loop extraction (task 12) is the highest-impact change — it accounts for 160 of 292 lines. Even without it, main() would still be ~130 lines, so it's mandatory.
- `_init_audio_pipeline()` groups several related but small initializations (pygame, executor, queues, VAD thread, session manager, tracker thread) because extracting each into its own function would create too many tiny 3-line functions. If any single subsystem grows, it can be split later.
