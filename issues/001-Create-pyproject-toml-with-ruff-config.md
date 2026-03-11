---
id=001-Create-pyproject-toml-with-ruff-config
title=Issue 001: Create pyproject.toml with Ruff Config
state=PLANNED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=65737
total_output_tokens=33
total_duration_seconds=119
total_iterations=2
run_count=2
---

# Issue 001: Create pyproject.toml with Ruff Config

## Sprint
Cyrus 2.0 Rewrite — Foundation (Week 1)

## Priority
Critical

## References
- docs/17-ruff-linting.md — Ruff rule sets and configuration format
- docs/12-code-audit.md — Code quality baseline

## Description
Create `cyrus2/pyproject.toml` with project metadata and Ruff linting/formatting configuration. This is the foundation for automated code quality checks. Ruff replaces flake8, pylint, isort, pyupgrade, and black with a single fast Rust-based tool.

## Blocked By
- None

## Acceptance Criteria
- [ ] File `cyrus2/pyproject.toml` exists with project metadata (name: cyrus, version: 2.0.0, python>=3.10)
- [ ] Ruff config includes rule sets: E, F, W, I, UP, B
- [ ] Target version set to py310, line-length to 88
- [ ] Exclude patterns include `.venv` and `cyrus-companion`
- [ ] Both `[tool.ruff.lint]` and `[tool.ruff.format]` sections present

## Implementation Steps
1. Navigate to project root: `cd /home/daniel/Projects/barf/cyrus`
2. Create `cyrus2/` directory if it doesn't exist: `mkdir -p cyrus2`
3. Create `cyrus2/pyproject.toml` with the following structure:
   - Project metadata section: `[project]` with name, version, description, requires-python
   - Ruff configuration section: `[tool.ruff]` with target-version, line-length, exclude
   - Lint rules: `[tool.ruff.lint]` with select = ["E", "F", "W", "I", "UP", "B"]
   - Format rules: `[tool.ruff.format]` (empty section, uses defaults)
4. Verify file is valid TOML: `python -m toml cyrus2/pyproject.toml` or similar

## Files to Create/Modify
- `cyrus2/pyproject.toml` (new file)

## Testing
```bash
# Verify the pyproject.toml is valid
cat cyrus2/pyproject.toml

# Once ruff is installed (issue 003), verify config is recognized
ruff config cyrus2/
```

## Config Content Reference
```toml
[project]
name = "cyrus"
version = "2.0.0"
description = "Cyrus 2.0 - AI voice assistant with VS Code integration"
requires-python = ">=3.10"

[tool.ruff]
target-version = "py310"
line-length = 88
exclude = [".venv", "cyrus-companion"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]

[tool.ruff.format]
```

## Rule Set Explanation
- **E**: pycodestyle errors (whitespace, indentation, line length)
- **F**: pyflakes (unused imports, undefined names, redefined variables)
- **W**: pycodestyle warnings
- **I**: isort (import sorting and grouping)
- **UP**: pyupgrade (modernize syntax for target Python version)
- **B**: flake8-bugbear (common bug patterns, mutable default args)

## Stage Log

### GROOMED — 2026-03-11 17:44:54Z

- **From:** NEW
- **Duration in stage:** 42s
- **Input tokens:** 32,989 (final context: 32,989)
- **Output tokens:** 7
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage

### PLANNED — 2026-03-11 19:33:28Z

- **From:** PLANNED
- **Duration in stage:** 77s
- **Input tokens:** 32,748 (final context: 32,748)
- **Output tokens:** 26
- **Iterations:** 1
- **Context used:** 16%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan
