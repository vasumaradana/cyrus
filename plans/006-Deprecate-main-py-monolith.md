# Implementation Plan: Deprecate main.py monolith

**Issue**: [006-Deprecate-main-py-monolith](/home/daniel/Projects/barf/cyrus/issues/006-Deprecate-main-py-monolith.md)
**Created**: 2026-03-16
**PROMPT**: `prompts/PROMPT_plan.md`

## Gap Analysis

**Already exists**:
- `cyrus_brain.py` — fully functional brain service with `async def main() -> None` (line 1696) and its own `__main__` block (line 1767) using `asyncio.run(main())`
- `cyrus_voice.py` — fully functional voice service (all voice/TTS/VAD code duplicated from main.py)
- `README.md` — already documents split mode as primary architecture (Quick Start only references brain + voice)
- Split architecture is operational — brain on port 8766, voice connects to it

**Needs building**:
- Replace `main.py` (currently 1,756-line monolith) with ~25-line thin wrapper
- Add deprecation warning printed on startup
- Update `README.md`: add main.py to Project Structure (currently absent), add "Deprecated: Monolith Mode" section
- Update `cyrus_brain.py` module docstring to mark it as PRIMARY ENTRY POINT
- Create `tests/test_deprecation.py` with 6 acceptance tests

**Blocker status — Issue 005**:
The issue declares "Blocked By: Issue 005 (Extract shared code into cyrus_common.py)". Currently `cyrus_common.py` does NOT exist and `cyrus_brain.py` does NOT import from it. However, **this blocker is soft for Issue 006**: the thin wrapper only needs `from cyrus_brain import main as brain_main`, and `cyrus_brain.py` works independently right now. The builder should verify the import works in Step 1. If `cyrus_brain.py` has broken imports (due to partial Issue 005 work), that's the real blocker — not the absence of `cyrus_common.py` per se.

## Approach

**Complete replacement, not incremental gutting.** Replace the entire 1,756-line `main.py` with a ~25-line wrapper that:
1. Prints a prominent deprecation warning via `print()` (consistent with project style — no logging yet per Issue 009/010)
2. Imports and delegates to `cyrus_brain.main()` via `asyncio.run()`
3. Handles `KeyboardInterrupt` for clean shutdown

**Why `print()` not `logging`**: The entire codebase uses `print()` throughout. Logging migration is Issue 009/010. Using `logging.getLogger().warning()` here would be the only file using logging, creating inconsistency.

**Why full replacement**: Surgically removing functions is risky — easier to miss dead code. The old content is preserved in git history. Every function in the monolith already exists in `cyrus_voice.py` or `cyrus_brain.py`.

**Two deliberately-dropped functions**:
- `_remote_route()` — experimental monolith-only WebSocket. Split architecture handles remote voice natively (`cyrus_voice.py --host <brain-ip>`)
- `startup_sequence()` — monolith-specific greeting. Brain + voice each have their own startup messages

## Rules to Follow

No `.claude/rules/` directory exists in the cyrus project. Follow these project conventions instead:
- **print() for output** — no logging module (project-wide pattern, logging is Issue 009/010)
- **Google-style docstrings** — per `python-pro.md` agent spec
- **Type hints on all functions** — `def main() -> None:`
- **PEP 8 compliance** — enforced via ruff
- **Static tests preferred** — runtime tests require audio hardware + Windows UIA, use AST/string analysis instead

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Implement wrapper + docstring changes | `python-pro` subagent | Senior Python dev, type-safe code, PEP 8 |
| Validate refactoring | `code-reviewer` subagent | Post-implementation review if needed |
| Lint/format | `ruff` (CLI tool) | `ruff check` + `ruff format` on changed files |

## Prioritized Tasks

- [x] **1. Verify prerequisite**: Confirm `from cyrus_brain import main` works (Python import check). If it fails, stop and report blocker.
- [x] **2. Replace main.py with thin wrapper**: Overwrite entire file with ~25-line deprecation wrapper that imports `brain_main` and calls `asyncio.run(brain_main())`
- [x] **3. Update cyrus_brain.py docstring**: Add "PRIMARY ENTRY POINT" and deprecation note for main.py to the module docstring
- [x] **4a. Update README — Project Structure**: Created `cyrus2/README.md` with Project Structure section listing `main.py — DEPRECATED monolith wrapper`
- [x] **4b. Update README — Deprecated section**: Added "Deprecated: Monolith Mode" section with migration instructions
- [x] **5. Verify no critical code lost**: Confirmed all main.py functions exist in cyrus_voice.py or cyrus_brain.py (static verification via tests)
- [x] **6. Lint and format**: Run `ruff check` + `ruff format` on main.py and cyrus_brain.py — all pass
- [x] **7. Write tests**: Created `cyrus2/tests/test_deprecation.py` with 8 static acceptance tests (split TestReadme into 2 tests)
- [x] **8. Run tests**: All 8 new tests pass; 34 total tests pass (0 failures)

## Implementation Details

### Task 2: main.py thin wrapper

```python
"""
Cyrus - All-in-one monolith mode (DEPRECATED)

This was the original single-process mode that combined voice, brain, and TTS.
It is maintained only as a thin wrapper for backward compatibility.

Recommended: Use split mode instead:
    python cyrus_brain.py &
    python cyrus_voice.py
"""

import asyncio
import sys

from cyrus_brain import main as brain_main


def main() -> None:
    print(
        "\n"
        "⚠️  DEPRECATION WARNING: main.py monolith mode is deprecated.\n"
        "Use split mode instead:\n"
        "  python cyrus_brain.py &\n"
        "  python cyrus_voice.py\n"
        "Split mode allows independent restart and clearer separation of concerns.\n"
    )
    asyncio.run(brain_main())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Cyrus] Shutting down.")
        sys.exit(0)
```

### Task 3: cyrus_brain.py docstring change

Change first line from:
```
cyrus_brain.py — Service 2: Logic / VS Code Watcher
```
To:
```
cyrus_brain.py — Service 2: Logic / VS Code Watcher (PRIMARY ENTRY POINT)

This is the recommended entry point for Cyrus. main.py is deprecated; use this directly.
```

### Task 4b: README "Deprecated: Monolith Mode" section

Insert after Project Structure:
```markdown
## Deprecated: Monolith Mode

> **⚠️ `main.py` is deprecated and will be removed in Cyrus 3.0.**

The original `main.py` combined voice I/O and brain logic in a single process.
It now delegates to `cyrus_brain.py` and logs a deprecation warning on startup.

**Use split mode instead** (documented in Quick Start above). If you previously
ran `python main.py`, switch to:

    python cyrus_brain.py &
    python cyrus_voice.py

No configuration changes needed — split mode uses the same `.env` and hooks.
```

### Task 7: Test file — `tests/test_deprecation.py`

6 static tests using AST parsing and string matching (no runtime execution needed):

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_main_is_thin_wrapper` | main.py ≤ 30 lines |
| 2 | `test_main_docstring_says_deprecated` | Module docstring contains "DEPRECATED" |
| 3 | `test_main_imports_brain_main` | Contains `from cyrus_brain import main` |
| 4 | `test_main_prints_deprecation_warning` | Contains "DEPRECATION" + references both services |
| 5 | `test_readme_documents_deprecation` | README has "deprecated" + "Monolith Mode" |
| 6 | `test_brain_docstring_marks_primary` | cyrus_brain.py docstring contains "PRIMARY" |

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| `main.py` refactored to thin wrapper | `test_main_is_thin_wrapper` (≤30 lines) | unit (static) |
| Deprecation warning logged on startup | `test_main_prints_deprecation_warning` | unit (static) |
| All business logic removed from main.py | `test_main_is_thin_wrapper` (line count proves no logic) | unit (static) |
| main.py imports and delegates to cyrus_brain.py | `test_main_imports_brain_main` | unit (static) |
| Documentation updated: recommend split mode | `test_readme_documents_deprecation` | unit (static) |
| Tests confirm wrapper forwards calls correctly | `test_main_imports_brain_main` + `test_main_prints_deprecation_warning` | unit (static) |

**No cheating** — cannot claim done without all 6 tests passing.

## Validation (Backpressure)

- **Tests**: `python -m pytest tests/test_deprecation.py -v` — all 6 pass
- **Lint**: `ruff check main.py cyrus_brain.py` — no violations
- **Format**: `ruff format --check main.py cyrus_brain.py` — already formatted
- **Compile**: `python -m py_compile main.py` — no syntax errors
- **Line count**: `wc -l main.py` — ≤ 30 lines

## Files to Create/Modify

- **Modify**: `main.py` — replace 1,756-line monolith with ~25-line thin wrapper
- **Modify**: `cyrus_brain.py` — update module docstring (first 2-3 lines only)
- **Modify**: `README.md` — add main.py to Project Structure + add Deprecated section
- **Create**: `tests/test_deprecation.py` — 6 acceptance tests
- **Create**: `tests/` directory (if it doesn't exist)

## Risk Notes

1. **Import side effects**: `from cyrus_brain import main as brain_main` executes cyrus_brain.py's module-level code at import time (comtypes/uiautomation try/except). Acceptable — same code runs when executed directly.

2. **asyncio.run() nesting**: The wrapper calls `asyncio.run(brain_main())`. Safe because main.py is only run as a script, never imported. `asyncio.run()` is the standard pattern.

3. **Issue 005 complete for cyrus2/**: `cyrus2/cyrus_common.py` already exists (Issue 005 was done). The import `from cyrus_brain import main` succeeds.

4. **Tests are static only**: No runtime testing (would require audio hardware, Windows UIA, VS Code). Runtime verification is manual. Static tests validate file structure, content, and documentation.

5. **Two functions deliberately dropped**: `_remote_route()` and `startup_sequence()` exist only in old main.py and are not migrated. Split architecture replaces their functionality.

## Implementation Notes (Builder Discoveries)

- **Plan referenced root files; issue targeted cyrus2/**: The plan was generated by examining root-level files (root `main.py` = 1,755 lines, root `cyrus_brain.py` has `async def main()` at line 1696). However, the issue says "Cyrus 2.0 Rewrite — Sprint 1" and specifies `cyrus2/main.py`. Implementation correctly targeted `cyrus2/` files.
- **README created (not modified)**: `cyrus2/README.md` did not exist; created fresh with Project Structure + Deprecated section.
- **8 tests (not 6)**: TestReadmeDocumentsDeprecation was split into `test_readme_exists` + `test_readme_documents_deprecation` for clearer failure messages; total test count is 8.
- **30-line limit exactly met**: After ruff auto-fix (adding blank line between stdlib/local imports), `main.py` is exactly 30 lines.
- **Final validation (2026-03-16)**: All 109 tests pass (8 deprecation + 101 others), ruff check clean, ruff format clean. Issue 007 tests also pass — `CommandResult` and dispatch table were already implemented.
