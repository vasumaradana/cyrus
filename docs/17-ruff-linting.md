# 17 — Ruff Linting & Formatting

## Overview

Add [Ruff](https://docs.astral.sh/ruff/) as the project's linter and formatter. Ruff replaces flake8, pylint, isort, pyupgrade, and black in a single fast Rust-based tool.

## Current State

- No linting or formatting tooling configured
- No `pyproject.toml`, `.flake8`, `.pylintrc`, or pre-commit hooks
- All Python files use inconsistent style

## Implementation Plan

### 1. Create `pyproject.toml`

Add ruff configuration:

```toml
[tool.ruff]
target-version = "py310"
line-length = 88
exclude = [".venv", "cyrus-companion"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]

[tool.ruff.format]
```

**Rule sets:**

| Code | What it catches |
|------|----------------|
| `E` | pycodestyle errors (whitespace, indentation, line length) |
| `F` | pyflakes (unused imports, undefined names, redefined variables) |
| `W` | pycodestyle warnings |
| `I` | isort (import sorting and grouping) |
| `UP` | pyupgrade (modernize syntax for target Python version) |
| `B` | flake8-bugbear (common bug patterns, mutable default args) |

### 2. Create `requirements-dev.txt`

```
ruff
```

### 3. Run auto-fix and format

```bash
pip install ruff
ruff check --fix .
ruff format .
```

**Files affected:**
- `main.py`
- `cyrus_voice.py`
- `cyrus_brain.py`
- `cyrus_server.py`
- `cyrus_hook.py`
- `probe_uia.py`
- `test_permission_scan.py`

### 4. Verify

```bash
ruff check .          # should report zero errors
ruff format --check . # should report all files formatted
```

## Developer Workflow

After implementation, developers should run before committing:

```bash
ruff check --fix .
ruff format .
```

Or configure editor integration — ruff has first-class VS Code support via the [Ruff extension](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff).

## Future Enhancements

- Add pre-commit hook for automatic enforcement
- Add GitHub Actions CI check
- Consider enabling additional rule sets (`SIM`, `RET`, `PTH`) once baseline is clean
