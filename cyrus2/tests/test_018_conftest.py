"""
Acceptance-driven tests for Issue 018: Setup pytest framework with conftest.

Tests verify every acceptance criterion from the issue:
  - cyrus2/tests/ directory exists
  - cyrus2/tests/conftest.py exists with shared fixtures (mock_logger, mock_config,
    mock_send)
  - requirements-dev.txt includes pytest>=7.0, pytest-asyncio, pytest-mock with
    version specifiers
  - pytest tests/ -v runs without import errors
  - conftest.py documents fixture purpose and usage

Strategy: File system checks for structural assertions; fixture injection tests
verify each conftest fixture works correctly.
"""

import ast
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Paths ──────────────────────────────────────────────────────────────────────
_CYRUS2_DIR = Path(__file__).parent.parent
_TESTS_DIR = _CYRUS2_DIR / "tests"
_CONFTEST_PATH = _TESTS_DIR / "conftest.py"
_REQUIREMENTS_DEV = _CYRUS2_DIR / "requirements-dev.txt"
_INIT_PATH = _TESTS_DIR / "__init__.py"


# ─────────────────────────────────────────────────────────────────────────────
# Structural: directory / file existence
# ─────────────────────────────────────────────────────────────────────────────


class TestDirectoryAndFileStructure:
    """Verify the tests/ directory and required files exist."""

    def test_tests_directory_exists(self) -> None:
        """cyrus2/tests/ directory must exist as the test root."""
        assert _TESTS_DIR.is_dir(), f"Expected tests/ directory at {_TESTS_DIR}"

    def test_conftest_file_exists(self) -> None:
        """cyrus2/tests/conftest.py must exist."""
        assert _CONFTEST_PATH.exists(), f"conftest.py not found at {_CONFTEST_PATH}"

    def test_init_file_exists(self) -> None:
        """cyrus2/tests/__init__.py must exist for package discovery."""
        assert _INIT_PATH.exists(), f"__init__.py not found at {_INIT_PATH}"


# ─────────────────────────────────────────────────────────────────────────────
# requirements-dev.txt: version specifiers
# ─────────────────────────────────────────────────────────────────────────────


class TestRequirementsDevTxt:
    """Verify requirements-dev.txt contains pytest dependencies with version pins."""

    def _read_requirements(self) -> list[str]:
        """Read requirements-dev.txt lines, stripping comments and blanks."""
        assert _REQUIREMENTS_DEV.exists(), "requirements-dev.txt not found"
        lines = _REQUIREMENTS_DEV.read_text().splitlines()
        return [
            line.strip() for line in lines if line.strip() and not line.startswith("#")
        ]

    def test_requirements_has_pytest_with_version(self) -> None:
        """requirements-dev.txt must include pytest with a version specifier (>=7.0)."""
        reqs = self._read_requirements()
        pytest_lines = [
            r
            for r in reqs
            if r.startswith("pytest")
            and "asyncio" not in r
            and "mock" not in r
            and "cov" not in r
        ]
        assert pytest_lines, "No pytest entry in requirements-dev.txt"
        line = pytest_lines[0]
        assert ">=" in line or "==" in line or "~=" in line, (
            f"pytest entry has no version specifier: '{line}'. "
            "Expected e.g. 'pytest>=7.0'"
        )

    def test_requirements_has_pytest_asyncio_with_version(self) -> None:
        """requirements-dev.txt must include pytest-asyncio with a version specifier."""
        reqs = self._read_requirements()
        lines = [r for r in reqs if r.startswith("pytest-asyncio")]
        assert lines, "No pytest-asyncio entry in requirements-dev.txt"
        line = lines[0]
        assert ">=" in line or "==" in line or "~=" in line, (
            f"pytest-asyncio entry has no version specifier: '{line}'. "
            "Expected e.g. 'pytest-asyncio>=0.21.0'"
        )

    def test_requirements_has_pytest_mock_with_version(self) -> None:
        """requirements-dev.txt must include pytest-mock with a version specifier."""
        reqs = self._read_requirements()
        lines = [r for r in reqs if r.startswith("pytest-mock")]
        assert lines, "No pytest-mock entry in requirements-dev.txt"
        line = lines[0]
        assert ">=" in line or "==" in line or "~=" in line, (
            f"pytest-mock entry has no version specifier: '{line}'. "
            "Expected e.g. 'pytest-mock>=3.10.0'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# conftest.py: fixture documentation (docstrings)
# ─────────────────────────────────────────────────────────────────────────────


class TestConftestDocumentation:
    """Verify conftest.py fixtures are documented with docstrings."""

    def _parse_fixtures(self) -> dict[str, ast.FunctionDef]:
        """Parse conftest.py and return dict of fixture name → AST node."""
        source = _CONFTEST_PATH.read_text()
        tree = ast.parse(source)
        fixtures: dict[str, ast.FunctionDef] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    dec_name = ""
                    if isinstance(decorator, ast.Name):
                        dec_name = decorator.id
                    elif isinstance(decorator, ast.Attribute):
                        dec_name = decorator.attr
                    elif isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Name):
                            dec_name = decorator.func.id
                        elif isinstance(decorator.func, ast.Attribute):
                            dec_name = decorator.func.attr
                    if dec_name == "fixture":
                        fixtures[node.name] = node
        return fixtures

    def test_mock_logger_fixture_has_docstring(self) -> None:
        """mock_logger fixture must have a docstring explaining its purpose."""
        fixtures = self._parse_fixtures()
        assert "mock_logger" in fixtures, "mock_logger fixture not found in conftest.py"
        node = fixtures["mock_logger"]
        docstring = ast.get_docstring(node)
        assert docstring, "mock_logger fixture has no docstring"

    def test_mock_config_fixture_has_docstring(self) -> None:
        """mock_config fixture must have a docstring explaining its purpose."""
        fixtures = self._parse_fixtures()
        assert "mock_config" in fixtures, "mock_config fixture not found in conftest.py"
        node = fixtures["mock_config"]
        docstring = ast.get_docstring(node)
        assert docstring, "mock_config fixture has no docstring"

    def test_mock_send_fixture_has_docstring(self) -> None:
        """mock_send fixture must have a docstring explaining its purpose."""
        fixtures = self._parse_fixtures()
        assert "mock_send" in fixtures, "mock_send fixture not found in conftest.py"
        node = fixtures["mock_send"]
        docstring = ast.get_docstring(node)
        assert docstring, "mock_send fixture has no docstring"


# ─────────────────────────────────────────────────────────────────────────────
# Fixture functional tests (use injected conftest fixtures)
# ─────────────────────────────────────────────────────────────────────────────


class TestMockLoggerFixture:
    """Verify mock_logger fixture provides a usable logger instance."""

    def test_mock_logger_is_logger_instance(self, mock_logger: logging.Logger) -> None:
        """mock_logger must be a logging.Logger instance."""
        assert isinstance(mock_logger, logging.Logger), (
            f"Expected logging.Logger, got {type(mock_logger)}"
        )

    def test_mock_logger_has_name(self, mock_logger: logging.Logger) -> None:
        """mock_logger must have a non-empty name for log filtering."""
        assert mock_logger.name, "mock_logger has no name"

    def test_mock_logger_captures_messages(
        self,
        mock_logger: logging.Logger,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Logging through mock_logger should be capturable via caplog."""
        with caplog.at_level(logging.DEBUG, logger=mock_logger.name):
            mock_logger.info("test message from mock_logger")
        assert "test message from mock_logger" in caplog.text

    def test_mock_logger_can_log_at_all_levels(
        self,
        mock_logger: logging.Logger,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """mock_logger must accept debug, info, warning, error, critical calls."""
        with caplog.at_level(logging.DEBUG, logger=mock_logger.name):
            mock_logger.debug("debug msg")
            mock_logger.info("info msg")
            mock_logger.warning("warn msg")
            mock_logger.error("error msg")
            mock_logger.critical("critical msg")
        assert "debug msg" in caplog.text
        assert "info msg" in caplog.text
        assert "warn msg" in caplog.text
        assert "error msg" in caplog.text
        assert "critical msg" in caplog.text


class TestMockConfigFixture:
    """Verify mock_config fixture provides a usable config dict."""

    def test_mock_config_is_dict(self, mock_config: dict) -> None:
        """mock_config must be a dict."""
        assert isinstance(mock_config, dict), f"Expected dict, got {type(mock_config)}"

    def test_mock_config_has_required_keys(self, mock_config: dict) -> None:
        """mock_config must contain sensible default keys for cyrus."""
        required_keys = {"host", "port", "log_level"}
        missing = required_keys - set(mock_config.keys())
        assert not missing, f"mock_config missing keys: {missing}"

    def test_mock_config_host_is_string(self, mock_config: dict) -> None:
        """mock_config['host'] must be a string."""
        assert isinstance(mock_config["host"], str), (
            f"Expected str for host, got {type(mock_config['host'])}"
        )

    def test_mock_config_port_is_int(self, mock_config: dict) -> None:
        """mock_config['port'] must be an integer."""
        assert isinstance(mock_config["port"], int), (
            f"Expected int for port, got {type(mock_config['port'])}"
        )

    def test_mock_config_is_mutable(self, mock_config: dict) -> None:
        """Each test gets its own independent mock_config copy to avoid
        cross-test pollution."""
        original_host = mock_config["host"]
        mock_config["host"] = "mutated-host"
        assert mock_config["host"] == "mutated-host"
        # Verify fixture scope — next call would return fresh copy
        # (confirmed by pytest fixture scoping, not directly testable in same test)
        _ = original_host  # suppress unused variable warning


class TestMockSendFixture:
    """Verify mock_send fixture provides a usable callable mock."""

    def test_mock_send_is_callable(self, mock_send: MagicMock) -> None:
        """mock_send must be callable (for use as IPC send() replacement)."""
        assert callable(mock_send), "mock_send must be callable"

    def test_mock_send_accepts_dict_payload(self, mock_send: MagicMock) -> None:
        """mock_send must accept a dict payload without errors."""
        payload = {"type": "speak", "text": "hello", "project": "test"}
        mock_send(payload)
        mock_send.assert_called_once_with(payload)

    def test_mock_send_records_calls(self, mock_send: MagicMock) -> None:
        """mock_send must record all calls for assertion in tests."""
        mock_send({"type": "chime"})
        mock_send({"type": "pause"})
        assert mock_send.call_count == 2

    def test_mock_send_resets_between_tests(self, mock_send: MagicMock) -> None:
        """Each test receives a fresh mock_send with zero recorded calls."""
        # If fixture scope is function (default), this fresh mock has no prior calls
        assert mock_send.call_count == 0

    def test_mock_send_can_be_configured_to_raise(self, mock_send: MagicMock) -> None:
        """mock_send can be configured to raise exceptions for error-path testing."""
        mock_send.side_effect = ConnectionError("IPC connection refused")
        with pytest.raises(ConnectionError, match="IPC connection refused"):
            mock_send({"type": "speak", "text": "test"})


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and boundary conditions for conftest fixtures."""

    def test_mock_send_empty_payload(self, mock_send: MagicMock) -> None:
        """mock_send must handle empty dict payload without error."""
        mock_send({})
        mock_send.assert_called_once_with({})

    def test_mock_config_log_level_valid(self, mock_config: dict) -> None:
        """mock_config log_level must be a valid logging level string."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        assert mock_config["log_level"] in valid_levels, (
            f"mock_config log_level '{mock_config['log_level']}' not in {valid_levels}"
        )

    def test_conftest_module_has_module_docstring(self) -> None:
        """conftest.py must have a module-level docstring explaining its purpose."""
        source = _CONFTEST_PATH.read_text()
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree)
        assert docstring, "conftest.py has no module-level docstring"
