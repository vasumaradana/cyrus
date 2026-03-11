---
id=003-Create-requirements-dev-txt
title=Issue 003: Create requirements-dev.txt
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=30341
total_output_tokens=8
total_duration_seconds=34
total_iterations=1
run_count=1
---

# Issue 003: Create requirements-dev.txt

## Sprint
Cyrus 2.0 Rewrite — Foundation (Week 1)

## Priority
High

## References
- docs/17-ruff-linting.md — Ruff as linting tool
- docs/14-test-suite.md — Testing framework requirements

## Description
Create `cyrus2/requirements-dev.txt` with development-only dependencies: pytest, pytest-asyncio, pytest-mock, and ruff. These tools enable automated testing and code quality checks without adding bloat to production requirements.

## Blocked By
- None (can be created in parallel with Issue 001-002)

## Acceptance Criteria
- [ ] File `cyrus2/requirements-dev.txt` exists
- [ ] Contains: `pytest`, `pytest-asyncio`, `pytest-mock`, `ruff`
- [ ] Optional: add pytest-cov for coverage reporting
- [ ] Can be installed with `pip install -r cyrus2/requirements-dev.txt`

## Implementation Steps
1. Navigate to cyrus2/ directory: `cd /home/daniel/Projects/barf/cyrus/cyrus2`
2. Create `requirements-dev.txt` as a new file
3. Add the following dependencies (one per line, no version pins yet):
   ```
   pytest
   pytest-asyncio
   pytest-mock
   ruff
   ```
4. Optional enhancements (can be added later):
   - `pytest-cov` for coverage reporting
   - `pytest-xdist` for parallel test execution
5. Verify file is readable:
   ```bash
   cat requirements-dev.txt
   ```

## Files to Create/Modify
- `cyrus2/requirements-dev.txt` (new file)

## Testing
```bash
# Verify the file exists and is readable
cat cyrus2/requirements-dev.txt

# Install dependencies (optional, if environment supports)
pip install -r cyrus2/requirements-dev.txt

# Verify pytest and ruff are available
pytest --version
ruff --version
```

## Notes
- Development dependencies are separated from production dependencies for cleaner deployments.
- These packages are used during development and CI/CD but not needed in production.
- Pinning versions (Issue 004) will happen separately for both production and dev requirements.
- Once installed, developers can use: `pytest tests/` to run tests and `ruff check/format` for linting.

## Stage Log

### GROOMED — 2026-03-11 17:46:17Z

- **From:** NEW
- **Duration in stage:** 34s
- **Input tokens:** 30,341 (final context: 30,341)
- **Output tokens:** 8
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
