# Plan: Issue 018 — Setup pytest framework with conftest

## Gap Analysis

| Component | Status | Notes |
|-----------|--------|-------|
| `cyrus2/tests/` directory | ✅ Exists | Has test files from issues 001–017 |
| `cyrus2/tests/__init__.py` | ✅ Created | Empty package marker |
| `cyrus2/tests/conftest.py` | ✅ Created | 3 fixtures: mock_logger, mock_config, mock_send |
| `requirements-dev.txt` deps | ✅ Updated | All 5 packages now have version specifiers |
| `pytest tests/ -v` runs clean | ✅ Verified | 395 tests collected, 0 import errors |

## Prioritized Tasks

- [x] 1. Create plan file (this file)
- [x] 2. Write acceptance-driven tests in `test_018_conftest.py` (TDD first)
- [x] 3. Create `cyrus2/tests/__init__.py` (empty)
- [x] 4. Create `cyrus2/tests/conftest.py` with fixtures: `mock_logger`, `mock_config`, `mock_send`
- [x] 5. Update `requirements-dev.txt` with version specifiers (`pytest>=7.0`, `pytest-asyncio>=0.21.0`, `pytest-mock>=3.10.0`)
- [x] 6. Run `pytest tests/ -v` to verify no import errors
- [x] 7. Update plan with completions

## Acceptance-Driven Tests

| Acceptance Criterion | Test | Status |
|---------------------|------|--------|
| `cyrus2/tests/` directory exists | `test_tests_directory_exists` | ✅ PASS |
| `cyrus2/tests/conftest.py` exists | `test_conftest_file_exists` | ✅ PASS |
| `requirements-dev.txt` has pytest>=7.0 | `test_requirements_has_pytest_with_version` | ✅ PASS |
| `requirements-dev.txt` has pytest-asyncio | `test_requirements_has_pytest_asyncio_with_version` | ✅ PASS |
| `requirements-dev.txt` has pytest-mock | `test_requirements_has_pytest_mock_with_version` | ✅ PASS |
| `mock_logger` fixture works | `test_mock_logger_is_logger_instance` | ✅ PASS |
| `mock_config` fixture provides dict | `test_mock_config_is_dict` | ✅ PASS |
| `mock_send` fixture is callable | `test_mock_send_is_callable` | ✅ PASS |
| Fixtures are documented | `test_*_fixture_has_docstring` (3 tests) | ✅ PASS |
| pytest runs without import errors | `pytest tests/ --collect-only` → 395 items | ✅ PASS |

**Test result: 26/26 passed in 0.02s**

## Files Created/Modified

- **CREATED** `cyrus2/tests/__init__.py` — empty package marker
- **CREATED** `cyrus2/tests/conftest.py` — shared fixtures (mock_logger, mock_config, mock_send)
- **CREATED** `cyrus2/tests/test_018_conftest.py` — 26 acceptance-driven tests
- **MODIFIED** `cyrus2/requirements-dev.txt` — added version specifiers to all 5 packages

## Notes

- Existing tests use `unittest.TestCase` style — conftest fixtures use pytest style, both work fine together
- `tmp_path` is pytest's built-in fixture; conftest documents this in its module docstring rather than re-defining it
- `mock_config` defaults mirror argparse config: host, port, log_level, voice_host, voice_port
- `mock_send` is a `MagicMock()` for the IPC `_send()` callable pattern, reset per test (function scope)
- pytest version: 9.0.2 (well above >=7.0 requirement)

## Open Questions

None — all tasks complete.
