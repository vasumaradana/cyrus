# Plan 009: Create cyrus_log module

## Summary

Create `cyrus2/cyrus_log.py` (~40 lines) — a centralized logging setup module. Exposes `setup_logging(name)` which configures a root logger with stderr output, conditional timestamps (DEBUG only), and `CYRUS_LOG_LEVEL` env var control. This is the foundation for replacing 218 bare `print()` calls across the codebase.

## Dependencies

None. The `cyrus2/` directory exists (empty). No other issues must complete first.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/cyrus_log.py` exists | `cyrus2/` is empty | Create file |
| `setup_logging()` function | No logging anywhere | Implement per spec |
| `CYRUS_LOG_LEVEL` env var support | Not read anywhere | Read in `setup_logging()` |
| stderr handler | 218 bare `print()` calls go to stdout | `StreamHandler(sys.stderr)` |
| Conditional timestamp format | No formatting at all | Branch on `level <= logging.DEBUG` |
| Level validation with fallback | N/A | `getattr(logging, level_name, logging.INFO)` |

No existing logging infrastructure in the codebase. All Python files use bare `print()` with ad-hoc prefixes like `[Brain]`, `[Voice]`, `[!]`.

## Design Decisions

### D1. Follow docs/16-logging-system.md exactly

The logging system doc provides the complete reference implementation. The issue acceptance criteria match it 1:1. No deviations needed.

### D2. Correct issue step 8 typo

The issue says "Get root logger via `getattr(logging, name)`" — this is wrong. `getattr(logging, "cyrus")` would try to access a non-existent attribute. The correct call is `logging.getLogger(name)`, which docs/16 uses. The plan follows the docs.

### D3. Format conditional applies to configured level, not per-message

When `CYRUS_LOG_LEVEL=DEBUG`, the timestamp format applies to ALL messages (including INFO, WARNING, ERROR) — not just DEBUG messages. This matches the docs/16 examples where INFO messages show timestamps in DEBUG mode. The format string is chosen once at setup time based on the configured level.

### D4. Level validation edge cases

`getattr(logging, level_name, logging.INFO)` could theoretically return a non-integer for attribute names like `"StreamHandler"`. In practice, `CYRUS_LOG_LEVEL` values will be `DEBUG|INFO|WARNING|ERROR|CRITICAL` or invalid strings. The `getattr` fallback handles all realistic cases correctly. No additional validation needed — matches spec.

### D5. No `__init__.py` needed

Python 3.3+ implicit namespace packages allow `from cyrus2.cyrus_log import setup_logging` without a `cyrus2/__init__.py`. The `cyrus2/` directory already exists. If a future issue (e.g., 001) adds `__init__.py`, it won't conflict.

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Test |
|---|---|---|
| AC1 | `cyrus2/cyrus_log.py` created with `setup_logging()` function | `python3 -c "from cyrus2.cyrus_log import setup_logging"` succeeds |
| AC2 | Accepts optional `name` parameter (defaults to "cyrus") | Call `setup_logging()` with no args → logger name is "cyrus"; call `setup_logging("test")` → logger name is "test" |
| AC3 | Returns configured root logger | Assert return type is `logging.Logger` and `logger.name == name` |
| AC4 | Reads `CYRUS_LOG_LEVEL` env var (defaults to "INFO") | Unset env → level is INFO; set `CYRUS_LOG_LEVEL=DEBUG` → level is DEBUG |
| AC5 | Validates log level and falls back to INFO on invalid value | Set `CYRUS_LOG_LEVEL=INVALID` → level is INFO, no error |
| AC6 | Handler writes to stderr | Capture stderr → contains log output; capture stdout → empty |
| AC7 | Format: `[{name}] {levelname:.1s} {message}` for INFO+ | `setup_logging("cyrus")` at INFO → output matches `[cyrus] I test` |
| AC8 | Format: `{asctime} [{name}] {levelname:.1s} {message}` for DEBUG | `setup_logging("cyrus")` at DEBUG → output matches `HH:MM:SS [cyrus] D test` |
| AC9 | Timestamp format: `%H:%M:%S` | Parse DEBUG output → timestamp matches `\d{2}:\d{2}:\d{2}` |
| AC10 | Handler attached to root logger with `propagate=False` | Assert `logger.propagate is False` and `len(logger.handlers) == 1` |
| AC11 | File is ~40 lines | `wc -l cyrus2/cyrus_log.py` → ~35-45 lines |
| AC12 | Child logger inherits from root | `setup_logging("cyrus")` → `logging.getLogger("cyrus.brain").info("test")` → output appears |

## Implementation Steps

### Step 1: Write the test script

**TDD: tests first.** Create a verification script that exercises all acceptance criteria.

**File**: `cyrus2/test_cyrus_log.py`

```python
"""Verification script for cyrus_log module."""

import io
import logging
import os
import re
import sys

failures = []


def check(label, condition):
    if not condition:
        failures.append(label)
        print(f"  FAIL: {label}")
    else:
        print(f"  OK:   {label}")


def fresh_logger(name):
    """Remove all handlers from a logger so tests don't interfere."""
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging.WARNING)
    return logger


def capture_stderr(fn):
    """Run fn() and return whatever it wrote to stderr."""
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        fn()
    finally:
        sys.stderr = old
    return buf.getvalue()


# ── Reset between tests ──────────────────────────────────────────────────────

print("=== AC1: import succeeds ===")
from cyrus2.cyrus_log import setup_logging
check("import setup_logging", callable(setup_logging))

print("\n=== AC2: default name is 'cyrus' ===")
fresh_logger("cyrus")
log = setup_logging()
check("default name", log.name == "cyrus")

print("\n=== AC3: returns Logger with correct name ===")
fresh_logger("custom")
log2 = setup_logging("custom")
check("returns Logger", isinstance(log2, logging.Logger))
check("name matches", log2.name == "custom")

print("\n=== AC4: reads CYRUS_LOG_LEVEL, defaults to INFO ===")
fresh_logger("test_default")
os.environ.pop("CYRUS_LOG_LEVEL", None)
log3 = setup_logging("test_default")
check("default level is INFO", log3.level == logging.INFO)

fresh_logger("test_debug")
os.environ["CYRUS_LOG_LEVEL"] = "DEBUG"
log4 = setup_logging("test_debug")
check("DEBUG level set", log4.level == logging.DEBUG)

print("\n=== AC5: invalid level falls back to INFO ===")
fresh_logger("test_invalid")
os.environ["CYRUS_LOG_LEVEL"] = "INVALID"
log5 = setup_logging("test_invalid")
check("invalid falls back to INFO", log5.level == logging.INFO)

print("\n=== AC6: handler writes to stderr (not stdout) ===")
fresh_logger("test_stderr")
os.environ["CYRUS_LOG_LEVEL"] = "INFO"
log6 = setup_logging("test_stderr")
stderr_out = capture_stderr(lambda: log6.info("stderr_test"))
check("stderr has output", "stderr_test" in stderr_out)

print("\n=== AC7: INFO format is [{name}] {level:.1s} {message} ===")
fresh_logger("fmt_info")
os.environ["CYRUS_LOG_LEVEL"] = "INFO"
log7 = setup_logging("fmt_info")
out7 = capture_stderr(lambda: log7.info("hello world"))
check("INFO format", out7.strip() == "[fmt_info] I hello world")

print("\n=== AC8+AC9: DEBUG format has HH:MM:SS timestamp ===")
fresh_logger("fmt_debug")
os.environ["CYRUS_LOG_LEVEL"] = "DEBUG"
log8 = setup_logging("fmt_debug")
out8 = capture_stderr(lambda: log8.debug("debug msg"))
ts_pattern = r"^\d{2}:\d{2}:\d{2} \[fmt_debug\] D debug msg$"
check("DEBUG format with timestamp", re.match(ts_pattern, out8.strip()) is not None)

print("\n=== AC10: propagate=False, exactly 1 handler ===")
fresh_logger("test_prop")
os.environ["CYRUS_LOG_LEVEL"] = "INFO"
log9 = setup_logging("test_prop")
check("propagate is False", log9.propagate is False)
check("exactly 1 handler", len(log9.handlers) == 1)

print("\n=== AC12: child logger inherits ===")
fresh_logger("parent")
os.environ["CYRUS_LOG_LEVEL"] = "INFO"
setup_logging("parent")
child = logging.getLogger("parent.child")
out_child = capture_stderr(lambda: child.info("from child"))
check("child output visible", "[parent.child] I from child" in out_child)

# ── Summary ──────────────────────────────────────────────────────────────────

os.environ.pop("CYRUS_LOG_LEVEL", None)

print(f"\n{'='*40}")
if failures:
    print(f"FAILED ({len(failures)}): {', '.join(failures)}")
    sys.exit(1)
else:
    print("All acceptance criteria passed.")
```

**Run** (will fail — module doesn't exist yet):

```bash
cd /home/daniel/Projects/barf/cyrus
python3 cyrus2/test_cyrus_log.py
```

### Step 2: Create `cyrus2/cyrus_log.py`

**File**: `cyrus2/cyrus_log.py`

Write the module following docs/16-logging-system.md exactly:

```python
"""Centralized logging setup for Cyrus.

Call ``setup_logging()`` once at startup in each entry point.
Child loggers inherit the configuration automatically::

    from cyrus_log import setup_logging
    setup_logging("cyrus")

    import logging
    log = logging.getLogger("cyrus.brain")
    log.info("Ready")
"""

import logging
import os
import sys


def setup_logging(name: str = "cyrus") -> logging.Logger:
    """Configure and return the root *name* logger.

    Reads ``CYRUS_LOG_LEVEL`` from the environment (default ``"INFO"``).
    Invalid values silently fall back to INFO.

    * INFO and above  → ``[{name}] {level:.1s} {message}``
    * DEBUG and below → ``{HH:MM:SS} [{name}] {level:.1s} {message}``

    Output goes to *stderr* so ``docker logs`` picks it up.
    """
    level_name = os.environ.get("CYRUS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = "[{name}] {levelname:.1s} {message}"
    if level <= logging.DEBUG:
        fmt = "{asctime} [{name}] {levelname:.1s} {message}"

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt, style="{", datefmt="%H:%M:%S"))

    root = logging.getLogger(name)
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False

    return root
```

**Target**: ~35 lines of code + docstrings ≈ 40 lines total.

### Step 3: Run test script — all tests must pass

```bash
cd /home/daniel/Projects/barf/cyrus
python3 cyrus2/test_cyrus_log.py
```

Expected: `All acceptance criteria passed.`

### Step 4: Run the issue's manual verification commands

```bash
cd /home/daniel/Projects/barf/cyrus

# Test default INFO level
python3 -c "from cyrus2.cyrus_log import setup_logging; log = setup_logging('cyrus'); log.info('test')"
# Expected stderr: [cyrus] I test

# Test DEBUG level with timestamp
CYRUS_LOG_LEVEL=DEBUG python3 -c "from cyrus2.cyrus_log import setup_logging; log = setup_logging('cyrus'); log.debug('test')"
# Expected stderr: HH:MM:SS [cyrus] D test

# Test invalid level falls back to INFO
CYRUS_LOG_LEVEL=INVALID python3 -c "from cyrus2.cyrus_log import setup_logging; log = setup_logging('cyrus'); log.info('test')"
# Expected stderr: [cyrus] I test (no error)

# Test child logger inherits from root
python3 -c "from cyrus2.cyrus_log import setup_logging; setup_logging('cyrus'); import logging; log = logging.getLogger('cyrus.brain'); log.info('from brain')"
# Expected stderr: [cyrus.brain] I from brain
```

### Step 5: Verify line count

```bash
wc -l /home/daniel/Projects/barf/cyrus/cyrus2/cyrus_log.py
```

Target: ~35–45 lines. If over 45, trim docstrings. If under 30, ensure docstring is present.

### Step 6: Clean up test file

Delete `cyrus2/test_cyrus_log.py` — it was a verification scaffold. The module is simple enough that the manual commands in Step 4 serve as the ongoing smoke test.

```bash
rm /home/daniel/Projects/barf/cyrus/cyrus2/test_cyrus_log.py
```

## Risk Assessment

**Low risk.** Single new file, ~40 lines, no dependencies on existing code, no modifications to existing files.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| `cyrus2/` not recognized as package | Import fails | Low | Python 3.3+ implicit namespace packages; test in Step 3 |
| `getattr` returns non-int for unusual env values | Wrong level set | Very low | Only realistic values are log level names; fallback handles the rest |
| Duplicate handlers if `setup_logging()` called twice | Double output | Low | Documented as "call once per entry point"; not a correctness bug |

**Known limitation**: If `setup_logging()` is called multiple times for the same logger name, handlers accumulate. This is acceptable — the function is designed to be called once per entry point at startup. A guard could be added later if needed, but the issue spec doesn't require it and it would add complexity to a deliberately minimal module.
