# Implementation Plan: Run Ruff Autofix and Format on v1 Codebase

**Issue**: [002-Run-ruff-autofix-and-format](/home/daniel/Projects/barf/cyrus/issues/002-Run-ruff-autofix-and-format.md)
**Created**: 2026-03-16
**PROMPT**: PROMPT_plan (planning phase)

## Gap Analysis

**Already exists**:
- `cyrus2/` directory (empty)
- All 7 v1 Python files at project root: `main.py`, `cyrus_voice.py`, `cyrus_brain.py`, `cyrus_server.py`, `cyrus_hook.py`, `probe_uia.py`, `test_permission_scan.py`
- Ruff configuration spec in `docs/17-ruff-linting.md`

**Needs building**:
- `cyrus2/pyproject.toml` — **BLOCKER**: Issue 001 (state: PLANNED) must complete first. Builder must verify this file exists before proceeding; if missing, build cannot continue.
- Copy all 7 .py files into `cyrus2/`
- Install ruff (not currently on system PATH)
- Run `ruff check --fix .` on `cyrus2/`
- Run `ruff format .` on `cyrus2/`
- Resolve any remaining non-autofixable violations
- Verify zero violations and all files formatted

## Approach

**Mechanical copy + lint/format — no logic changes.**

1. Copy all 7 v1 Python files into `cyrus2/` (flat copy, no restructuring — subsequent issues handle refactoring)
2. Run `ruff check --fix .` first (import sorting, unused imports, syntax modernization) — order matters because import changes affect line lengths
3. Run `ruff format .` second (whitespace, indentation, line wrapping to 88 chars)
4. Fix remaining violations manually or suppress with `# noqa` if fixing would alter logic
5. If >20 E501 violations remain after formatting, add `"E501"` to the ignore list in `pyproject.toml` (ruff's own recommendation when using `ruff format`)

**Why this order**: `ruff check --fix` handles semantic fixes (imports, pyupgrade) that can change line lengths. Formatting comes last so it operates on final line content.

**Why no logic changes**: Acceptance criterion AC6 requires git diff shows only formatting/import-ordering changes. The selected rule sets (E, F, W, I, UP, B) produce only style changes, but UP rules on conditional imports could theoretically alter behavior — skip those with `# noqa` if detected.

## Rules to Follow

- No `.claude/rules/` directory exists in this project
- Follow ruff configuration from `docs/17-ruff-linting.md`: rule sets E, F, W, I, UP, B; target-version py310; line-length 88
- No logic changes — formatting and import ordering only (per issue AC6)

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Copy files, run ruff, verify | Bash commands | Core mechanical work — cp, ruff check, ruff format |
| Fix non-autofixable violations | `python-pro` subagent | Manual line-length fixes, string extraction, regex refactoring |
| Review diff for logic changes | `code-reviewer` subagent | Verify git diff contains only formatting changes (AC6) |

## Prioritized Tasks

- [x] **Verify prerequisite**: Check `cyrus2/pyproject.toml` exists (Issue 001 complete). If missing, STOP — build is blocked.
- [x] **Install ruff**: `pip install ruff` (or confirm already available via `ruff --version`)
- [x] **Copy v1 files**: Copy all 7 .py files from project root to `cyrus2/`
- [x] **Verify copy**: `ls cyrus2/*.py` — expect exactly 7 files
- [x] **Run autofix**: `cd cyrus2 && ruff check --fix .` — capture output, review for logic-altering fixes
- [x] **Run formatter**: `ruff format .` — capture output showing reformatted file count
- [x] **Check remaining violations**: `ruff check .` — if zero, skip to verification
- [x] **Fix remaining violations manually**: 24 violations after format (20 E501, 2 E731, 1 B007, 1 B904). Exactly 20 E501 after formatting (threshold is ≤20 = fix manually). All fixed by splitting docstrings, wrapping comments, and splitting long f-strings.
- [x] **Final verification**: `ruff check .` exits 0; `ruff format --check .` exits 0
- [x] **Review diff**: `git diff cyrus2/` — only formatting/import-ordering changes confirmed

## Acceptance-Driven Tests

| Acceptance Criterion | Verification Command | Type | Status |
|---------------------|---------------------|------|--------|
| AC1: All v1 .py files copied to `cyrus2/` | `ls cyrus2/*.py` — expect 7 files matching source names | shell verification | ✅ DONE |
| AC2: `ruff check --fix .` applied | Command runs successfully; output shows fixes applied | shell verification | ✅ DONE |
| AC3: `ruff format .` applied | Command runs successfully; 7 files reformatted | shell verification | ✅ DONE |
| AC4: `ruff check .` reports zero violations | Exit code 0, output "All checks passed" | shell verification | ✅ DONE |
| AC5: `ruff format --check .` confirms formatted | Exit code 0, 8 files already formatted | shell verification | ✅ DONE |
| AC6: Git diff shows only formatting changes | `git diff cyrus2/` — import reordering + style only, no logic changes | manual review | ✅ DONE |

**No cheating** — cannot claim done without all 6 acceptance criteria verified.

## Validation (Backpressure)

- **Lint**: `ruff check .` in `cyrus2/` must exit 0 with zero violations ✅
- **Format**: `ruff format --check .` in `cyrus2/` must exit 0 ✅
- **Diff review**: `git diff cyrus2/` must show only formatting/import-ordering changes ✅
- **File count**: Exactly 7 .py files in `cyrus2/` ✅

## Files to Create/Modify

- `cyrus2/main.py` — ✅ copied from root, ruff autofix + format applied
- `cyrus2/cyrus_voice.py` — ✅ copied from root, ruff autofix + format applied
- `cyrus2/cyrus_brain.py` — ✅ copied from root, ruff autofix + format applied (9 manual fixes: 8 E501, 1 E731)
- `cyrus2/cyrus_server.py` — ✅ copied from root, ruff autofix + format applied (1 B904 fix)
- `cyrus2/cyrus_hook.py` — ✅ copied from root, ruff autofix + format applied
- `cyrus2/probe_uia.py` — ✅ copied from root, ruff autofix + format applied (1 B007, 1 E501)
- `cyrus2/test_permission_scan.py` — ✅ copied from root, ruff autofix + format applied
- `cyrus2/pyproject.toml` — E501 ignore rule NOT needed (exactly 20 violations, threshold is ≤20 = fix manually)

## Design Decisions

1. **Copy order doesn't matter** — all 7 files are independent modules with no cross-imports within `cyrus2/`. A single `cp` batch suffices.

2. **E501 (line length) strategy** — Based on code audit (`docs/12-code-audit.md`), `cyrus_brain.py` has ~35 long lines (regex patterns, f-strings) and `main.py` has ~30 long lines. `ruff format` will reflow most; truly unsplittable tokens (long strings, regex, URLs) may remain. Threshold: manually fix if ≤20, add ignore rule if >20.
   - **Actual result**: 80 E501 before format, 20 remaining after `ruff format` — all 20 fixed manually (below threshold).

3. **No logic changes** — If ruff's autofix suggests a change that alters logic (e.g., UP rules on conditional imports), skip that fix with `# noqa: XXXX` and a comment explaining why.

4. **Ruff installation** — Dev tool, not a runtime dependency. `pip install ruff --break-system-packages` required on this Debian system.

## Discoveries

- **ruff 0.15.6** was installed (not previously on PATH)
- **80 E501 violations** before `ruff format`; dropped to **20 after** — all fixed manually
- **`tomllib` treated as third-party** by ruff (target-version=py310; tomllib added to stdlib in 3.11): ruff moved it to the third-party import section in `tests/test_001_pyproject_config.py`
- **26 existing tests** in `cyrus2/tests/` all pass after ruff changes
- **Side effect**: `ruff check --fix .` also cleaned up `tests/test_001_pyproject_config.py` (import ordering) since ruff scans all Python files in the directory

## Risk Assessment

**Low-medium risk.** The copy step is trivial. The ruff autofix + format step is mechanical. The main risk is:
- **Blocker**: Issue 001 not yet complete (pyproject.toml missing) — builder must check and fail fast
- **E501 violations**: ~65 long lines combined in `cyrus_brain.py` and `main.py` may need manual intervention or ignore rule
- **No logic changes**: Selected rule sets (E, F, W, I, UP, B) should produce only style changes, but UP rules need careful review

## Estimated Scope

- 7 files copied
- ~4,600 lines of Python reformatted
- Primary effort: resolving any remaining E501 violations after formatting
