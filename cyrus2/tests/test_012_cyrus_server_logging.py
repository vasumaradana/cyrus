"""
Acceptance-driven tests for Issue 012: Replace print() calls in cyrus_server.py.

These tests verify every acceptance criterion from the issue using static
source-code analysis (grep/source text) rather than runtime execution.  Runtime
testing is impractical because cyrus_server.py depends on the websockets package
and an async event loop, but correctness of the logging migration can be fully
verified by inspecting the source.

Acceptance criteria tested:
  - No remaining print() calls
  - import logging added
  - from cyrus2.cyrus_log import setup_logging added
  - log = logging.getLogger("cyrus.server") defined at module level
  - setup_logging("cyrus") called inside main()
  - 3 log.info() calls present (lifecycle events)
  - 1 log.debug() call present (routing decision)
  - 0 log.error() calls (no error patterns in original)
  - No f-strings used in log.*() calls
  - File compiles without errors
"""

import ast
import py_compile
import re
import unittest
from pathlib import Path

# Path to the file under test
SERVER_PATH = Path(__file__).parent.parent / "cyrus_server.py"


def _source() -> str:
    """Return the full source text of cyrus_server.py."""
    return SERVER_PATH.read_text(encoding="utf-8")


class TestServerFileExists(unittest.TestCase):
    """Prerequisite: the source file must be present."""

    def test_file_exists(self):
        """AC: cyrus2/cyrus_server.py must exist."""
        self.assertTrue(
            SERVER_PATH.exists(),
            f"cyrus_server.py not found at {SERVER_PATH}",
        )


class TestNoPrintCalls(unittest.TestCase):
    """AC: All 4 print() calls replaced — none must remain."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_no_print_calls_remain(self):
        """AC: grep for print( in source must return 0 matches."""
        lines_with_print = [
            (i + 1, line)
            for i, line in enumerate(self.src.splitlines())
            if re.search(r"\bprint\s*\(", line) and not line.lstrip().startswith("#")
        ]
        self.assertEqual(
            lines_with_print,
            [],
            f"Found remaining print() calls on lines: "
            f"{[ln for ln, _ in lines_with_print]}",
        )

    def test_no_new_print_calls_introduced(self):
        """AC: No new print() calls introduced — same as no remaining print() calls."""
        count = len(
            [
                line
                for line in self.src.splitlines()
                if re.search(r"\bprint\s*\(", line)
                and not line.lstrip().startswith("#")
            ]
        )
        self.assertEqual(
            count,
            0,
            f"Expected 0 print() calls remaining, found {count}",
        )


class TestImports(unittest.TestCase):
    """AC: Required imports must be present."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_logging_import(self):
        """AC: 'import logging' must appear in the file."""
        self.assertIn(
            "import logging",
            self.src,
            "Missing 'import logging' in cyrus_server.py",
        )

    def test_setup_logging_import(self):
        """AC: 'from cyrus2.cyrus_log import setup_logging' must appear."""
        self.assertIn(
            "from cyrus2.cyrus_log import setup_logging",
            self.src,
            "Missing 'from cyrus2.cyrus_log import setup_logging' in cyrus_server.py",
        )


class TestLoggerDefinition(unittest.TestCase):
    """AC: Module-level logger 'log' must be defined with the correct name."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_logger_name(self):
        """AC: log = logging.getLogger('cyrus.server') must be defined."""
        self.assertIn(
            'log = logging.getLogger("cyrus.server")',
            self.src,
            'Missing: log = logging.getLogger("cyrus.server") in cyrus_server.py',
        )

    def test_logger_is_module_level(self):
        """Logger must be defined at module level (not inside a function/class)."""
        lines = self.src.splitlines()
        for i, line in enumerate(lines):
            if 'log = logging.getLogger("cyrus.server")' in line:
                # Must not be indented (module-level = no leading whitespace)
                self.assertFalse(
                    line.startswith(" ") or line.startswith("\t"),
                    f"Logger defined inside a function/class at line {i + 1}: {line!r}",
                )
                return
        self.fail("Logger definition not found in source")


class TestSetupLoggingInMain(unittest.TestCase):
    """AC: setup_logging('cyrus') must be called inside main()."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_setup_logging_in_main(self):
        """AC: setup_logging('cyrus') must appear inside main()."""
        # Extract the body of main() — everything after 'def main():' up to EOF
        match = re.search(
            r"^def main\(\)[^\n]*\n(.*?)(?=^(?:async )?def |\Z)",
            self.src,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, "main() function not found in cyrus_server.py")
        main_body = match.group(1)
        self.assertIn(
            'setup_logging("cyrus")',
            main_body,
            'setup_logging("cyrus") not called inside main()',
        )


class TestLogLevelCalls(unittest.TestCase):
    """AC: Correct log levels used for each print() replacement."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_info_calls_count(self):
        """AC: Exactly 3 log.info() calls (connected, disconnected, listening)."""
        count = self.src.count("log.info(")
        self.assertEqual(
            count,
            3,
            f"Expected exactly 3 log.info() calls, found {count}",
        )

    def test_debug_calls_count(self):
        """AC: Exactly 1 log.debug() call (routing decision per-utterance)."""
        count = self.src.count("log.debug(")
        self.assertEqual(
            count,
            1,
            f"Expected exactly 1 log.debug() call, found {count}",
        )

    def test_no_error_calls(self):
        """AC: 0 log.error() calls — no error patterns in original prints."""
        count = self.src.count("log.error(")
        self.assertEqual(
            count,
            0,
            f"Expected 0 log.error() calls (no error patterns), found {count}",
        )

    def test_info_calls_present(self):
        """AC: log.info() must be called at least once (lifecycle events)."""
        self.assertIn(
            "log.info(",
            self.src,
            "No log.info() calls found — lifecycle events not converted",
        )

    def test_debug_calls_present(self):
        """AC: log.debug() must be called at least once (routing decision)."""
        self.assertIn(
            "log.debug(",
            self.src,
            "No log.debug() calls found — routing decision not converted",
        )


class TestNoFstringsInLogCalls(unittest.TestCase):
    """AC: All log.*() calls must use %s-style formatting, not f-strings."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_no_fstrings_in_log_calls(self):
        """AC: No f-string inside a log.*() call argument."""
        lines = self.src.splitlines()
        violations = []
        for i, line in enumerate(lines):
            # Match any log call that contains an f-string argument
            if re.search(r"\blog\.\w+\s*\(.*f['\"]", line):
                violations.append((i + 1, line.strip()))
        self.assertEqual(
            violations,
            [],
            f"Found f-strings inside log calls on lines: "
            f"{[ln for ln, _ in violations]}",
        )


class TestFileCompiles(unittest.TestCase):
    """AC: File still has same functionality; only logging mechanism changed."""

    def test_file_compiles(self):
        """AC: cyrus_server.py must compile without syntax errors."""
        try:
            py_compile.compile(str(SERVER_PATH), doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"cyrus_server.py failed to compile: {e}")


class TestASTStructure(unittest.TestCase):
    """AST-based structural checks."""

    @classmethod
    def setUpClass(cls):
        source = SERVER_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(source)
        cls.src = source

    def test_no_print_calls_ast(self):
        """AC: AST walk finds 0 print() call nodes."""
        print_calls = []
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                print_calls.append(node.lineno)
        self.assertEqual(
            print_calls,
            [],
            f"Found print() calls at lines: {print_calls}",
        )

    def test_import_logging_in_ast(self):
        """AC: AST finds 'import logging' statement."""
        found = any(
            isinstance(node, ast.Import)
            and any(alias.name == "logging" for alias in node.names)
            for node in ast.walk(self.tree)
        )
        self.assertTrue(found, "No 'import logging' found in AST")

    def test_get_logger_call_in_ast(self):
        """AC: AST finds logging.getLogger('cyrus.server') call."""
        found = False
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getLogger"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logging"
            ):
                # Check for "cyrus.server" argument
                if node.args and isinstance(node.args[0], ast.Constant):
                    if node.args[0].value == "cyrus.server":
                        found = True
        self.assertTrue(found, 'logging.getLogger("cyrus.server") not found in AST')

    def test_no_fstring_in_log_call_args_ast(self):
        """AC: No JoinedStr (f-string) as first argument to log.*() calls."""
        violations = []
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("debug", "info", "warning", "error", "critical")
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "log"
            ):
                if node.args and isinstance(node.args[0], ast.JoinedStr):
                    violations.append(node.lineno)
        self.assertEqual(
            violations,
            [],
            f"Found f-strings as first arg in log.*() calls at lines: {violations}",
        )

    def test_total_log_call_count_ast(self):
        """Total log.*() calls must be exactly 4 (replacing the 4 print() calls)."""
        log_calls = []
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("debug", "info", "warning", "error", "critical")
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "log"
            ):
                log_calls.append((node.lineno, node.func.attr))
        self.assertEqual(
            len(log_calls),
            4,
            f"Expected exactly 4 log.*() calls, found {len(log_calls)}: {log_calls}",
        )


class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_setup_logging_import_before_logger_definition(self):
        """setup_logging import must appear before logger definition in file."""
        import_pos = self.src.find("from cyrus2.cyrus_log import setup_logging")
        logger_pos = self.src.find('log = logging.getLogger("cyrus.server")')
        self.assertGreater(
            import_pos,
            -1,
            "setup_logging import not found",
        )
        self.assertGreater(
            logger_pos,
            -1,
            "logger definition not found",
        )
        self.assertLess(
            import_pos,
            logger_pos,
            "setup_logging import must appear before logger definition",
        )

    def test_unicode_arrow_replaced_with_ascii(self):
        """Unicode right arrow (→) must not appear in log calls."""
        lines = self.src.splitlines()
        violations = []
        for i, line in enumerate(lines):
            if re.search(r"\blog\.\w+\s*\(", line) and "\u2192" in line:
                violations.append((i + 1, line.strip()))
        self.assertEqual(
            violations,
            [],
            f"Found Unicode arrow in log calls on lines: "
            f"{[ln for ln, _ in violations]}",
        )

    def test_brain_prefix_removed_from_log_messages(self):
        """[Brain] prefix must not appear in log.*() call messages."""
        lines = self.src.splitlines()
        violations = []
        for i, line in enumerate(lines):
            if re.search(r"\blog\.\w+\s*\(", line) and "[Brain]" in line:
                violations.append((i + 1, line.strip()))
        self.assertEqual(
            violations,
            [],
            f"Found [Brain] prefix in log calls on lines: "
            f"{[ln for ln, _ in violations]}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
