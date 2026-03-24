# Implementation Plan: Create requirements-dev.txt

**Issue**: [003-Create-requirements-dev-txt](/home/daniel/Projects/barf/cyrus/issues/003-Create-requirements-dev-txt.md)
**Created**: 2026-03-16
**PROMPT**: `/home/daniel/Projects/barf/cyrus/prompts/PROMPT_plan.md`

## Gap Analysis

**Already exists**: `cyrus2/` directory (empty). Root-level requirements files (`requirements.txt`, `requirements-brain.txt`, `requirements-voice.txt`) establish the pattern: bare package names, one per line, trailing newline, no version pins. Reference docs `docs/14-test-suite.md` and `docs/17-ruff-linting.md` both specify these dev dependencies.

**Needs building**: Single file `cyrus2/requirements-dev.txt` with 5 packages:
- `pytest` — test runner
- `pytest-asyncio` — async test support
- `pytest-cov` — coverage reporting (AC3 marks optional; including it — standard practice, zero cost)
- `pytest-mock` — mocking fixtures
- `ruff` — linter and formatter

## Approach

**Write the file verbatim with the 5 packages in alphabetical order.** The issue and both reference docs (`docs/14-test-suite.md`, `docs/17-ruff-linting.md`) agree on the required packages. Alphabetical order keeps diffs clean and matches standard Python conventions.

**Why include pytest-cov**: AC3 says "optional" but `docs/14-test-suite.md` references it implicitly (testing framework setup), coverage is standard practice, and listing it costs nothing. Including it now avoids a round-trip later.

**Why no version pins**: Issue 004 explicitly handles pinning for both production and dev dependencies. The existing root-level requirements files all use bare package names — follow the same pattern.

**Why alphabetical order**: Makes diffs cleaner and avoids merge conflicts when adding packages. All 5 packages have `pytest-*` or `ruff` as names, so alphabetical grouping is natural.

## Rules to Follow

- No `.claude/rules/` directory exists in this project — no rule files to reference.

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Create requirements-dev.txt | Direct file write | Single file, fully specified content — no agent needed |
| Verify file content | `python3` validation script | Programmatically check all packages present and ordered |
| Verify pip installability | `pip install --dry-run` | Confirm pip can parse the file without errors |

This issue is simple enough that no subagents or skills are needed.

## Prioritized Tasks

- [x] Create `cyrus2/requirements-dev.txt` with exact content (5 packages, alphabetical, trailing newline)
- [x] Verify file exists and content matches expected packages
- [x] Verify pip can parse the file (dry-run install)

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| AC1: File `cyrus2/requirements-dev.txt` exists | `test -f cyrus2/requirements-dev.txt` | verification |
| AC2: Contains pytest, pytest-asyncio, pytest-mock, ruff | Read file → assert all 4 packages present | verification |
| AC3: Optional: add pytest-cov | Read file → assert pytest-cov present | verification |
| AC4: Installable with `pip install -r` | `pip install --dry-run -r cyrus2/requirements-dev.txt` succeeds | verification |

**No cheating** — cannot claim done without all 4 verifications passing.

## Validation (Backpressure)

- **Content check**: Python script reads file, asserts exact package list `['pytest', 'pytest-asyncio', 'pytest-cov', 'pytest-mock', 'ruff']` in alphabetical order
- **Pip check**: `pip install --dry-run -r cyrus2/requirements-dev.txt` resolves all packages without errors
- **No lint/build**: This is a plain text file — no linting or build step applies

## Files to Create/Modify

- `cyrus2/requirements-dev.txt` (new file) — 5 packages, one per line, alphabetical, trailing newline

## Exact File Content

```
pytest
pytest-asyncio
pytest-cov
pytest-mock
ruff
```

## Risk Assessment

**Minimal risk.** Single new file with 5 lines of text. No code changes, no imports, no runtime impact. Only failure mode is a typo in a package name, caught by the dry-run verification step.
