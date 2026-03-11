---
id=018-Setup-pytest-framework-with-conftest
title=Issue 018: Setup pytest framework with conftest
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=40628
total_output_tokens=4
total_duration_seconds=85
total_iterations=1
run_count=1
---

# Issue 018: Setup pytest framework with conftest

## Sprint
Sprint 3 — Test Suite

## Priority
Critical

## References
- [docs/14-test-suite.md — File Structure](../docs/14-test-suite.md#file-structure)
- [docs/14-test-suite.md — Verification](../docs/14-test-suite.md#verification)

## Description
Initialize pytest testing infrastructure with conftest.py containing shared fixtures. This provides the foundation for all test tiers and ensures consistent test setup/teardown across the suite. Must include pytest + pytest-asyncio in requirements-dev.txt.

## Blocked By
- Issue 003 (requirements-dev.txt)

## Acceptance Criteria
- [ ] `cyrus2/tests/` directory created
- [ ] `cyrus2/tests/conftest.py` exists with shared fixtures (at minimum: tmp_path, mock_logger, mock_config)
- [ ] `requirements-dev.txt` includes pytest>=7.0, pytest-asyncio, pytest-mock
- [ ] `pytest tests/ -v` runs without import errors
- [ ] conftest.py documents fixture purpose and usage

## Implementation Steps
1. Create `cyrus2/tests/` directory structure
2. Create `cyrus2/tests/conftest.py` with:
   - `@pytest.fixture` for `tmp_path` (reusable temp directories)
   - `@pytest.fixture` for `mock_logger` (capture/verify log output)
   - `@pytest.fixture` for `mock_config` (test config dict with sensible defaults)
   - `@pytest.fixture` for `mock_send` (callable to mock IPC send)
3. Add pytest dependencies to `requirements-dev.txt`:
   ```
   pytest>=7.0
   pytest-asyncio>=0.21.0
   pytest-mock>=3.10.0
   ```
4. Verify imports work: `from conftest import *` succeeds in test files
5. Add `__init__.py` to `cyrus2/tests/` (empty, for package discovery)

## Files to Create/Modify
- `cyrus2/tests/__init__.py` (empty)
- `cyrus2/tests/conftest.py` (fixtures)
- `requirements-dev.txt` (add dependencies)

## Testing
```bash
cd cyrus2
pip install -r ../requirements-dev.txt
pytest tests/ -v --collect-only  # Should list all test items (0 for now)
pytest tests/conftest.py -v  # Should import without error
```

## Stage Log

### GROOMED — 2026-03-11 18:23:19Z

- **From:** NEW
- **Duration in stage:** 85s
- **Input tokens:** 40,628 (final context: 40,628)
- **Output tokens:** 4
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
