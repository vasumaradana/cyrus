# Verification: Create pyproject.toml with Ruff Config

**Issue**: [001-Create-pyproject-toml-with-ruff-config](/home/daniel/Projects/barf/cyrus/issues/001-Create-pyproject-toml-with-ruff-config.md)
**Status**: COMPLETE
**Created**: 2026-03-16

## Evidence

- `cyrus2/pyproject.toml` exists (created 2026-03-16 11:41)
- Content matches the Config Content Reference from the issue exactly
- File is valid TOML (verified with `tomllib.load()`)

### Acceptance Criteria Verification

| Criterion | Status | Evidence |
|-----------|--------|----------|
| `cyrus2/pyproject.toml` exists with project metadata (name: cyrus, version: 2.0.0, python>=3.10) | PASS | `[project]` section has `name = "cyrus"`, `version = "2.0.0"`, `requires-python = ">=3.10"` |
| Ruff config includes rule sets: E, F, W, I, UP, B | PASS | `select = ["E", "F", "W", "I", "UP", "B"]` in `[tool.ruff.lint]` |
| Target version set to py310, line-length to 88 | PASS | `target-version = "py310"`, `line-length = 88` in `[tool.ruff]` |
| Exclude patterns include `.venv` and `cyrus-companion` | PASS | `exclude = [".venv", "cyrus-companion"]` in `[tool.ruff]` |
| Both `[tool.ruff.lint]` and `[tool.ruff.format]` sections present | PASS | Both sections present (format uses defaults as specified) |

## Verification Steps

- [x] File exists at `cyrus2/pyproject.toml`
- [x] Valid TOML (parsed successfully with Python `tomllib`)
- [x] All 5 acceptance criteria confirmed
- [x] `ruff check` passes (BUILD: 0 errors)
- [x] `ruff format --check` passes (CHECK: already formatted)
- [x] `pytest` passes (26/26 tests pass)

## Pre-Complete Check Fix (2026-03-16)

The build/check/test commands failed because:
1. `.barfrc` used `python` but only `python3` is available on this system
2. `ruff` and `pytest` were not installed

**Fixes applied:**
- Updated `.barfrc` commands to use `cyrus2/.venv/bin/python` and scope to `cyrus2/`
- Created virtual environment at `cyrus2/.venv` using `uv venv`
- Installed `ruff==0.15.6` and `pytest==9.0.2` into the venv using `uv pip install`
- Fixed E501 (line too long) in `cyrus2/tests/test_001_pyproject_config.py` line 207 by splitting chained `.get()` call
- Fixed I001 (unsorted imports) via `ruff --fix`

## Recommendation

All acceptance criteria satisfied. Build/check/test all pass. Issue is complete.
