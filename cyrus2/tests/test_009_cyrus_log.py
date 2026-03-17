"""
Acceptance-driven tests for Issue 009: Create cyrus_log module.

These tests verify every acceptance criterion from the issue:
  - cyrus2/cyrus_log.py exists with setup_logging() function
  - Accepts optional name parameter (defaults to "cyrus")
  - Returns configured root logger (logging.Logger instance)
  - Reads CYRUS_LOG_LEVEL env var (defaults to "INFO")
  - Validates log level, falls back to INFO on invalid value
  - Handler writes to stderr
  - Format: [{name}] {levelname:.1s} {message} for INFO/WARNING/ERROR
  - Format: {asctime} [{name}] {levelname:.1s} {message} for DEBUG and below
  - Timestamp format: %H:%M:%S (hours:minutes:seconds)
  - Handler attached to logger with propagate=False
  - File is ~40 lines
"""

import io
import logging
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add cyrus2/ directory to sys.path so `from cyrus_log import ...` resolves
# correctly regardless of which directory pytest is invoked from.
# This matches the pattern used in test_007 and test_008.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

from cyrus_log import setup_logging  # noqa: E402

# Path to the implementation module for line-count test
CYRUS_LOG_PATH = _CYRUS2_DIR / "cyrus_log.py"


def _cleanup_logger(name: str) -> None:
    """Remove all handlers from a logger and reset it to a clean state."""
    logger = logging.getLogger(name)
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True


class TestSetupLoggingExists(unittest.TestCase):
    """Verify setup_logging is importable and callable."""

    def test_setup_logging_exists(self):
        """AC: cyrus_log.py must export a callable setup_logging function."""
        self.assertTrue(
            callable(setup_logging),
            "setup_logging must be a callable function",
        )

    def test_module_file_exists(self):
        """AC: cyrus2/cyrus_log.py must exist on disk."""
        self.assertTrue(
            CYRUS_LOG_PATH.exists(),
            f"cyrus_log.py not found at {CYRUS_LOG_PATH}",
        )


class TestDefaultBehavior(unittest.TestCase):
    """Verify default parameter behaviour — name defaults to 'cyrus', level to INFO."""

    def setUp(self) -> None:
        self._cleanup_names: list[str] = []

    def tearDown(self) -> None:
        for name in self._cleanup_names:
            _cleanup_logger(name)

    def test_default_name_is_cyrus(self) -> None:
        """AC: Accepts optional name parameter — default name must be 'cyrus'."""
        log = setup_logging()
        self._cleanup_names.append("cyrus")
        self.assertEqual(
            log.name,
            "cyrus",
            "setup_logging() default name must be 'cyrus'",
        )

    def test_returns_logger_instance(self) -> None:
        """AC: Returns configured root logger — return type must be logging.Logger."""
        log = setup_logging("test.009.returns")
        self._cleanup_names.append("test.009.returns")
        self.assertIsInstance(
            log,
            logging.Logger,
            "setup_logging() must return a logging.Logger instance",
        )

    def test_default_level_is_info(self) -> None:
        """AC: Reads CYRUS_LOG_LEVEL env var — defaults to INFO when env var absent."""
        saved = os.environ.pop("CYRUS_LOG_LEVEL", None)
        try:
            log = setup_logging("test.009.default.info")
            self._cleanup_names.append("test.009.default.info")
            self.assertEqual(
                log.level,
                logging.INFO,
                f"Default level must be INFO (20), got {log.level}",
            )
        finally:
            if saved is not None:
                os.environ["CYRUS_LOG_LEVEL"] = saved


class TestEnvVarControl(unittest.TestCase):
    """Verify CYRUS_LOG_LEVEL environment variable control."""

    def setUp(self) -> None:
        self._cleanup_names: list[str] = []

    def tearDown(self) -> None:
        for name in self._cleanup_names:
            _cleanup_logger(name)

    def test_reads_env_var_debug(self) -> None:
        """AC: Reads CYRUS_LOG_LEVEL env var — DEBUG sets level to DEBUG (10)."""
        with patch.dict(os.environ, {"CYRUS_LOG_LEVEL": "DEBUG"}):
            log = setup_logging("test.009.env.debug")
            self._cleanup_names.append("test.009.env.debug")
        self.assertEqual(
            log.level,
            logging.DEBUG,
            "CYRUS_LOG_LEVEL=DEBUG must set level to logging.DEBUG (10)",
        )

    def test_reads_env_var_warning(self) -> None:
        """Happy path: CYRUS_LOG_LEVEL=WARNING sets level to WARNING (30)."""
        with patch.dict(os.environ, {"CYRUS_LOG_LEVEL": "WARNING"}):
            log = setup_logging("test.009.env.warning")
            self._cleanup_names.append("test.009.env.warning")
        self.assertEqual(
            log.level,
            logging.WARNING,
            "CYRUS_LOG_LEVEL=WARNING must set level to logging.WARNING (30)",
        )

    def test_invalid_level_falls_back_to_info(self) -> None:
        """AC: Validates log level — invalid value must fall back to INFO silently."""
        with patch.dict(os.environ, {"CYRUS_LOG_LEVEL": "INVALID"}):
            log = setup_logging("test.009.env.invalid")
            self._cleanup_names.append("test.009.env.invalid")
        self.assertEqual(
            log.level,
            logging.INFO,
            "Invalid CYRUS_LOG_LEVEL must silently fall back to INFO (20)",
        )

    def test_env_var_case_insensitive(self) -> None:
        """Edge case: CYRUS_LOG_LEVEL=debug (lowercase) must be uppercased correctly."""
        with patch.dict(os.environ, {"CYRUS_LOG_LEVEL": "debug"}):
            log = setup_logging("test.009.env.lowercase")
            self._cleanup_names.append("test.009.env.lowercase")
        self.assertEqual(
            log.level,
            logging.DEBUG,
            "CYRUS_LOG_LEVEL must be uppercased before lookup — 'debug' must work",
        )

    def test_reads_env_var_error(self) -> None:
        """Happy path: CYRUS_LOG_LEVEL=ERROR sets level to logging.ERROR (40)."""
        with patch.dict(os.environ, {"CYRUS_LOG_LEVEL": "ERROR"}):
            log = setup_logging("test.009.env.error")
            self._cleanup_names.append("test.009.env.error")
        self.assertEqual(
            log.level,
            logging.ERROR,
            "CYRUS_LOG_LEVEL=ERROR must set level to logging.ERROR (40)",
        )


class TestHandlerConfiguration(unittest.TestCase):
    """Verify handler is attached to stderr with propagate=False."""

    def setUp(self) -> None:
        self._cleanup_names: list[str] = []

    def tearDown(self) -> None:
        for name in self._cleanup_names:
            _cleanup_logger(name)

    def test_handler_is_stderr(self) -> None:
        """AC: Handler writes to stderr — StreamHandler.stream must be sys.stderr."""
        log = setup_logging("test.009.handler.stderr")
        self._cleanup_names.append("test.009.handler.stderr")
        stderr_handlers = [
            h
            for h in log.handlers
            if isinstance(h, logging.StreamHandler) and h.stream is sys.stderr
        ]
        self.assertGreater(
            len(stderr_handlers),
            0,
            "At least one StreamHandler pointing to sys.stderr must be attached",
        )

    def test_propagate_is_false(self) -> None:
        """AC: Handler attached with propagate=False to prevent double-logging."""
        log = setup_logging("test.009.propagate")
        self._cleanup_names.append("test.009.propagate")
        self.assertFalse(
            log.propagate,
            "propagate must be False to prevent double-logging via root logger",
        )

    def test_handler_count_is_one(self) -> None:
        """Edge case: setup_logging() must add exactly one handler per call."""
        log = setup_logging("test.009.one.handler")
        self._cleanup_names.append("test.009.one.handler")
        self.assertEqual(
            len(log.handlers),
            1,
            f"setup_logging() must add exactly one handler, got {len(log.handlers)}",
        )


class TestOutputFormats(unittest.TestCase):
    """Verify log output format strings for INFO and DEBUG levels."""

    def setUp(self) -> None:
        self._cleanup_names: list[str] = []

    def tearDown(self) -> None:
        for name in self._cleanup_names:
            _cleanup_logger(name)

    def _capture_output(
        self,
        logger_name: str,
        level: int,
        message: str,
    ) -> str:
        """Configure a logger at the given level and capture one log line."""
        level_name = logging.getLevelName(level)
        with patch.dict(os.environ, {"CYRUS_LOG_LEVEL": level_name}):
            log = setup_logging(logger_name)
        self._cleanup_names.append(logger_name)
        # Redirect handler stream to StringIO for capture without touching sys.stderr
        buf = io.StringIO()
        for handler in log.handlers:
            handler.stream = buf
        log.log(level, message)
        return buf.getvalue()

    def test_info_format_no_timestamp(self) -> None:
        """AC: INFO output must match '[name] I message' — no timestamp."""
        output = self._capture_output("test.009.fmt.info", logging.INFO, "test message")
        self.assertIn(
            "[test.009.fmt.info] I test message",
            output,
            f"INFO format must be '[name] I message', got: {output!r}",
        )

    def test_info_format_no_timestamp_prefix(self) -> None:
        """AC: INFO output must NOT start with HH:MM:SS timestamp prefix."""
        output = self._capture_output("test.009.fmt.info2", logging.INFO, "hello world")
        self.assertNotRegex(
            output,
            r"^\d{2}:\d{2}:\d{2}",
            f"INFO format must NOT have a timestamp prefix, got: {output!r}",
        )

    def test_debug_format_has_timestamp(self) -> None:
        """AC: DEBUG output must start with HH:MM:SS timestamp prefix."""
        output = self._capture_output("test.009.fmt.debug", logging.DEBUG, "debug msg")
        self.assertRegex(
            output,
            r"^\d{2}:\d{2}:\d{2} \[test\.009\.fmt\.debug\] D debug msg",
            f"DEBUG format must start with HH:MM:SS timestamp, got: {output!r}",
        )

    def test_timestamp_format(self) -> None:
        """AC: Timestamp format is %H:%M:%S — must match \\d{2}:\\d{2}:\\d{2}."""
        output = self._capture_output("test.009.fmt.ts", logging.DEBUG, "ts check")
        match = re.match(r"(\d{2}:\d{2}:\d{2})", output)
        self.assertIsNotNone(
            match,
            f"DEBUG output must begin with HH:MM:SS timestamp, got: {output!r}",
        )

    def test_warning_format_no_timestamp(self) -> None:
        """Happy path: WARNING level uses compact format '[name] W message'."""
        output = self._capture_output("test.009.fmt.warn", logging.WARNING, "warn msg")
        self.assertIn(
            "[test.009.fmt.warn] W warn msg",
            output,
            f"WARNING format must be '[name] W message', got: {output!r}",
        )

    def test_error_format_no_timestamp(self) -> None:
        """Happy path: ERROR level uses compact format '[name] E message'."""
        output = self._capture_output("test.009.fmt.err", logging.ERROR, "err msg")
        self.assertIn(
            "[test.009.fmt.err] E err msg",
            output,
            f"ERROR format must be '[name] E message', got: {output!r}",
        )


class TestCustomName(unittest.TestCase):
    """Verify custom name parameter and child logger inheritance."""

    def setUp(self) -> None:
        self._cleanup_names: list[str] = []

    def tearDown(self) -> None:
        for name in self._cleanup_names:
            _cleanup_logger(name)

    def test_custom_name(self) -> None:
        """AC: Accepts optional name parameter — custom name sets logger.name."""
        log = setup_logging("test.009.custom")
        self._cleanup_names.append("test.009.custom")
        self.assertEqual(
            log.name,
            "test.009.custom",
            "Logger name must match the name argument passed to setup_logging()",
        )

    def test_child_logger_inherits(self) -> None:
        """AC: Child loggers inherit from parent — output shows child name."""
        log = setup_logging("test.009.parent")
        self._cleanup_names.append("test.009.parent")
        child = logging.getLogger("test.009.parent.child")
        self._cleanup_names.append("test.009.parent.child")
        # Redirect parent handler to capture child output
        buf = io.StringIO()
        for handler in log.handlers:
            handler.stream = buf
        child.info("from child")
        output = buf.getvalue()
        self.assertIn(
            "[test.009.parent.child] I from child",
            output,
            f"Child logger output must show child name, got: {output!r}",
        )

    def test_child_logger_effective_level(self) -> None:
        """Happy path: Child logger inherits effective level from the parent."""
        log = setup_logging("test.009.parent.level")
        self._cleanup_names.append("test.009.parent.level")
        child = logging.getLogger("test.009.parent.level.child")
        self._cleanup_names.append("test.009.parent.level.child")
        self.assertEqual(
            child.getEffectiveLevel(),
            log.level,
            "Child logger must inherit effective level from parent logger",
        )


class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_file_line_count(self) -> None:
        """AC: File is ~40 lines — must be between 25 and 60 lines."""
        lines = CYRUS_LOG_PATH.read_text().splitlines()
        self.assertGreaterEqual(
            len(lines),
            25,
            f"cyrus_log.py has too few lines: {len(lines)} (minimum 25)",
        )
        self.assertLessEqual(
            len(lines),
            60,
            f"cyrus_log.py has too many lines: {len(lines)} (maximum 60)",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
