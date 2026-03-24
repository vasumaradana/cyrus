---
id=001-Create-pyproject-toml-with-ruff-config
title=Issue 001: Create pyproject.toml with Ruff Config
state=COMPLETE
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=160047
total_output_tokens=90
total_duration_seconds=371
total_iterations=5
run_count=4
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
- [] File `cyrus2/pyproject.toml` exists with project metadata (name: cyrus, version: 2.0.0, python>=3.10)
- [] Ruff config includes rule sets: E, F, W, I, UP, B
- [] Target version set to py310, line-length to 88
- [] Exclude patterns include `.venv` and `cyrus-companion`
- [] Both `[tool.ruff.lint]` and `[tool.ruff.format]` sections present

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

### GROOMED — 2026-03-16 17:25:40Z

- **From:** NEW
- **Duration in stage:** 29s
- **Input tokens:** 26,865 (final context: 26,865)
- **Output tokens:** 8
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage

### PLANNED — 2026-03-16 17:26:47Z

- **From:** PLANNED
- **Duration in stage:** 55s
- **Input tokens:** 31,994 (final context: 31,994)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 16%
- **Model:** claude-opus-4-6
- **Trigger:** manual/plan

### COMPLETE — 2026-03-16 17:34:57Z

- **From:** BUILT
- **Duration in stage:** 0s
- **Input tokens:** 0 (final context: 0)
- **Output tokens:** 0
- **Iterations:** 0
- **Model:** 
- **Trigger:** auto/verify

### COMPLETE — 2026-03-16 17:34:57Z

- **From:** COMPLETE
- **Duration in stage:** 392s
- **Input tokens:** 93,379 (final context: 59,777)
- **Output tokens:** 51
- **Iterations:** 2
- **Context used:** 30%
- **Model:** claude-sonnet-4-6
- **Trigger:** manual/build

### COMPLETE — 2026-03-16 17:35:14Z

- **From:** COMPLETE
- **Duration in stage:** 16s
- **Input tokens:** 25,514 (final context: 25,514)
- **Output tokens:** 9
- **Iterations:** 1
- **Context used:** 13%
- **Model:** claude-sonnet-4-6
- **Trigger:** manual/build

### GROOMED — 2026-03-16 17:39:18Z

- **From:** NEW
- **Duration in stage:** 37s
- **Input tokens:** 29,734 (final context: 29,734)
- **Output tokens:** 3
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage

### PLANNED — 2026-03-16 17:40:51Z

- **From:** PLANNED
- **Duration in stage:** 52s
- **Input tokens:** 27,076 (final context: 27,076)
- **Output tokens:** 12
- **Iterations:** 1
- **Context used:** 14%
- **Model:** claude-opus-4-6
- **Trigger:** manual/plan

### PLANNED — 2026-03-16 17:55:41Z

- **From:** PLANNED
- **Duration in stage:** 237s
- **Input tokens:** 73,232 (final context: 42,293)
- **Output tokens:** 50
- **Iterations:** 2
- **Context used:** 21%
- **Model:** claude-sonnet-4-6
- **Trigger:** manual/build

### COMPLETE — 2026-03-16 18:35:06Z

- **From:** BUILT
- **Duration in stage:** 0s
- **Input tokens:** 0 (final context: 0)
- **Output tokens:** 0
- **Iterations:** 0
- **Model:** 
- **Trigger:** auto/verify

### COMPLETE — 2026-03-16 18:35:06Z

- **From:** COMPLETE
- **Duration in stage:** 45s
- **Input tokens:** 30,005 (final context: 30,005)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 15%
- **Model:** claude-sonnet-4-6
- **Trigger:** manual/build
