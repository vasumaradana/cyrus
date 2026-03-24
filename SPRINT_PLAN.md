# Cyrus 2.0 Sprint Plan

**Project:** Cyrus Voice Assistant for Claude Code
**Current Size:** ~4,620 LOC (7 Python files)
**Planning Date:** 2026-03-11
**Sprint Duration:** 1 week (5 business days)

---

## Summary: 6 Sprints, 57 Issues

| Sprint | Title | Focus | Issues | Est. Effort |
|--------|-------|-------|--------|-------------|
| **0** | Tooling & Foundation | pyproject.toml, ruff, dev deps, CI setup | 001–007 | 4 days |
| **1** | Core Refactor | Extract common, deprecate main.py, break god functions | 008–018 | 8 days |
| **2** | Quality & Safety | Logging, thread safety, error handling, security fixes | 019–035 | 8 days |
| **3** | Test Suite | Unit + integration tests (4 tiers, 70+ tests) | 036–050 | 8 days |
| **4** | Configuration & Auth | Config system, TCP auth, dep pinning | 051–057 | 5 days |
| **5** | Docker & Extension | Headless mode, companion registration, Dockerfile | 058–072 | 8 days |
| **6** | Polish | Health checks, metrics, persistence, docs | 073–080 | 6 days |

**Total Estimated Effort:** ~47 days (junior dev pace with ramp-up)

---

## Sprint 0: Tooling & Foundation (4 days)

**Goal:** Set up linting, formatting, dev dependencies, and build infrastructure. No code logic changes — pure tooling.

**Blockers:** None (foundation)

---

### 001 — Create `pyproject.toml` with project metadata

**Sprint:** 0
**Size:** 1 day (junior dev)
**Description:**
Add `pyproject.toml` with project metadata (name, version, description, author, license), Python version constraint (3.10+), and entry points for main entry points. Include build system config.

**Reference:** Doc 17, "Create `pyproject.toml`"
**Depends on:** Nothing
**Blocks:** 002, 003, 004, 005
**Acceptance Criteria:**
- File exists with [project] table, build-system, and tool.ruff config stub
- Can be parsed by `pip` without errors
- Python version pinned to `python = "^3.10"`

---

### 002 — Configure Ruff (linter + formatter)

**Sprint:** 0
**Size:** 2 days (1 setup + 1 cleanup)
**Description:**
Add Ruff configuration to `pyproject.toml` with rules E, F, W, I, UP, B. Create `requirements-dev.txt` with ruff dependency. Run `ruff check --fix .` and `ruff format .` against all 7 `.py` files. Commit formatting changes as a separate commit.

**Reference:** Doc 17, section "Implementation Plan"
**Depends on:** 001
**Blocks:** 006, 007
**Acceptance Criteria:**
- `ruff check .` returns zero errors
- `ruff format --check .` passes (all files formatted)
- All `.py` files have consistent style (imports sorted, spacing normalized)
- No logic changes, only cosmetic reformatting

---

### 003 — Create `requirements-dev.txt` with test dependencies

**Sprint:** 0
**Size:** 1 day (junior dev)
**Description:**
Create `requirements-dev.txt` with pytest, pytest-asyncio, pytest-cov, and other dev tools. Pin versions. This file will be used in Sprint 3 (test suite setup) and later sprints.

**Reference:** Doc 14, "Framework: pytest"
**Depends on:** 001
**Blocks:** 009, 036
**Acceptance Criteria:**
- File exists with pytest, pytest-asyncio, pytest-cov, and ruff (duplicate OK)
- All dependencies are version-pinned
- `pip install -r requirements-dev.txt` succeeds

---

### 004 — Create issue template (.github/ISSUE_TEMPLATE)

**Sprint:** 0
**Size:** 0.5 days (junior dev)
**Description:**
Add a standard GitHub issue template for bug reports and feature requests. Include sections: "Expected behavior", "Actual behavior", "Steps to reproduce", "Environment" (Python version, OS, Cyrus version).

**Reference:** Best practice
**Depends on:** Nothing
**Blocks:** None (informational)
**Acceptance Criteria:**
- `.github/ISSUE_TEMPLATE/bug_report.md` exists with standard sections
- Template is rendered when creating a new issue

---

### 005 — Set up GitHub Actions CI stub

**Sprint:** 0
**Size:** 1 day (junior dev)
**Description:**
Create `.github/workflows/lint.yml` that runs on every PR: ruff check, ruff format check. Add `.github/workflows/test.yml` stub (will be expanded in Sprint 3). Both should report pass/fail to PR.

**Reference:** Doc 17, "Developer Workflow"
**Depends on:** 002, 003
**Blocks:** 006
**Acceptance Criteria:**
- `.github/workflows/lint.yml` exists and runs `ruff check` and `ruff format --check`
- Workflow passes on main branch
- Workflow fails if code is not formatted or has lint errors
- `.github/workflows/test.yml` stub exists (can be empty for now)

---

### 006 — Create `CONTRIBUTING.md`

**Sprint:** 0
**Size:** 0.5 days (junior dev)
**Description:**
Document development setup, linting/formatting workflow, how to run tests, and PR expectations. Reference `requirements-dev.txt` and ruff.

**Reference:** Docs 14, 17
**Depends on:** 002, 003, 005
**Blocks:** None (documentation)
**Acceptance Criteria:**
- File exists in project root
- Includes setup instructions (`.venv`, `pip install -r requirements.txt`, `pip install -r requirements-dev.txt`)
- Includes lint/format commands
- Includes test run instructions

---

### 007 — Update `README.md` with architecture overview

**Sprint:** 0
**Size:** 1 day (junior dev)
**Description:**
Update README with high-level architecture (brain, voice, hook, server components), quick start, and link to Sprint Plan (this document) and individual feature docs (12–17).

**Reference:** Self
**Depends on:** 001
**Blocks:** None (documentation)
**Acceptance Criteria:**
- Architecture diagram or ASCII art explaining components
- Quick start section
- Link to feature docs and sprint plan
- Explains the split-mode (brain + voice) vs. main.py monolith

---

## Sprint 1: Core Refactor (8 days)

**Goal:** Extract duplicated code, break god functions, deprecate main.py. This reduces codebase by ~2,000 lines and makes all subsequent refactoring a single-file change.

**Blockers:** Sprint 0 (ruff + formatting)

---

### 008 — Create `cyrus_common.py` with shared utilities

**Sprint:** 1
**Size:** 2 days (extraction + dedup)
**Description:**
Create `cyrus_common.py` and extract the following functions and constants from main.py and cyrus_brain.py (doc 12, section C3):
- `_extract_project(title)` — parse VS Code window title
- `_make_alias(proj)` — kebab/snake → spaces
- `_resolve_project(query, aliases)` — fuzzy project matching
- `clean_for_speech(text)` — strip markdown, code blocks, truncate
- `_sanitize_for_speech(text)` — Unicode → ASCII mapping
- `_strip_fillers(text)` — remove leading filler words
- `_is_answer_request(text)` — detect question patterns
- `_fast_command(text)` — meta-command routing (pause, unlock, which_project, etc.)
- `_FILLER_RE` regex constant
- `_HALLUCINATIONS` list constant
- `play_chime()` and `play_listen_chime()` (if not audio-specific)

Update both main.py and cyrus_brain.py to import from cyrus_common.py instead of duplicating code. Delete duplicate definitions.

**Reference:** Doc 12, section C3
**Depends on:** 002 (ruff formatting must be done first)
**Blocks:** 009, 010, 011, 012, 013, 014, 015, 016, 017, 018
**Acceptance Criteria:**
- `cyrus_common.py` exists with 11 functions and 2 constants extracted
- main.py imports from cyrus_common instead of duplicating
- cyrus_brain.py imports from cyrus_common instead of duplicating
- No duplicate definitions remain
- All tests from Sprint 3 Tier 1 pass (project matching, fast command, text cleaning)
- Original functionality preserved (no behavior change)

---

### 009 — Create command dispatch dict for `_execute_cyrus_command()`

**Sprint:** 1
**Size:** 1.5 days (refactor + test)
**Description:**
Refactor `_execute_cyrus_command()` in cyrus_brain.py (lines 331–398, 776 lines total) into a command dispatch pattern (doc 12, section C1). Create a dict mapping command names (e.g., "switch_project", "unlock", "which_project") to small handler functions. Each handler is 10–30 lines. Replace the 6+-level nested if/elif chain with a single dict lookup + call.

Handler functions to extract:
- `_handle_switch_project(args)` — switch to named project
- `_handle_unlock(args)` — unlock voice input
- `_handle_which_project(args)` — report active project
- `_handle_last_message(args)` — retrieve last chat message
- `_handle_new_session(args)` — start new session
- `_handle_rename_alias(args)` — rename an alias
- Default handler for unknown commands

Update both main.py and cyrus_brain.py to use the dispatch dict. Document the pattern in CONTRIBUTING.md.

**Reference:** Doc 12, section C1
**Depends on:** 008
**Blocks:** 010, 019
**Acceptance Criteria:**
- Dispatch dict `_COMMANDS` exists in cyrus_common.py
- All handler functions extract cleanly with no nested if/elif
- Command routing logic is single dict lookup
- All tests from Sprint 3 Tier 1 (test_fast_command.py) pass
- Cyclomatic complexity of main logic reduced to ≤3

---

### 010 — Extract subsystems from `main()` in cyrus_brain.py

**Sprint:** 1
**Size:** 1.5 days (refactor + test)
**Description:**
Refactor `main()` in cyrus_brain.py (lines 1416–1549, 133 lines) into smaller subsystems (doc 12, section C2). Extract:
- `_init_vad()` — initialize VAD, model loading, state
- `_init_tts()` — initialize TTS (speech synthesis)
- `_init_audio()` — audio device setup
- `_start_watchers()` — start ChatWatcher and PermissionWatcher polling threads
- `_start_servers()` — start TCP servers (brain port 8766, hook 8767, mobile 8769)
- `_run_loop()` — main event loop with wake word detection and utterance processing

Each function is 10–30 lines. Slim `main()` becomes a 6-line orchestrator.

Do the same for main.py (lines 1435–1755, 320 lines).

**Reference:** Doc 12, section C2
**Depends on:** 008
**Blocks:** 011, 020
**Acceptance Criteria:**
- Each subsystem function is ≤30 lines
- `main()` is ≤10 lines (pure orchestration)
- No behavior change — system starts and runs identically
- All startup errors are logged (Sprint 2 requirement)
- Cyclomatic complexity of main() ≤5

---

### 011 — Extract subsystems from `main()` in main.py

**Sprint:** 1
**Size:** 1.5 days (see 010, parallel work)
**Description:**
Same as 010 but for main.py. After this and 010, both entry points have clean, testable subsystems.

**Reference:** Doc 12, section C2
**Depends on:** 008
**Blocks:** 012, 020
**Acceptance Criteria:**
- Each subsystem function is ≤30 lines
- `main()` is ≤10 lines
- No behavior change
- All tests pass

---

### 012 — Deprecate `main.py`—update docs and disable by default

**Sprint:** 1
**Size:** 1 day (docs + wrapper)
**Description:**
Document in README that main.py (monolithic mode) is deprecated. New users should use split mode (cyrus_brain.py + cyrus_voice.py). Add a deprecation comment at the top of main.py pointing to the docs. Update entry points in pyproject.toml to prefer split mode. Keep main.py functional but do not add new features to it.

**Reference:** Doc 15, recommendation #2
**Depends on:** 008, 009, 010, 011
**Blocks:** None (documentation)
**Acceptance Criteria:**
- `main.py` has deprecation notice at top
- `pyproject.toml` shows split-mode entry points as primary
- README explains split vs. monolithic modes
- main.py still runs without error (backward compat)

---

### 013 — Break up `ChatWatcher` class

**Sprint:** 1
**Size:** 1 day (refactor)
**Description:**
`ChatWatcher` in both main.py and cyrus_brain.py has methods doing multiple things. Extract:
- `_extract_response(tree, anchor)` — extract text from UIA tree after anchor point
- `_detect_stop_event()` — detect hook stop event on port 8767
- `_backtrack_to_anchor(tree)` — navigate tree to previous anchor
- `_run()` → `_poll_tree()` and `_poll_hook()` — separate polling paths

Keep class but reduce method length to <50 lines each. Make private helpers for deep nesting.

**Reference:** Doc 12, section M4 (deep nesting)
**Depends on:** 008
**Blocks:** None (follow-on polish)
**Acceptance Criteria:**
- No method in ChatWatcher exceeds 50 lines
- Deep nesting reduced to ≤5 levels
- All tests from Sprint 3 Tier 4 (test_chat_extraction.py) pass

---

### 014 — Break up `PermissionWatcher` class

**Sprint:** 1
**Size:** 1 day (refactor)
**Description:**
`PermissionWatcher` is another complex class. Extract:
- `_scan_for_dialog()` — scan UIA tree for permission dialog UI
- `_extract_permission_type()` — determine which permission (network, file, etc.)
- `_extract_response_from_utterance()` — match speech against ALLOW_WORDS/DENY_WORDS
- `handle_response()` → separate permission grant vs. deny paths

Keep class but reduce method length to <50 lines each.

**Reference:** Doc 12, sections C1, M4
**Depends on:** 008
**Blocks:** None (follow-on polish)
**Acceptance Criteria:**
- No method exceeds 50 lines
- Deep nesting reduced to ≤5 levels
- All tests from Sprint 3 Tier 3 (test_permission_keywords.py) pass

---

### 015 — Break up `SessionManager` class

**Sprint:** 1
**Size:** 1 day (refactor)
**Description:**
`SessionManager` manages prompts, aliases, and transcription state. Extract:
- `_scan_sessions()` — find all VS Code windows
- `_update_active_session()` — track which window has focus
- `_manage_aliases()` → separate get/set/delete alias helpers
- `_manage_prompts()` → separate get/update prompt helpers

Reduce method length to <40 lines each.

**Reference:** Doc 12, section M4
**Depends on:** 008
**Blocks:** None (follow-on polish)
**Acceptance Criteria:**
- No method exceeds 40 lines
- Deep nesting reduced to ≤5 levels

---

### 016 — Extract audio/UI utilities to helper modules

**Sprint:** 1
**Size:** 1 day (refactor)
**Description:**
Extract platform-specific and UI-heavy functions into focused modules:
- `cyrus_audio.py` — `play_chime()`, `play_listen_chime()`, audio device initialization
- `cyrus_uia.py` — UIAutomation tree walking, window finding (move `_vs_code_windows()`, `_is_vs_code()`, etc.)

This makes it easier to mock these in tests (Sprint 3) and to guard with HEADLESS flag (Sprint 5).

**Reference:** Doc 12, sections C1, M4
**Depends on:** 008
**Blocks:** 041, 042 (test suite — makes mocking cleaner)
**Acceptance Criteria:**
- `cyrus_audio.py` exists with audio-related functions
- `cyrus_uia.py` exists with UIAutomation tree walking
- Both main.py and cyrus_brain.py import from these modules
- No duplicate audio/UIA code remains

---

### 017 — Reduce import complexity—organize module boundaries

**Sprint:** 1
**Size:** 0.5 days (refactor + docs)
**Description:**
After extractions above, review circular imports and module dependency graph. Document in CONTRIBUTING.md:
- Core modules: cyrus_common.py (utilities, no external deps beyond stdlib)
- Platform modules: cyrus_uia.py, cyrus_audio.py (Windows/audio specific)
- Service modules: cyrus_brain.py, cyrus_voice.py, cyrus_hook.py, cyrus_server.py
- Entry points: main.py (deprecated), cyrus_brain.py, cyrus_voice.py

Ensure no circular imports. Update imports in all files to use absolute paths (no relative imports).

**Reference:** Doc 12, section M4
**Depends on:** 008, 016
**Blocks:** 018
**Acceptance Criteria:**
- No circular imports
- Module dependency graph is acyclic (DAG)
- CONTRIBUTING.md documents module organization
- `python -c "import cyrus_brain; import cyrus_voice"` succeeds without errors

---

### 018 — Run full ruff check and format on refactored code

**Sprint:** 1
**Size:** 0.5 days (cleanup)
**Description:**
After all extractions and refactoring, run ruff check --fix and ruff format to ensure consistent style. Commit as "chore: ruff cleanup after Sprint 1 refactor".

**Reference:** Doc 17
**Depends on:** 008–017
**Blocks:** 019 (logging must work on clean code)
**Acceptance Criteria:**
- `ruff check .` returns zero errors
- `ruff format --check .` passes
- All refactored files are properly formatted

---

## Sprint 2: Quality & Safety (8 days)

**Goal:** Add logging, fix race conditions, improve error handling, patch security issues. Improve robustness and debuggability.

**Blockers:** Sprint 1 (clean code structure)

---

### 019 — Create logging infrastructure (`cyrus_log.py`)

**Sprint:** 2
**Size:** 0.5 days (simple module)
**Description:**
Create `cyrus_log.py` with `setup_logging(name: str)` function. Use Python's `logging` module with:
- Log level from env var `CYRUS_LOG_LEVEL` (default: INFO)
- Format: `[name] {L} message` (where L = I/W/E/D)
- Timestamps in DEBUG mode
- Stderr output (for Docker docker logs integration)

See doc 16 for format details.

**Reference:** Doc 16, "Design" section
**Depends on:** 018
**Blocks:** 020, 021, 022, 023
**Acceptance Criteria:**
- Module exists with <50 lines
- `setup_logging("cyrus")` returns a logger
- Logger respects `CYRUS_LOG_LEVEL` env var
- Format matches examples in doc 16

---

### 020 — Replace `print()` in cyrus_brain.py with logging

**Sprint:** 2
**Size:** 1.5 days (66 print calls)
**Description:**
Replace all 66 `print()` calls in cyrus_brain.py with appropriate `log` calls. Follow conversion rules from doc 16:
- Error/fatal messages → `log.error()`
- State changes, connections → `log.info()`
- Routing decisions, command dispatch → `log.debug()`
- Warnings, fallbacks → `log.warning()`

Import at top: `log = logging.getLogger(__name__)`. Call `setup_logging()` in `main()`.

**Reference:** Doc 16, "Migration approach"
**Depends on:** 019
**Blocks:** 021
**Acceptance Criteria:**
- All 66 print calls replaced (or reduced via extraction)
- Logger import and setup correct
- `CYRUS_LOG_LEVEL=DEBUG` shows detailed output
- `CYRUS_LOG_LEVEL=INFO` shows only important messages
- No print() calls remain except in error fallbacks

---

### 021 — Replace `print()` in cyrus_voice.py with logging

**Sprint:** 2
**Size:** 1 day (32 print calls)
**Description:**
Same as 020 for cyrus_voice.py (32 print calls). Use logger name `cyrus.voice`.

**Reference:** Doc 16
**Depends on:** 019
**Blocks:** 022
**Acceptance Criteria:**
- All 32 print calls replaced
- Logger setup correct
- Log output matches expected format

---

### 022 — Replace `print()` in main.py and cyrus_server.py

**Sprint:** 2
**Size:** 0.5 days (72 print calls total)
**Description:**
Replace remaining 68 + 4 = 72 print calls in main.py and cyrus_server.py with logging. Use logger names `cyrus.main` and `cyrus.server`.

Note: Do NOT add logging to cyrus_hook.py (doc 16 explains why — must never block Claude Code).

**Reference:** Doc 16
**Depends on:** 019
**Blocks:** 023
**Acceptance Criteria:**
- All 72 print calls replaced
- cyrus_hook.py left untouched
- Logging works end-to-end

---

### 023 — Add logging.exception() to broad `except Exception` handlers

**Sprint:** 2
**Size:** 1.5 days (81 handlers across files)
**Description:**
Audit all 81 `except Exception` handlers (doc 12, section H1). Replace silent `pass` with context-appropriate logging:
- Where we need resilience (UIA tree walks, socket retries), add `log.debug("Context...", exc_info=True)` before `pass`
- Where we're catching to log + retry, add `log.warning("Retrying: %s", e)` before `continue`
- Where silent is truly needed (e.g., in audio fallback), keep `pass` but add a comment explaining why

Goal: All errors are visible in debug logs, but production (INFO level) stays clean.

**Reference:** Doc 12, section H1
**Depends on:** 020, 021, 022
**Blocks:** 024, 025, 026, 027
**Acceptance Criteria:**
- All silent `except Exception: pass` have context before them (log or comment)
- `CYRUS_LOG_LEVEL=DEBUG` shows every exception and its traceback
- `CYRUS_LOG_LEVEL=INFO` shows only important failures
- No error is completely hidden

---

### 024 — Add thread safety locks to shared mutable state

**Sprint:** 2
**Size:** 2 days (6 vars, multiple files)
**Description:**
Add `threading.Lock` for each mutable cache/state variable identified in doc 12, section C4:
- `_chat_input_cache` → `_chat_input_lock`
- `_vscode_win_cache` → `_win_cache_lock`
- `_chat_input_coords` → `_coords_lock`
- `_conversation_active` → `_active_event` (use `threading.Event` instead of bool)
- `_mobile_clients` → `_mobile_lock` (already doing `.copy()`, now protect writes too)
- `_whisper_prompt` → `_whisper_lock`

Wrap all reads and writes with `with lock:`. For `_conversation_active`, use `Event.set()` / `Event.clear()` / `Event.is_set()` instead of `=` assignment.

Add a comment above each variable explaining what it guards and which threads access it.

**Reference:** Doc 12, section C4
**Depends on:** 023
**Blocks:** 025, 026
**Acceptance Criteria:**
- All identified variables are protected with locks
- No unprotected reads/writes remain
- `_conversation_active` uses `threading.Event`
- Thread safety doc added to CONTRIBUTING.md
- No deadlocks (simple lock acquisition order: always acquire in same order)

---

### 025 — Fix clipboard/keystroke focus verification (security H2)

**Sprint:** 2
**Size:** 1 day (simple guard)
**Description:**
Add `_assert_vscode_focus()` guard before clipboard and keystroke sequences in main.py:1295, 1302, and cyrus_brain.py:928 (doc 12, section H2). Use `pygetwindow.getActiveWindow()` to verify VS Code is in focus before executing Ctrl+A, Ctrl+V, etc. If focus has shifted, log warning and abort.

```python
def _assert_vscode_focus():
    import pygetwindow as gw
    active = gw.getActiveWindow()
    if active and "Visual Studio Code" not in active.title:
        raise RuntimeError("VS Code lost focus — aborting keystroke")
```

**Reference:** Doc 12, section H2
**Depends on:** 023
**Blocks:** None
**Acceptance Criteria:**
- Function exists and is called before clipboard/keystroke ops
- If focus lost, operation aborts with clear log message
- Does not block if VS Code regains focus during operation

---

### 026 — Add PermissionWatcher approval logging (security H3)

**Sprint:** 2
**Size:** 0.5 days (logging only)
**Description:**
In PermissionWatcher.handle_response() (cyrus_brain.py around 876–914), add `log.warning()` each time a permission is auto-approved. Log the permission type (network, file, clipboard, etc.) and the utterance that triggered it.

Future: Consider requiring a specific confirmation phrase like "approve that" instead of just "yes" — this is noted but not implemented in Sprint 2.

**Reference:** Doc 12, section H3
**Depends on:** 020, 021
**Blocks:** None
**Acceptance Criteria:**
- Every permission approval is logged with type and trigger utterance
- Log level is WARNING (visible by default)
- Logs are clear enough to audit in production

---

### 027 — Fix file handle leak in SessionManager (H4)

**Sprint:** 2
**Size:** 0.5 days (trivial)
**Description:**
Fix cyrus_brain.py:1181 — `port = int(open(port_file).read().strip())` with proper context manager:
```python
with open(port_file) as f:
    port = int(f.read().strip())
```

Add try/except for missing file and add log.error() for bad port number.

**Reference:** Doc 12, section H4
**Depends on:** 020
**Blocks:** None
**Acceptance Criteria:**
- File handle always closed
- Missing file → log.error() + graceful fallback
- Invalid port → log.error() + skip session

---

### 028 — Pin all dependencies in requirements.txt files

**Sprint:** 2
**Size:** 1 day (version pinning)
**Description:**
Run `pip freeze` in a working environment and update all requirements files:
- `requirements.txt` (17 packages)
- `requirements-voice.txt` (10 packages)
- `requirements-brain.txt` (8 packages)
- `requirements-dev.txt` (created in Sprint 0)

Pin torch, onnxruntime-gpu, faster-whisper, and others to exact versions. Commit with message "chore: pin all dependency versions for reproducibility".

Alternatively, use `pip-compile` or `uv lock` to generate lockfiles.

**Reference:** Doc 12, section H5
**Depends on:** 003 (requirements-dev.txt exists)
**Blocks:** None (dependency management)
**Acceptance Criteria:**
- All dependencies have `==` version constraints
- `pip install -r requirements.txt` installs exact versions
- No `pip install` warnings about missing versions
- torch and onnxruntime-gpu have compatible versions for GPU support

---

## Sprint 3: Test Suite (8 days)

**Goal:** Add pytest with 4 tiers of tests (~70+ test cases). Achieve >80% coverage on pure functions and key logic.

**Blockers:** Sprint 1 (clean code structure), Sprint 0 (test dependencies)

---

### 029 — Set up pytest and test infrastructure

**Sprint:** 3
**Size:** 1 day (conftest.py + structure)
**Description:**
Create `tests/` directory and `tests/conftest.py` with:
- pytest fixtures for mock objects (mock UIA trees, mock sockets, mock audio)
- Helper functions for test data (sample window titles, sample utterances, sample JSON payloads)
- Any shared mocking utilities

Create empty test files for each tier (listed below). Update .github/workflows/test.yml to run `pytest tests/ -v --cov=.`.

**Reference:** Doc 14, "File Structure"
**Depends on:** 003, 016
**Blocks:** 030–043
**Acceptance Criteria:**
- `tests/conftest.py` exists with shared fixtures
- `tests/test_*.py` files created (initially empty)
- `pytest tests/ --collect-only` lists all tests
- Coverage reporting configured

---

### 030 — Implement Tier 1 tests: `test_text_processing.py`

**Sprint:** 3
**Size:** 1 day (15 + 8 + 8 = 31 test cases)
**Description:**
Test pure text-cleaning functions from cyrus_common.py:
- `clean_for_speech()` — 15 cases (markdown removal, code block stripping, truncation)
- `_sanitize_for_speech()` — 8 cases (Unicode → ASCII mapping: em dash, curly quotes, etc.)
- `_strip_fillers()` — 8 cases (remove "uh", "um", "like", leading filler words)

All are zero-mock tests. Use pytest parametrize for cases.

**Reference:** Doc 14, "Tier 1: Pure Function Tests" > test_text_processing.py
**Depends on:** 008, 029
**Blocks:** None
**Acceptance Criteria:**
- 31 test cases, all passing
- >95% coverage of text processing functions
- Tests cover edge cases (empty string, None, very long input, special Unicode)

---

### 031 — Implement Tier 1 tests: `test_project_matching.py`

**Sprint:** 3
**Size:** 1 day (10 + 6 + 10 = 26 test cases)
**Description:**
Test utility functions from cyrus_common.py:
- `_extract_project(title)` — 10 cases (VS Code window title parsing: "filename — project — VS Code")
- `_make_alias(proj)` — 6 cases (kebab/snake → spaces: "my-project" → "my project")
- `_resolve_project(query, aliases)` — 10 cases (fuzzy matching with aliases)

All zero-mock. Use pytest parametrize.

**Reference:** Doc 14, "Tier 1" > test_project_matching.py
**Depends on:** 008, 029
**Blocks:** None
**Acceptance Criteria:**
- 26 test cases, all passing
- >95% coverage
- Edge cases: missing parts, Unicode in titles, empty aliases dict

---

### 032 — Implement Tier 1 tests: `test_fast_command.py`

**Sprint:** 3
**Size:** 1.5 days (25 test cases)
**Description:**
Test `_fast_command(text)` from cyrus_common.py. This is the meta-command router (pause, unlock, which_project, last_message, switch, rename).

Cases:
- 5 cases per command type (pause, unlock, which_project, last_message, switch, rename) = 30 cases
- Non-commands (should return None) — 5 cases
- Edge cases (empty, whitespace, junk) — 5 cases

Total ~40 cases. Use pytest parametrize.

**Reference:** Doc 14, "Tier 1" > test_fast_command.py
**Depends on:** 009, 029
**Blocks:** None
**Acceptance Criteria:**
- 40 test cases, all passing
- >95% coverage of _fast_command and dispatch dict
- Tests verify extracted handler functions are called correctly

---

### 033 — Implement Tier 2 tests: `test_hook.py`

**Sprint:** 3
**Size:** 1 day (12 test cases)
**Description:**
Test cyrus_hook.py message dispatch (doc 14, "Tier 2: Hook Parsing Tests"). Mock stdin with JSON payloads and verify `_send()` is called correctly.

Cases:
- Stop event (2 cases: valid, missing fields)
- PreToolUse event (2 cases)
- PostToolUse event (2 cases)
- Notification event (2 cases)
- PreCompact event (2 cases)
- Invalid JSON (1 case)
- Unknown event type (1 case)

Total 12 cases. Mock stdin, capture stdout.

**Reference:** Doc 14, "Tier 2: Hook Parsing Tests"
**Depends on:** 029
**Blocks:** None
**Acceptance Criteria:**
- 12 test cases, all passing
- Covers all event types and error cases
- cyrus_hook.py has zero print() calls during test run

---

### 034 — Implement Tier 3 tests: `test_permission_keywords.py`

**Sprint:** 3
**Size:** 0.5 days (12 test cases)
**Description:**
Test PermissionWatcher.handle_response() keyword matching (doc 14, "Tier 3"). Test ALLOW_WORDS and DENY_WORDS matching:
- Match "yes", "allow", "approve", "ok" → allow (4 cases)
- Match "no", "deny", "reject", "cancel" → deny (4 cases)
- No match → no response (2 cases)
- Case insensitive, with filler words (2 cases)

Total 12 cases. No mocking — just keyword matching.

**Reference:** Doc 14, "Tier 3" > test_permission_keywords.py
**Depends on:** 024, 029
**Blocks:** None
**Acceptance Criteria:**
- 12 test cases, all passing
- Tests cover ALLOW_WORDS and DENY_WORDS
- Case-insensitive matching verified

---

### 035 — Implement Tier 3 tests: `test_vad_logic.py`

**Sprint:** 3
**Size:** 1.5 days (15 test cases)
**Description:**
Test VAD state machine logic. Mock Silero model + ring buffer, test transitions:
- Silence → detecting speech (1 case)
- Speech → back to silence (1 case)
- Adaptive silence timeout (1 case)
- Ring buffer wraparound (2 cases)
- Threshold crossing (2 cases)
- Transcription timeout (1 case)
- Model loading error → fallback (1 case)
- Multiple utterances in sequence (3 cases)

Total 15 cases. Use pytest-asyncio for async test methods if VAD is async.

**Reference:** Doc 14, "Tier 3" > test_vad_logic.py
**Depends on:** 029
**Blocks:** None
**Acceptance Criteria:**
- 15 test cases, all passing
- VAD state machine covered
- Timeout and error paths tested

---

### 036 — Implement Tier 4 tests: `test_chat_extraction.py`

**Sprint:** 3
**Size:** 1 day (10 test cases)
**Description:**
Test ChatWatcher._extract_response() with mock UIA trees (doc 14, "Tier 4"). Create mock AutomationElement trees representing VS Code chat UI:
- Response found after anchor (1 case)
- No response yet (1 case)
- Multiple anchors — backtrack correctly (2 cases)
- Tree navigation errors (1 case)
- Empty response (1 case)
- Very long response (1 case)
- Response with code blocks (1 case)
- Focus lost during extraction (1 case)

Total 10 cases. Mock pyautogui, uiautomation modules.

**Reference:** Doc 14, "Tier 4" > test_chat_extraction.py
**Depends on:** 013, 029
**Blocks:** None
**Acceptance Criteria:**
- 10 test cases, all passing
- Mock UIA tree creation documented
- ChatWatcher extraction logic fully covered

---

### 037 — Implement Tier 4 tests: `test_companion_protocol.py`

**Sprint:** 3
**Size:** 1 day (8 test cases)
**Description:**
Test companion extension IPC (doc 14, "Tier 4"). Needed in Sprint 5, but easiest to write now while brain code is fresh. Test JSON line protocol:
- Extension registration message (1 case)
- Focus event (1 case)
- Blur event (1 case)
- Permission response from brain (1 case)
- Prompt response from brain (1 case)
- Connection timeout (1 case)
- Invalid JSON (1 case)
- Reconnection with backoff (1 case)

Total 8 cases. Mock socket, parse JSON lines.

**Reference:** Doc 14, "Tier 4" > test_companion_protocol.py
**Depends on:** 029
**Blocks:** 058, 059, 060, 061
**Acceptance Criteria:**
- 8 test cases, all passing
- Protocol defined and documented
- Socket mocking tested

---

### 038 — Run full test suite and check coverage

**Sprint:** 3
**Size:** 0.5 days (analysis)
**Description:**
Run `pytest tests/ -v --cov=. --cov-report=html`. Review coverage report:
- Pure functions should be >95%
- Stateful logic (watchers, managers) should be >70%
- Integration (main() orchestration) should be >50%

If gaps exist, add targeted tests. Update CONTRIBUTING.md with coverage expectations and commands to run tests locally.

**Reference:** Doc 14
**Depends on:** 030–037
**Blocks:** None
**Acceptance Criteria:**
- Overall coverage >80%
- Pure functions >95%
- Coverage report generated (HTML)
- All tests passing on main branch
- CI/CD (GitHub Actions) runs tests on every PR

---

### 039 — Audit test maintenance plan and add issue tracker

**Sprint:** 3
**Size:** 0.5 days (documentation)
**Description:**
Document in CONTRIBUTING.md:
- How to run tests locally (`pytest tests/`)
- How to add new tests
- Coverage expectations per module type
- When to skip/mark tests (e.g., `@pytest.mark.skip("UIA unavailable on non-Windows")`)
- How CI/CD enforces coverage minimums

Create GitHub issue template for "Bug Report" that includes "Add test case for regression?" section.

**Reference:** Doc 14, 004
**Depends on:** 038
**Blocks:** None
**Acceptance Criteria:**
- CONTRIBUTING.md updated with test guidance
- Test maintenance documented
- CI/CD enforces test pass before merge

---

### 040 — Implement module-level docstrings and type hints

**Sprint:** 3
**Size:** 1 day (cleanup)
**Description:**
Add docstrings to all module files explaining purpose and key components. Add type hints to function signatures (at minimum, extracted functions from Sprint 1). Use Python 3.10+ syntax (e.g., `list[str]` instead of `List[str]`).

Not required to be 100% — focus on public APIs and test-adjacent code.

**Reference:** Best practice
**Depends on:** 008–017 (refactored modules)
**Blocks:** None
**Acceptance Criteria:**
- Module docstrings added to all 7 main modules
- Public function signatures have type hints
- Docstrings follow Google style or NumPy style
- No breaking changes to tests

---

## Sprint 4: Configuration & Auth (5 days)

**Goal:** Add config file support, TCP authentication, and hardcoded constant extraction. Enable non-code tuning.

**Blockers:** Sprint 2 (logging, clean code), Sprint 3 (tests)

---

### 041 — Create centralized constants module

**Sprint:** 4
**Size:** 1 day (extraction + refactor)
**Description:**
Create `cyrus_constants.py` with all hardcoded ports, timeouts, and thresholds from doc 12, section M1/M2:

Ports:
```python
BRAIN_PORT = 8766
HOOK_PORT = 8767
MOBILE_PORT = 8769
SERVER_PORT = 8765
EXTENSION_PORT = 8770  # new, for companion registration
```

Timeouts:
```python
TTS_TIMEOUT = 25.0
SOCKET_TIMEOUT = 10
VAD_TIMEOUT = 30  # silence timeout
POLL_INTERVAL_CHAT = 0.5
POLL_INTERVAL_PERMISSION = 0.3
HOTKEY_DEBOUNCE = 0.2  # new
```

Voice parameters:
```python
SPEECH_THRESHOLD = 0.5
SILENCE_WINDOW = 1.0
MAX_SPEECH_WORDS = 500
```

Update all references in cyrus_brain.py, cyrus_voice.py, cyrus_server.py to import from cyrus_constants.

**Reference:** Doc 12, sections M1, M2; Doc 15, recommendation #5
**Depends on:** 008
**Blocks:** 042, 043, 044
**Acceptance Criteria:**
- `cyrus_constants.py` exists with all constants
- All hardcoded numbers replaced with imports
- No magic numbers remain in code
- All tests still pass

---

### 042 — Create TOML config file support

**Sprint:** 4
**Size:** 1.5 days (config parser + defaults)
**Description:**
Create `cyrus_config.py` that reads `cyrus.toml` (if present) and falls back to environment variables or hardcoded defaults:

```toml
[brain]
port = 8766
log_level = "INFO"

[voice]
model = "medium.en"
tts_timeout = 25.0

[session]
max_aliases = 50
persist_state = true

[wake_word]
phrase = "hey cyrus"
threshold = 0.5
```

API:
```python
from cyrus_config import config
port = config.brain.port  # reads from TOML, env var, or default
```

Priority: env var > TOML > hardcoded default.

**Reference:** Doc 15, recommendation #5; Doc 12, M2
**Depends on:** 041
**Blocks:** 043, 044, 045
**Acceptance Criteria:**
- `cyrus_config.py` exists with config loading
- `cyrus.toml.example` provided as template
- Env vars override TOML
- Defaults work if TOML absent
- All existing code uses config module instead of constants (refactor)

---

### 043 — Add TCP authentication to all listening ports

**Sprint:** 4
**Size:** 1.5 days (auth + testing)
**Description:**
Add shared secret authentication from `.env` (e.g., `CYRUS_TOKEN=my-secret-string`). On connection to any brain port (8766, 8767, 8769, 8770), first message must be `{"auth": "my-secret-string"}`. Brain rejects connection if auth fails.

Update cyrus_voice.py, cyrus_hook.py, mobile clients, and extension (Sprint 5) to send auth on connect.

For localhost-only use (existing setup), make auth optional but log a warning if missing.

**Reference:** Doc 15, recommendation #3
**Depends on:** 041, 042
**Blocks:** 045, 058
**Acceptance Criteria:**
- Auth token loaded from `.env` or env var `CYRUS_TOKEN`
- All ports validate auth before accepting
- Unauthenticated connections logged as WARNING
- cyrus_voice.py sends auth on startup
- Tests verify auth protocol (test_companion_protocol.py)

---

### 044 — Update cyrus.toml with example + documentation

**Sprint:** 4
**Size:** 0.5 days (docs)
**Description:**
Create `cyrus.toml.example` with all available settings, comments explaining each. Update README with "Configuration" section linking to it. Explain env var precedence.

**Reference:** Doc 15, recommendation #5; Doc 12, M2
**Depends on:** 042
**Blocks:** None
**Acceptance Criteria:**
- `cyrus.toml.example` exists with all settings
- README has "Configuration" section
- Env var precedence documented
- Users can `cp cyrus.toml.example cyrus.toml` and customize

---

### 045 — Refactor all hardcoded constants to use config module

**Sprint:** 4
**Size:** 1 day (refactor across files)
**Description:**
Go through cyrus_brain.py, cyrus_voice.py, cyrus_server.py, cyrus_hook.py and replace all remaining hardcoded numbers with config imports. Remove `cyrus_constants.py` (merged into `cyrus_config.py`).

Update all old `from cyrus_constants import` to `from cyrus_config import config`.

**Reference:** Docs 12, 15
**Depends on:** 041, 042, 044
**Blocks:** None
**Acceptance Criteria:**
- No hardcoded ports, timeouts, thresholds in any file
- All config accessed via `config` object
- All tests still pass
- `ruff check .` passes

---

## Sprint 5: Docker & Extension (8 days)

**Goal:** Enable cross-platform deployment via Docker. Add companion extension registration and focus tracking. Make brain runnable without Windows UI dependencies.

**Blockers:** Sprint 2 (logging), Sprint 4 (config + auth)

---

### 046 — Add HEADLESS mode guard to cyrus_brain.py

**Sprint:** 5
**Size:** 1 day (conditional imports)
**Description:**
Add at top of cyrus_brain.py (after imports):
```python
HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1"

if not HEADLESS:
    import comtypes
    import pyautogui
    import pyperclip
    import pygetwindow as gw
    import UIAutomation as automation
    # ... other Windows-only imports
```

Guard all Windows-specific code with `if not HEADLESS:` or try/except blocks. In HEADLESS mode, these features are replaced by companion extension messages (see 047–060).

Modify:
- `_vs_code_windows()` → in headless, return empty (extensions register on their own)
- `_start_active_tracker()` → in headless, skip (no active window polling)
- `ChatWatcher._scan_uia()` → in headless, skip UIA polling, use hook-only
- `PermissionWatcher._scan()` → in headless, skip UIA polling
- `PermissionWatcher.handle_response()` → in headless, send message to companion

**Reference:** Doc 13, "Phase 1: Add `HEADLESS` Mode"
**Depends on:** 042
**Blocks:** 047–050
**Acceptance Criteria:**
- HEADLESS flag works (`CYRUS_HEADLESS=1`)
- All Windows imports guarded
- Code paths work in both modes
- No import errors in headless mode

---

### 047 — Implement extension registration server (port 8770)

**Sprint:** 5
**Size:** 1.5 days (async TCP server)
**Description:**
Add async TCP server on port 8770 (HEADLESS mode only) to handle companion extension registration. Track `_registered_sessions: dict[str, SessionInfo]` with workspace name, connection, and listen port.

On message from extension:
- `{"type": "register", "workspace": "my-project", "safe": "my_project", "port": 8768}` — create ChatWatcher and PermissionWatcher for this session, store connection
- `{"type": "focus", "workspace": "my-project"}` — update `_active_project`
- `{"type": "blur", "workspace": "my-project"}` — clear active if it matches
- (connection closes) — remove session

Send back:
- `{"type": "permission_respond", "action": "allow" | "deny"}` — response to permission dialog
- `{"type": "prompt_respond", "text": "user answer"}` — response to prompt

Keep connection persistent so brain can send messages back to extension.

**Reference:** Doc 13, "Phase 3: Brain-side Registration Listener"
**Depends on:** 046, 043
**Blocks:** 048, 049, 050
**Acceptance Criteria:**
- Server listens on port 8770 in HEADLESS mode
- Sessions registered and tracked
- Messages parsed correctly
- Connections cleaned up on close
- Test in test_companion_protocol.py passes (from Sprint 3)

---

### 048 — Add companion extension bidirectional messaging

**Sprint:** 5
**Size:** 1.5 days (TypeScript + socket handling)
**Description:**
Update `cyrus-companion/src/extension.ts`:

On activate:
- Connect to `config.get("cyrusCompanion.brainHost"):config.get("cyrusCompanion.brainPort")` (default: localhost:8770)
- Send `{"type": "register", "workspace": <name>, "safe": <alias>, "port": <listen_port>}`
- Implement auto-reconnect with exponential backoff (1s, 2s, 4s... up to 30s)

Hook workspace events:
- `vscode.window.onDidChangeWindowState()` → send `{"type": "focus"}` or `{"type": "blur"}`
- `vscode.workspace.onDidChangeWorkspaceFolders()` → update workspace name

Listen for brain messages:
- `{"type": "permission_respond", "action": "allow" | "deny"}` → press "1" for allow, "Escape" for deny
- `{"type": "prompt_respond", "text": "..."}` → inject text as if user typed it

**Reference:** Doc 13, "Phase 2: Companion Extension Registration Protocol"
**Depends on:** 043
**Blocks:** 049, 050
**Acceptance Criteria:**
- Extension connects on startup
- Auto-reconnect works
- Focus/blur events sent
- Brain messages trigger keyboard actions
- All tests pass

---

### 049 — Update companion extension settings

**Sprint:** 5
**Size:** 0.5 days (package.json)
**Description:**
Update `cyrus-companion/package.json` with new settings:
```json
"cyrusCompanion.brainHost": {
  "type": "string",
  "default": "localhost",
  "description": "Brain server host"
},
"cyrusCompanion.brainPort": {
  "type": "integer",
  "default": 8770,
  "description": "Brain registration port"
}
```

**Reference:** Doc 13, "Phase 2"
**Depends on:** 048
**Blocks:** None
**Acceptance Criteria:**
- Settings visible in VS Code extension settings
- Defaults work for localhost
- Remote brain accessible if settings changed

---

### 050 — Create Dockerfile and docker-compose.yml

**Sprint:** 5
**Size:** 1 day (Docker setup)
**Description:**
Create `Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements-brain-headless.txt .
RUN pip install --no-cache-dir -r requirements-brain-headless.txt
COPY cyrus_brain.py cyrus_hook.py cyrus_server.py cyrus_common.py cyrus_log.py cyrus_config.py cyrus_constants.py .env* ./
ENV CYRUS_HEADLESS=1
EXPOSE 8766 8767 8769 8770
CMD ["python", "cyrus_brain.py"]
```

Create `requirements-brain-headless.txt` with minimal deps (no UI libraries):
```
python-dotenv
websockets
faster-whisper
torch
# (no pyautogui, pygetwindow, comtypes, UIAutomation)
```

Create `docker-compose.yml`:
```yaml
services:
  brain:
    build: .
    ports:
      - "8766:8766"
      - "8767:8767"
      - "8769:8769"
      - "8770:8770"
    environment:
      - CYRUS_HEADLESS=1
      - CYRUS_LOG_LEVEL=INFO
      - CYRUS_TOKEN=${CYRUS_TOKEN:-mytoken}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8789/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

**Reference:** Doc 13, "Phase 4: Docker Files"
**Depends on:** 046, 047, 043, 044
**Blocks:** 051
**Acceptance Criteria:**
- Dockerfile builds successfully
- `docker compose up` starts brain without errors
- Brain listens on all 4 ports
- HEADLESS=1 prevents Windows import errors
- Healthcheck endpoint configured (Sprint 6)

---

### 051 — Make cyrus_hook.py configurable for remote brain

**Sprint:** 5
**Size:** 0.5 days (env var)
**Description:**
Update cyrus_hook.py to read brain host from env var:
```python
BRAIN_HOST = os.environ.get("CYRUS_BRAIN_HOST", "localhost")
```

Default remains localhost, so existing setups unaffected. Docker users can set `CYRUS_BRAIN_HOST=brain` (or IP) to connect to container.

**Reference:** Doc 13, "Phase 5"
**Depends on:** 046
**Blocks:** None
**Acceptance Criteria:**
- Env var configurable
- Defaults to localhost
- Hook can connect to Docker brain

---

### 052 — Document Docker quickstart

**Sprint:** 5
**Size:** 1 day (README update)
**Description:**
Add to README:
- "Docker Deployment" section
- Quick start: `docker compose up`
- Configuration: set env vars in `.env` or `docker-compose.yml`
- Multi-platform: works on macOS, Linux, Windows
- Companion extension still runs locally on Windows/macOS/Linux, connects to Docker brain
- Volume mounting for custom config
- Troubleshooting: `docker logs`, log levels

**Reference:** Doc 13, "Phase 6: Documentation"
**Depends on:** 050
**Blocks:** None
**Acceptance Criteria:**
- README includes Docker section
- Quick start commands provided
- Config examples shown
- Troubleshooting guide included

---

## Sprint 6: Polish (6 days)

**Goal:** Add health checks, metrics collection, session persistence, docs updates, and final touches.

**Blockers:** Sprint 5 (Docker), Sprint 4 (config)

---

### 053 — Implement health check HTTP endpoint

**Sprint:** 6
**Size:** 1 day (HTTP server + checks)
**Description:**
Add lightweight HTTP health check endpoint on port 8789 (or configured):

GET `/health` → returns 200 + JSON:
```json
{
  "status": "ok",
  "uptime": 3600,
  "active_sessions": 2,
  "whisper_loaded": true,
  "last_utterance": "2026-03-11T14:32:00Z"
}
```

Use for:
- Docker healthchecks (already in docker-compose.yml)
- Monitoring + alerting
- Troubleshooting (is brain alive?)

**Reference:** Doc 15, recommendation #6
**Depends on:** 042, 046, 047
**Blocks:** 054
**Acceptance Criteria:**
- Endpoint listens on configurable port (default 8789)
- Returns proper HTTP response
- `curl localhost:8789/health` works
- Docker healthcheck uses it
- Monitoring-friendly (Prometheus format optional for future)

---

### 054 — Collect and expose metrics

**Sprint:** 6
**Size:** 1 day (tracking)
**Description:**
Track:
- Utterance count (total, per session, per hour)
- Transcription latency (min/max/avg)
- TTS latency (min/max/avg)
- Permission approval rate (% allowed vs. denied)
- Error count (by type)
- Session duration

Expose via `/metrics` endpoint (or `/health` sub-section). Log stats periodically (every hour at INFO level).

**Reference:** Doc 15, nice-to-have #11
**Depends on:** 053
**Blocks:** None
**Acceptance Criteria:**
- Metrics collected without blocking
- Accessible via endpoint
- Logged hourly
- Aggregated per-session

---

### 055 — Implement session state persistence (JSON)

**Sprint:** 6
**Size:** 1 day (serialization)
**Description:**
On shutdown, save session state to `~/.cyrus/sessions.json`:
```json
{
  "session_1": {
    "project": "backend",
    "aliases": {"api": "api_server", ...},
    "prompt": "You are a helpful assistant..."
  },
  "session_2": {...}
}
```

On startup, restore sessions (if configured in cyrus.toml). This survives brain restarts.

Optional: add `session.persist_state = true/false` in config.

**Reference:** Doc 15, nice-to-have #10
**Depends on:** 042
**Blocks:** None
**Acceptance Criteria:**
- Sessions saved on graceful shutdown
- Sessions restored on startup (if configured)
- No data loss on crash (is optional feature)
- Configurable via cyrus.toml

---

### 056 — Make Whisper model configurable

**Sprint:** 6
**Size:** 0.5 days (config)
**Description:**
Currently hardcoded to `medium.en`. Add to cyrus.toml:
```toml
[voice]
whisper_model = "medium.en"  # or "tiny.en", "base.en", "small.en"
```

Update cyrus_voice.py to load from config. Smaller models reduce memory and latency on weak hardware.

**Reference:** Doc 15, nice-to-have #9
**Depends on:** 042
**Blocks:** None
**Acceptance Criteria:**
- Config option exists
- cyrus_voice.py reads from config
- Defaults to medium.en
- Users can switch to tiny.en or base.en

---

### 057 — Update all documentation

**Sprint:** 6
**Size:** 1.5 days (docs)
**Description:**
Update/create:
- README.md — architecture, quick start, Docker, config, troubleshooting
- CONTRIBUTING.md — dev setup, coding standards, test guidelines
- docs/ARCHITECTURE.md — detailed module descriptions, data flow, diagrams
- docs/DEPLOYMENT.md — Docker, remote brain, extension setup
- docs/CONFIGURATION.md — all config options, env vars, examples
- docs/TROUBLESHOOTING.md — common issues, log levels, debugging

Link all docs from README.

**Reference:** Sprints 0–5 (all features)
**Depends on:** All prior sprints
**Blocks:** None
**Acceptance Criteria:**
- All docs updated and linked
- No references to old code patterns
- Examples work (tested manually)
- Troubleshooting guide covers common issues

---

### 058 — Final ruff check and code cleanup

**Sprint:** 6
**Size:** 0.5 days (linting)
**Description:**
Run `ruff check --fix .` and `ruff format .` on all changes from Sprints 4–6. Commit as "chore: final ruff cleanup before 2.0 release".

**Reference:** Doc 17
**Depends on:** 045–057
**Blocks:** 059
**Acceptance Criteria:**
- `ruff check .` returns zero errors
- `ruff format --check .` passes
- All files properly formatted

---

### 059 — Run full test suite + coverage report

**Sprint:** 6
**Size:** 0.5 days (validation)
**Description:**
Run `pytest tests/ -v --cov=. --cov-report=html`. Verify:
- All tests still passing
- Coverage maintained >80%
- No regressions from Sprints 4–6

Generate final coverage report and commit.

**Reference:** Sprint 3, 038
**Depends on:** 058
**Blocks:** 060
**Acceptance Criteria:**
- All tests pass
- Coverage ≥80%
- No regressions
- Final report generated

---

### 060 — Prepare 2.0 release notes and tagging

**Sprint:** 6
**Size:** 1 day (release prep)
**Description:**
Create `RELEASE_NOTES_2.0.md` summarizing:
- Major features: Docker, companion extension, logging, config, test suite
- Breaking changes: main.py deprecated, config file support required for some features
- Migration guide: how to upgrade from 1.x
- New env vars and settings
- Performance improvements (expected metrics)

Tag version 2.0 with annotated tag and push to main branch.

**Reference:** All sprints
**Depends on:** 057, 059
**Blocks:** None
**Acceptance Criteria:**
- Release notes comprehensive and accurate
- Migration guide helpful
- Tag pushed to main
- Ready for distribution

---

## Appendix: Issue Dependency Graph

```
Sprint 0 (Foundation)
  001 → 002 → 005 → 053 (health)
         ↓
  003 → 036 (tests)

Sprint 1 (Refactor)
  008 (extract common)
    ↓
  009 (dispatch dict)
  010, 011 (subsystems)
  013, 014, 015 (break classes)
  016 (audio/UIA modules)
    ↓
  017 (module boundaries)
    ↓
  018 (ruff cleanup)

Sprint 2 (Quality)
  018 → 019 (logging setup)
    ↓
  020, 021, 022 (logging migration)
    ↓
  023 (exception logging)
    ↓
  024 (thread safety)
  025 (focus guard)
  026 (permission logging)
  027 (file leak)
  028 (dep pinning)

Sprint 3 (Tests)
  003, 008, 029 (setup) → 030–037 (test tiers)
    ↓
  038 (coverage check)
  039 (maintenance plan)
  040 (docstrings/hints)

Sprint 4 (Config)
  008 → 041 (constants)
    ↓
  042 (TOML config)
    ↓
  043 (TCP auth)
  044 (example config)
    ↓
  045 (refactor to use config)

Sprint 5 (Docker)
  042, 043 → 046 (HEADLESS mode)
    ↓
  047 (registration server)
    ↓
  048 (extension messaging)
  049 (settings)
  050 (Docker files)
    ↓
  051 (hook configurable)
  052 (Docker docs)

Sprint 6 (Polish)
  042, 046, 047 → 053 (health)
    ↓
  054 (metrics)
  042 → 055 (persistence)
  042 → 056 (Whisper config)
  All → 057 (docs)
    ↓
  058 (ruff cleanup)
    ↓
  059 (test coverage)
  060 (release)
```

---

## Estimation Notes

**Confidence:** 0.75
- Codebase well-understood from audit docs
- Team experience with Python, Docker, VS Code extension dev assumed
- No blockers identified; risk is implementation complexity (god functions larger than estimated)
- Refactor-heavy early sprints may uncover additional duplication

**Caveats:**
- Assumes 1 developer at junior dev pace (1–3 days per issue)
- Docker phase (Sprint 5) may expand if extension work is more complex
- Test suite (Sprint 3) is large; can be parallelized with other sprints
- Polish (Sprint 6) has flexibility — health checks + metrics + persistence can be descoped if time is tight

**Recommendations:**
- Start with Sprint 0 immediately (infrastructure, fast wins)
- Run Sprints 1 and 3 in parallel if resource-rich (refactor doesn't block tests much)
- Validate Docker deployment (Sprint 5) early with manual testing
- Polish features (Sprint 6) are nice-to-have; prioritize release over feature-completeness

---

**Document generated:** 2026-03-11
**Next step:** Review with team, adjust sprint cadence, assign first issues from Sprint 0.
