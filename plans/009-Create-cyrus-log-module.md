# Implementation Plan: Create cyrus_log module

**Issue**: [009-Create-cyrus-log-module](/home/daniel/Projects/barf/cyrus/issues/009-Create-cyrus-log-module.md)
**Created**: 2026-03-16
**PROMPT**: `.claude/prompts/plan.md`

## Gap Analysis

**Already exists**:
- Complete logging system design spec at `docs/16-logging-system.md` with exact code, format strings, and per-module logger names
- `cyrus2/` directory with `pyproject.toml` (Ruff config: E, F, W, I, UP, B rules, py310, line-length 88)
- Test patterns established in `cyrus2/tests/test_001_pyproject_config.py` (unittest, class-based, AC: docstrings, setUpClass, assertion messages)

**Needs building**:
- `cyrus2/cyrus_log.py` — the logging setup module (~40 lines)
- `cyrus2/tests/test_009_cyrus_log.py` — acceptance-driven tests for all 11 acceptance criteria

## Approach

Create a minimal, focused `cyrus_log.py` module that centralizes Python logging configuration. The implementation follows the exact spec from `docs/16-logging-system.md` — a single `setup_logging()` function that configures a named root logger with stderr output, conditional timestamps (DEBUG only), and env var control.

**Why this approach**: The spec is fully defined in the design doc. No architectural decisions needed — just implement exactly what's specified, then verify with comprehensive acceptance tests following the established test_001 pattern.

**Implementation note**: The issue's Step 8 says `getattr(logging, name)` but the design spec correctly uses `logging.getLogger(name)`. Follow the design spec — `getattr(logging, name)` would look up an attribute on the logging module, not get a logger by name.

## Rules to Follow

- `.claude/rules/` — Empty (no project rules defined)
- **Ruff compliance**: Code must pass `ruff check` and `ruff format` with pyproject.toml settings (E, F, W, I, UP, B; line-length 88; py310)
- **Test pattern**: Follow test_001 conventions — unittest, class-based, "AC:" docstrings, assertion messages, setUpClass for shared setup, edge case class

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Write cyrus_log.py | Direct implementation | ~40 lines, no agent needed |
| Write test file | Direct implementation | Follow test_001 pattern |
| Lint check | `ruff check cyrus2/cyrus_log.py` | Verify Ruff compliance |
| Run tests | `python -m pytest cyrus2/tests/test_009_cyrus_log.py` or `python -m unittest` | Verify acceptance |

## Prioritized Tasks

- [x] Create `cyrus2/cyrus_log.py` with `setup_logging()` function (~40 lines)
  - Import `logging`, `sys`, `os`
  - `setup_logging(name: str = "cyrus") -> logging.Logger`
  - Read `CYRUS_LOG_LEVEL` env var, `.upper()`, default "INFO"
  - Validate with `getattr(logging, level_name, logging.INFO)` — falls back to INFO on invalid value
  - Conditional format: `[{name}] {levelname:.1s} {message}` for INFO+, prepend `{asctime}` for DEBUG and below
  - `StreamHandler(sys.stderr)` with `Formatter(fmt, style="{", datefmt="%H:%M:%S")`
  - `logging.getLogger(name)` — set level, add handler, `propagate=False`
  - Return the logger
  - Module docstring explaining usage pattern
- [x] Create `cyrus2/tests/test_009_cyrus_log.py` with acceptance tests (see table below)
- [x] Run Ruff lint + format check on new file
- [x] Run all tests and verify they pass

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| `cyrus2/cyrus_log.py` created with `setup_logging()` | `test_setup_logging_exists` — function is importable and callable | unit |
| Accepts optional `name` parameter (defaults to "cyrus") | `test_default_name_is_cyrus` — returned logger.name == "cyrus" | unit |
| Accepts optional `name` parameter | `test_custom_name` — `setup_logging("test.custom")` returns logger with name "test.custom" | unit |
| Returns configured root logger | `test_returns_logger_instance` — return type is `logging.Logger` | unit |
| Reads `CYRUS_LOG_LEVEL` env var (defaults to "INFO") | `test_default_level_is_info` — without env var, logger.level == logging.INFO | unit |
| Reads `CYRUS_LOG_LEVEL` env var | `test_reads_env_var_debug` — set env var to DEBUG, level == logging.DEBUG | unit |
| Validates log level, falls back to INFO on invalid | `test_invalid_level_falls_back_to_info` — set env var to "INVALID", level == logging.INFO | unit |
| Handler writes to stderr | `test_handler_is_stderr` — handler is StreamHandler, handler.stream is sys.stderr | unit |
| Format: `[{name}] {levelname:.1s} {message}` for INFO+ | `test_info_format_no_timestamp` — capture output, verify `[cyrus] I test message` | unit |
| Format: `{asctime} [{name}] {levelname:.1s} {message}` for DEBUG | `test_debug_format_has_timestamp` — capture output, verify `HH:MM:SS [cyrus] D test message` | unit |
| Timestamp format: `%H:%M:%S` | `test_timestamp_format` — verify timestamp matches `\d{2}:\d{2}:\d{2}` pattern | unit |
| Handler attached with `propagate=False` | `test_propagate_is_false` — logger.propagate is False | unit |
| Child logger inherits from root | `test_child_logger_inherits` — `logging.getLogger("cyrus.brain")` uses parent's handler | unit |
| File is ~40 lines | `test_file_line_count` — file is between 25 and 60 lines | unit |

**No cheating** — cannot claim done without all required tests passing.

## Validation (Backpressure)

- **Tests**: `python -m unittest cyrus2/tests/test_009_cyrus_log.py -v` — all tests pass
- **Lint**: `ruff check cyrus2/cyrus_log.py` — no violations
- **Format**: `ruff format --check cyrus2/cyrus_log.py` — already formatted
- **Existing tests**: `python -m unittest cyrus2/tests/test_001_pyproject_config.py -v` — still passes (no regression)

## Files to Create/Modify

- `cyrus2/cyrus_log.py` — **create new** (~40 lines, logging setup module)
- `cyrus2/tests/test_009_cyrus_log.py` — **create new** (~150-200 lines, acceptance tests)

## Key Decisions

1. **unittest over pytest**: Matching established test_001 pattern. The project plans to adopt pytest (docs/14) but that's a future issue (003). Stay consistent with what exists now.
2. **Test isolation**: Each test must clean up loggers (remove handlers, reset level) to prevent cross-test contamination. Use `setUp`/`tearDown` or `addCleanup` to remove handlers after each test.
3. **Env var testing**: Use `unittest.mock.patch.dict(os.environ, ...)` to safely set/unset CYRUS_LOG_LEVEL without affecting other tests.
4. **Output capture**: Use `io.StringIO` as handler stream replacement or capture stderr to verify format strings produce correct output.
5. **Follow design spec**: Issue Step 8 says `getattr(logging, name)` — this is incorrect (would look up module attribute, not get logger). Use `logging.getLogger(name)` per the design doc.
6. **Import path fix (discovered during build)**: Test was initially written with `from cyrus2.cyrus_log import setup_logging` — this fails because `cyrus2` is not an installed package. The established pattern (from `test_007`, `test_008`) is to add `cyrus2/` to `sys.path` via `Path(__file__).parent.parent` and import directly: `from cyrus_log import setup_logging`. Fixed accordingly.

## Validation Results

All validation passed on 2026-03-16:
- `ruff check` — ✅ All checks passed
- `ruff format --check` — ✅ 2 files already formatted
- `pytest tests/ -v` — ✅ 168 tests passed, 0 failed (all 009 tests + full regression suite)
