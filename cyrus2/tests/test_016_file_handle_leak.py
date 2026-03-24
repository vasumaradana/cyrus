"""Acceptance-driven tests for Issue 016: Fix file handle leak in
_open_companion_connection.

Tests verify every acceptance criterion from the issue:
  - File handle wrapped in `with` statement
  - Exception handling added for missing/unreadable port file
  - Exception handling added for invalid port number
  - Error messages logged (printed) appropriately
  - File handle always closes even on exception
  - Existing port file reading functionality preserved

Strategy: Static analysis (AST) for structural checks; runtime tests mock
Windows dependencies so the module imports cleanly on any platform.
"""

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Mock Windows-specific modules BEFORE any cyrus_brain import ───────────────
# cyrus_brain.py imports Windows-only packages at the module level.
# Mock them in sys.modules first so the import succeeds on any platform.
_WIN_MODS = [
    "comtypes",
    "comtypes.gen",
    "uiautomation",
    "pyautogui",
    "pygetwindow",
    "pyperclip",
    "websockets",
    "websockets.exceptions",
    "websockets.legacy",
    "websockets.legacy.server",
]
for _mod in _WIN_MODS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Add cyrus2/ directory to sys.path so imports resolve correctly.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

import cyrus_brain  # noqa: E402

# Path for static analysis.
BRAIN_PY = _CYRUS2_DIR / "cyrus_brain.py"


# ── AC: File handle wrapped in `with` statement (AST structural check) ────────


class TestFileHandleStructural(unittest.TestCase):
    """AC: open() inside _open_companion_connection must use a with statement."""

    @classmethod
    def setUpClass(cls):
        cls.brain_source = BRAIN_PY.read_text(encoding="utf-8")
        cls.brain_tree = ast.parse(cls.brain_source)

    def _find_function(self, name: str) -> ast.FunctionDef | None:
        """Return the FunctionDef node for the named function."""
        for node in ast.walk(self.brain_tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    def test_open_is_inside_with_statement_in_open_companion_connection(self):
        """AC: open() call must appear inside a 'with' context manager, not bare."""
        func = self._find_function("_open_companion_connection")
        self.assertIsNotNone(
            func, "_open_companion_connection function not found in cyrus_brain.py"
        )

        # Walk the function body looking for bare open() calls (not inside With)
        bare_open_calls = []

        def _find_bare_opens(node, inside_with=False):
            """Recursively find open() calls that are not inside a With node."""
            if isinstance(node, ast.With):
                # Collect context expressions (the things after 'with')
                for item in node.items:
                    ctx = item.context_expr
                    # Check if the context expression itself is a call to open()
                    if isinstance(ctx, ast.Call):
                        func_node = ctx.func
                        if isinstance(func_node, ast.Name) and func_node.id == "open":
                            # This is 'with open(...) as ...' — correct usage
                            pass
                # Walk body with inside_with=True
                for child in ast.iter_child_nodes(node):
                    _find_bare_opens(child, inside_with=True)
            elif isinstance(node, ast.Call):
                func_node = node.func
                if isinstance(func_node, ast.Name) and func_node.id == "open":
                    if not inside_with:
                        bare_open_calls.append(
                            f"Line {node.lineno}: bare open() call found"
                        )
                for child in ast.iter_child_nodes(node):
                    _find_bare_opens(child, inside_with)
            else:
                for child in ast.iter_child_nodes(node):
                    _find_bare_opens(child, inside_with)

        _find_bare_opens(func)
        self.assertEqual(
            bare_open_calls,
            [],
            "Bare open() calls found in _open_companion_connection "
            "(must be wrapped in 'with'):\n" + "\n".join(bare_open_calls),
        )

    def test_with_open_pattern_present_in_function(self):
        """AC: 'with open(port_file) as f:' pattern must appear in the function."""
        func = self._find_function("_open_companion_connection")
        self.assertIsNotNone(func)

        # Find With nodes in the function that use open() as context manager
        with_open_found = False
        for node in ast.walk(func):
            if isinstance(node, ast.With):
                for item in node.items:
                    ctx = item.context_expr
                    if (
                        isinstance(ctx, ast.Call)
                        and isinstance(ctx.func, ast.Name)
                        and ctx.func.id == "open"
                    ):
                        with_open_found = True
        self.assertTrue(
            with_open_found,
            "No 'with open(...)' pattern found in _open_companion_connection",
        )

    def test_no_bare_open_in_entire_open_companion_connection_source(self):
        """AC: Source text of function must not contain bare 'int(open(' pattern."""
        # This is a text-level check as a belt-and-suspenders guard
        source_lines = self.brain_source.splitlines()
        func = self._find_function("_open_companion_connection")
        self.assertIsNotNone(func)

        func_lines = source_lines[func.lineno - 1 : func.end_lineno]
        violations = [
            f"Line {func.lineno + i}: {line.strip()}"
            for i, line in enumerate(func_lines)
            if "int(open(" in line and not line.strip().startswith("#")
        ]
        self.assertEqual(
            violations,
            [],
            "Found bare 'int(open(' pattern in _open_companion_connection — "
            "must use 'with open(...) as f:' instead:\n" + "\n".join(violations),
        )


# ── AC: FileNotFoundError handling ────────────────────────────────────────────


class TestFileNotFoundHandling(unittest.TestCase):
    """AC: FileNotFoundError raised and logged when port file is missing."""

    def test_file_not_found_propagates_on_windows(self):
        """AC: FileNotFoundError re-raised when port file does not exist."""
        with patch("os.name", "nt"):
            with patch("os.environ.get", return_value="/fake/localappdata"):
                with patch("os.path.join", return_value="/nonexistent/path/port.file"):
                    with patch(
                        "builtins.open", side_effect=FileNotFoundError("not found")
                    ):
                        with self.assertRaises(FileNotFoundError):
                            cyrus_brain._open_companion_connection("test_workspace")

    def test_file_not_found_logged_as_error(self):
        """AC: log.error() called when port file not found."""
        with patch("os.name", "nt"):
            with patch("os.environ.get", return_value="/fake/localappdata"):
                with patch(
                    "os.path.join", return_value="/nonexistent/companion-test.port"
                ):
                    with patch(
                        "builtins.open", side_effect=FileNotFoundError("not found")
                    ):
                        with patch.object(cyrus_brain.log, "error") as mock_log_error:
                            try:
                                cyrus_brain._open_companion_connection("test")
                            except FileNotFoundError:
                                pass
                            mock_log_error.assert_called_once()

    def test_file_not_found_message_includes_port_file_path(self):
        """AC: Diagnostic log message includes the port file path for context."""
        fake_port_path = "/fake/localappdata/cyrus/companion-myworkspace.port"
        with patch("os.name", "nt"):
            with patch("os.environ.get", return_value="/fake/localappdata"):
                with patch("os.path.join", return_value=fake_port_path):
                    with patch(
                        "builtins.open", side_effect=FileNotFoundError("not found")
                    ):
                        with patch.object(cyrus_brain.log, "error") as mock_log_error:
                            try:
                                cyrus_brain._open_companion_connection("myworkspace")
                            except FileNotFoundError:
                                pass
                            # Verify the port file path appears in the log call args
                            call_args = mock_log_error.call_args
                            self.assertIsNotNone(
                                call_args, "log.error must have been called"
                            )
                            args_str = " ".join(str(a) for a in call_args.args)
                            self.assertIn(
                                fake_port_path,
                                args_str,
                                f"Expected port file path '{fake_port_path}'"
                                " in log.error args",
                            )


# ── AC: ValueError handling ───────────────────────────────────────────────────


class TestValueErrorHandling(unittest.TestCase):
    """AC: ValueError raised and logged when port file contains invalid content."""

    def test_invalid_port_content_propagates_value_error(self):
        """AC: ValueError re-raised when port file contains non-integer content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".port", delete=False) as tmp:
            tmp.write("not_a_number\n")
            tmp_path = tmp.name

        try:
            with patch("os.name", "nt"):
                with patch("os.environ.get", return_value="/fake"):
                    with patch("os.path.join", return_value=tmp_path):
                        with self.assertRaises(ValueError):
                            cyrus_brain._open_companion_connection("test")
        finally:
            os.unlink(tmp_path)

    def test_invalid_port_logged_as_error(self):
        """AC: log.error() called when port file content is invalid."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".port", delete=False) as tmp:
            tmp.write("garbage_port\n")
            tmp_path = tmp.name

        try:
            with patch("os.name", "nt"):
                with patch("os.environ.get", return_value="/fake"):
                    with patch("os.path.join", return_value=tmp_path):
                        with patch.object(cyrus_brain.log, "error") as mock_log_error:
                            try:
                                cyrus_brain._open_companion_connection("test")
                            except ValueError:
                                pass
                            mock_log_error.assert_called_once()
        finally:
            os.unlink(tmp_path)

    def test_invalid_port_message_includes_port_file_path(self):
        """AC: Diagnostic log message for invalid port includes the file path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".port", delete=False) as tmp:
            tmp.write("invalid\n")
            tmp_path = tmp.name

        try:
            with patch("os.name", "nt"):
                with patch("os.environ.get", return_value="/fake"):
                    with patch("os.path.join", return_value=tmp_path):
                        with patch.object(cyrus_brain.log, "error") as mock_log_error:
                            try:
                                cyrus_brain._open_companion_connection("test")
                            except ValueError:
                                pass
                            call_args = mock_log_error.call_args
                            self.assertIsNotNone(
                                call_args, "log.error must have been called"
                            )
                            args_str = " ".join(str(a) for a in call_args.args)
                            self.assertIn(
                                tmp_path,
                                args_str,
                                f"Expected port file path '{tmp_path}'"
                                " in log.error args",
                            )
        finally:
            os.unlink(tmp_path)

    def test_empty_port_file_raises_value_error(self):
        """Edge case: empty port file should raise ValueError (int('') fails)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".port", delete=False) as tmp:
            tmp.write("")
            tmp_path = tmp.name

        try:
            with patch("os.name", "nt"):
                with patch("os.environ.get", return_value="/fake"):
                    with patch("os.path.join", return_value=tmp_path):
                        with self.assertRaises(ValueError):
                            cyrus_brain._open_companion_connection("test")
        finally:
            os.unlink(tmp_path)

    def test_float_port_content_raises_value_error(self):
        """Edge case: float string like '8766.5' is not a valid int port."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".port", delete=False) as tmp:
            tmp.write("8766.5\n")
            tmp_path = tmp.name

        try:
            with patch("os.name", "nt"):
                with patch("os.environ.get", return_value="/fake"):
                    with patch("os.path.join", return_value=tmp_path):
                        with self.assertRaises(ValueError):
                            cyrus_brain._open_companion_connection("test")
        finally:
            os.unlink(tmp_path)


# ── AC: File handle always closes even on exception ──────────────────────────


class TestFileHandleAlwaysCloses(unittest.TestCase):
    """AC: File handle __exit__ called even when ValueError or
    FileNotFoundError raised."""

    def test_file_handle_closed_on_value_error(self):
        """AC: Context manager __exit__ invoked when ValueError raised inside
        with block."""
        mock_file = MagicMock()
        # Make int() conversion fail by returning non-numeric content from read()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)  # don't suppress exceptions
        mock_file.read.return_value = "not_a_number"

        with patch("os.name", "nt"):
            with patch("os.environ.get", return_value="/fake"):
                with patch("os.path.join", return_value="/fake/port.file"):
                    with patch("builtins.open", return_value=mock_file):
                        try:
                            cyrus_brain._open_companion_connection("test")
                        except ValueError:
                            pass

        # __exit__ must have been called (this is the with-statement cleanup)
        mock_file.__exit__.assert_called_once()
        args = mock_file.__exit__.call_args[0]
        # The exception type passed to __exit__ should be ValueError
        self.assertIs(
            args[0],
            ValueError,
            "ValueError should have been passed to __exit__ for context"
            " manager cleanup",
        )

    def test_file_handle_closed_on_success(self):
        """AC: File handle still closed in the normal (no-exception) path."""
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = "8766"

        mock_socket = MagicMock()
        mock_socket_instance = MagicMock()
        mock_socket.return_value = mock_socket_instance

        with patch("os.name", "nt"):
            with patch("os.environ.get", return_value="/fake"):
                with patch("os.path.join", return_value="/fake/port.file"):
                    with patch("builtins.open", return_value=mock_file):
                        with patch("socket.socket", mock_socket):
                            cyrus_brain._open_companion_connection("test")

        # __exit__ must have been called with no exception (None, None, None)
        mock_file.__exit__.assert_called_once_with(None, None, None)


# ── AC: Existing port file reading functionality preserved ────────────────────


class TestPortFileReadingFunctionality(unittest.TestCase):
    """AC: Valid port file content correctly parsed and used for socket connection."""

    def test_valid_port_number_read_and_used(self):
        """AC: Valid port file with '8766' leads to connect('127.0.0.1', 8766)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".port", delete=False) as tmp:
            tmp.write("8766\n")
            tmp_path = tmp.name

        mock_socket_cls = MagicMock()
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        try:
            with patch("os.name", "nt"):
                with patch("os.environ.get", return_value="/fake"):
                    with patch("os.path.join", return_value=tmp_path):
                        with patch("socket.socket", mock_socket_cls):
                            result = cyrus_brain._open_companion_connection("test")
        finally:
            os.unlink(tmp_path)

        # Verify connect was called with the correct host and port
        mock_sock.connect.assert_called_once_with(("127.0.0.1", 8766))
        # Verify the socket was returned
        self.assertEqual(result, mock_sock)

    def test_valid_port_with_whitespace_stripped(self):
        """AC: Port value with surrounding whitespace/newline is correctly parsed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".port", delete=False) as tmp:
            tmp.write("  9000  \n")
            tmp_path = tmp.name

        mock_socket_cls = MagicMock()
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        try:
            with patch("os.name", "nt"):
                with patch("os.environ.get", return_value="/fake"):
                    with patch("os.path.join", return_value=tmp_path):
                        with patch("socket.socket", mock_socket_cls):
                            cyrus_brain._open_companion_connection("test")
        finally:
            os.unlink(tmp_path)

        mock_sock.connect.assert_called_once_with(("127.0.0.1", 9000))

    def test_unix_path_uses_af_unix_socket(self):
        """AC: On non-Windows (os.name != 'nt'), AF_UNIX socket is used
        (no file read)."""
        mock_socket_cls = MagicMock()
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        with patch("os.name", "posix"):
            with patch("socket.socket", mock_socket_cls):
                # On Unix, connect is called directly (no port file involved)
                cyrus_brain._open_companion_connection("test_workspace")

        # Verify AF_UNIX socket was created
        import socket as _socket

        mock_socket_cls.assert_called_once_with(_socket.AF_UNIX, _socket.SOCK_STREAM)

    def test_socket_timeout_set_to_10(self):
        """AC: Socket timeout preserved at 10 seconds."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".port", delete=False) as tmp:
            tmp.write("8766\n")
            tmp_path = tmp.name

        mock_socket_cls = MagicMock()
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        try:
            with patch("os.name", "nt"):
                with patch("os.environ.get", return_value="/fake"):
                    with patch("os.path.join", return_value=tmp_path):
                        with patch("socket.socket", mock_socket_cls):
                            cyrus_brain._open_companion_connection("test")
        finally:
            os.unlink(tmp_path)

        mock_sock.settimeout.assert_called_once_with(10)


# ── AC: Exception handling structure present in source ────────────────────────


class TestExceptionHandlingStructure(unittest.TestCase):
    """AC: FileNotFoundError and ValueError handlers present in source."""

    @classmethod
    def setUpClass(cls):
        cls.brain_source = BRAIN_PY.read_text(encoding="utf-8")
        cls.brain_tree = ast.parse(cls.brain_source)

    def _find_function(self, name: str) -> ast.FunctionDef | None:
        for node in ast.walk(self.brain_tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    def _find_except_types_in_function(self, func_node: ast.FunctionDef) -> list[str]:
        """Return all exception type names caught in except clauses within the
        function."""
        caught = []
        for node in ast.walk(func_node):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    caught.append("bare_except")
                elif isinstance(node.type, ast.Name):
                    caught.append(node.type.id)
                elif isinstance(node.type, ast.Tuple):
                    for elt in node.type.elts:
                        if isinstance(elt, ast.Name):
                            caught.append(elt.id)
        return caught

    def test_file_not_found_error_caught_in_function(self):
        """AC: FileNotFoundError explicitly caught in _open_companion_connection."""
        func = self._find_function("_open_companion_connection")
        self.assertIsNotNone(func)
        caught = self._find_except_types_in_function(func)
        self.assertIn(
            "FileNotFoundError",
            caught,
            "FileNotFoundError not found in except handlers of"
            " _open_companion_connection",
        )

    def test_value_error_caught_in_function(self):
        """AC: ValueError explicitly caught in _open_companion_connection."""
        func = self._find_function("_open_companion_connection")
        self.assertIsNotNone(func)
        caught = self._find_except_types_in_function(func)
        self.assertIn(
            "ValueError",
            caught,
            "ValueError not found in except handlers of _open_companion_connection",
        )

    def test_exceptions_are_reraised(self):
        """AC: Both caught exceptions are re-raised (raise statement present)."""
        func = self._find_function("_open_companion_connection")
        self.assertIsNotNone(func)

        # Count raise statements inside except handlers
        raise_count = 0
        for node in ast.walk(func):
            if isinstance(node, ast.ExceptHandler):
                for child in ast.walk(node):
                    if isinstance(child, ast.Raise) and child.exc is None:
                        # Bare 'raise' — re-raise
                        raise_count += 1

        self.assertGreaterEqual(
            raise_count,
            2,
            f"Expected at least 2 bare 'raise' statements in except handlers,"
            f" found {raise_count}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
