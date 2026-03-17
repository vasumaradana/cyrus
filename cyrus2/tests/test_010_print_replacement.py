"""
Acceptance-driven tests for Issue 010: Replace print() calls in cyrus_brain.py.

Tests verify every acceptance criterion from the issue:
  - All print() calls replaced with log.*() equivalents
  - from cyrus_log import setup_logging added at module top
  - import logging present
  - log = logging.getLogger("cyrus.brain") defined after imports
  - setup_logging("cyrus") called once in main()
  - [Brain] prefix patterns → log.info()
  - [!] prefix patterns → log.error()
  - Fallback/timeout/retry patterns → log.warning()
  - Routing/dispatch/scan patterns → log.debug()
  - Exception handlers with broad except → log.error(..., exc_info=True)
  - All f-strings converted to %s-style lazy formatting
  - File imports cleanly (functionality preserved)
  - No new print() calls introduced
  - No root logger calls (logging.info, logging.debug, etc.) remain

Strategy: Static analysis (AST + source text) for structural checks; runtime
tests mock Windows dependencies so the module imports cleanly on any platform.
"""

import ast
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

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

# Add cyrus2/ directory to sys.path so `import cyrus_brain` resolves correctly.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

# Paths for static analysis.
BRAIN_PY = _CYRUS2_DIR / "cyrus_brain.py"


# ── AC: All print() calls replaced ────────────────────────────────────────────


class TestNoPrintCallsRemain(unittest.TestCase):
    """AC: All print() calls replaced with log.*() equivalents."""

    def test_no_print_calls_remain(self):
        """No print() calls must remain in cyrus_brain.py (excludes comments)."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        lines_with_print = []
        for i, line in enumerate(source.splitlines(), 1):
            # Skip pure comment lines
            if line.lstrip().startswith("#"):
                continue
            if "print(" in line:
                lines_with_print.append((i, line.rstrip()))
        self.assertEqual(
            [],
            lines_with_print,
            f"Found {len(lines_with_print)} print() call(s): {lines_with_print[:5]}",
        )

    def test_no_new_print_calls_introduced(self):
        """Belt-and-suspenders: total print() count in non-comment lines is 0."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        count = sum(
            1
            for line in source.splitlines()
            if "print(" in line and not line.lstrip().startswith("#")
        )
        self.assertEqual(0, count, f"Expected 0 print() calls, found {count}")


# ── AC: from cyrus_log import setup_logging added ─────────────────────────────


class TestSetupLoggingImportExists(unittest.TestCase):
    """AC: from cyrus_log import setup_logging added at module top."""

    @classmethod
    def setUpClass(cls) -> None:
        source = BRAIN_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(source)

    def test_setup_logging_import_exists(self) -> None:
        """AST: cyrus_brain.py must import setup_logging from cyrus_log."""
        found = False
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
                # Accept both 'from cyrus_log import ...'
                # and 'from cyrus2.cyrus_log import ...'
                if "cyrus_log" in module and "setup_logging" in names:
                    found = True
                    break
        self.assertTrue(
            found,
            "Missing: from cyrus_log import setup_logging "
            "(or from cyrus2.cyrus_log import setup_logging)",
        )


# ── AC: import logging present ────────────────────────────────────────────────


class TestLoggingImportExists(unittest.TestCase):
    """AC: import logging present in cyrus_brain.py."""

    @classmethod
    def setUpClass(cls) -> None:
        source = BRAIN_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(source)

    def test_logging_import_exists(self) -> None:
        """AST: import logging must be present."""
        found = any(
            isinstance(node, ast.Import)
            and any(alias.name == "logging" for alias in node.names)
            for node in ast.walk(self.tree)
        )
        self.assertTrue(found, "Missing: import logging")


# ── AC: Named logger defined ──────────────────────────────────────────────────


class TestNamedLoggerDefined(unittest.TestCase):
    """AC: log = logging.getLogger("cyrus.brain") defined after imports."""

    def test_named_logger_defined(self) -> None:
        """Source must contain logging.getLogger("cyrus.brain")."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        self.assertIn(
            'logging.getLogger("cyrus.brain")',
            source,
            'Missing: log = logging.getLogger("cyrus.brain")',
        )

    def test_log_variable_assignment(self) -> None:
        """Source must assign the logger to the variable 'log'."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        self.assertIn(
            'log = logging.getLogger("cyrus.brain")',
            source,
            'Missing: log = logging.getLogger("cyrus.brain")',
        )


# ── AC: setup_logging called in main() ────────────────────────────────────────


class TestSetupLoggingCalledInMain(unittest.TestCase):
    """AC: setup_logging("cyrus") called once in main() before any logging."""

    @classmethod
    def setUpClass(cls) -> None:
        source = BRAIN_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(source)

    def _get_main_body(self) -> list:
        """Return the AST body statements of the main() function."""
        for node in ast.walk(self.tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "main"
            ):
                return node.body
        return []

    def test_setup_logging_called_in_main(self) -> None:
        """main() must call setup_logging('cyrus') as an early statement."""
        main_body = self._get_main_body()
        self.assertTrue(main_body, "main() function not found")
        found = False
        for stmt in main_body:
            # Look for: setup_logging("cyrus")
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                func = call.func
                if isinstance(func, ast.Name) and func.id == "setup_logging":
                    if call.args and isinstance(call.args[0], ast.Constant):
                        if call.args[0].value == "cyrus":
                            found = True
                            break
        self.assertTrue(found, 'main() must call setup_logging("cyrus")')


# ── AC: [Brain] prefix patterns → log.info() ──────────────────────────────────


class TestBrainPrefixRemoved(unittest.TestCase):
    """AC: [Brain] prefix stripped — log.info() used instead of print."""

    def test_no_brain_prefix_in_log_calls(self) -> None:
        """No log.* call should have '[Brain]' as part of its message string."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        violations = []
        for i, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            # Pattern: log.method( followed by "[Brain]" on the same line
            if re.search(r"log\.\w+\s*\(.*\[Brain\]", line):
                violations.append((i, line.rstrip()))
        self.assertEqual(
            [],
            violations,
            f"Found [Brain] prefix in log calls: {violations}",
        )


# ── AC: [!] prefix patterns → log.error() ─────────────────────────────────────


class TestErrorPrefixRemoved(unittest.TestCase):
    """AC: [!] prefix stripped — log.error() used instead of print."""

    def test_no_error_prefix_in_log_calls(self) -> None:
        """No log.* call should have '[!]' as part of its message string."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        violations = []
        for i, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if re.search(r"log\.\w+\s*\(.*\[!\]", line):
                violations.append((i, line.rstrip()))
        self.assertEqual(
            [],
            violations,
            f"Found [!] prefix in log calls: {violations}",
        )


# ── AC: Fallback/timeout/retry → log.warning() ────────────────────────────────


class TestFallbackPatternsUseWarning(unittest.TestCase):
    """AC: Fallback/timeout/retry patterns use log.warning()."""

    def test_timeout_uses_warning(self) -> None:
        """Submit timed out message must use log.warning()."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        warning_lines = [
            line.strip() for line in source.splitlines() if "log.warning(" in line
        ]
        warning_text = "\n".join(warning_lines)
        self.assertIn(
            "timed out",
            warning_text,
            "Submit timed out message must use log.warning()",
        )

    def test_fallback_to_uia_uses_warning(self) -> None:
        """Companion unavailable / falling back to UIA → warning."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        found_warning = False
        for line in source.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if ("falling back" in line.lower() or "unavailable" in line.lower()) and (
                "uia" in line.lower() or "extension" in line.lower()
            ):
                if "log.warning(" in line:
                    found_warning = True
                    break
        self.assertTrue(
            found_warning,
            "Fallback/unavailable-extension patterns must use log.warning()",
        )

    def test_cache_clear_retry_uses_warning(self) -> None:
        """Comtypes cache clear retry must use a warning-level log call."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        lines = source.splitlines()
        # The cache-clear message could span multiple lines (e.g. log.warning(\n "..."))
        # or use logging.getLogger("cyrus.brain").warning() before log is defined.
        # Check: find the "cache, retrying" message and ensure .warning( precedes it.
        for i, line in enumerate(lines):
            if "cache, retrying" in line.lower() and not line.lstrip().startswith("#"):
                # Check this line and the 2 lines before it for a .warning( call
                region = lines[max(0, i - 2) : i + 1]
                if any(".warning(" in ln for ln in region):
                    return  # found — test passes
                self.fail(
                    f"'cache, retrying' message must use .warning(), got: {region}"
                )
        self.fail("'cache, retrying' message not found in cyrus_brain.py")


# ── AC: Routing/dispatch/scan → log.debug() ───────────────────────────────────


class TestRoutingPatternsUseDebug(unittest.TestCase):
    """AC: Routing/dispatch/scan patterns use log.debug()."""

    def test_active_project_uses_debug(self) -> None:
        """Active project tracking (window scan) must use log.debug()."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        found = any(
            "log.debug(" in line and "Active project" in line
            for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertTrue(
            found,
            "Active project scan must use log.debug()",
        )

    def test_hook_dispatch_uses_debug(self) -> None:
        """Hook event dispatch must use log.debug()."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        found = any(
            "log.debug(" in line
            and ("Hook event" in line or "hook event" in line.lower())
            for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertTrue(
            found,
            "Hook event dispatch must use log.debug()",
        )

    def test_conversation_routing_uses_debug(self) -> None:
        """Conversation routing ('heard') must use log.debug()."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        found = any(
            "log.debug(" in line and ("Conversation heard" in line or "heard:" in line)
            for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertTrue(
            found,
            "Conversation heard routing must use log.debug()",
        )

    def test_brain_command_dispatch_uses_debug(self) -> None:
        """Brain command dispatch must use log.debug()."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        found = any(
            "log.debug(" in line and "Brain command" in line
            for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertTrue(
            found,
            "Brain command dispatch must use log.debug()",
        )

    def test_pre_tool_dispatch_uses_debug(self) -> None:
        """pre_tool received dispatch must use log.debug()."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        lines = source.splitlines()
        # The log.debug( and "pre_tool received" may be on adjacent lines (wrapped call)
        for i, line in enumerate(lines):
            if "pre_tool received" in line and not line.lstrip().startswith("#"):
                # Check this line and the 2 lines before it for log.debug(
                region = lines[max(0, i - 2) : i + 1]
                if any("log.debug(" in ln for ln in region):
                    return  # found — test passes
                self.fail(
                    f"'pre_tool received' message must use log.debug(), got: {region}"
                )
        self.fail("'pre_tool received' message not found in cyrus_brain.py")


# ── AC: Exception handlers use exc_info=True ──────────────────────────────────


class TestExceptBlocksUseExcInfo(unittest.TestCase):
    """AC: Exception handlers with broad except → log.error(..., exc_info=True)."""

    @classmethod
    def setUpClass(cls) -> None:
        source = BRAIN_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(source, filename=str(BRAIN_PY))

    def _get_log_error_calls_in_except_blocks(self) -> list[tuple[int, bool]]:
        """
        Walk the AST and collect (lineno, has_exc_info) for every log.error()
        call found directly inside an ExceptHandler body.
        """
        results: list[tuple[int, bool]] = []

        class _Visitor(ast.NodeVisitor):
            def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
                # Walk only the direct statements in this handler
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                        call = stmt.value
                        if (
                            isinstance(call.func, ast.Attribute)
                            and isinstance(call.func.value, ast.Name)
                            and call.func.value.id == "log"
                            and call.func.attr == "error"
                        ):
                            has_exc_info = any(
                                isinstance(kw, ast.keyword)
                                and kw.arg == "exc_info"
                                and isinstance(kw.value, ast.Constant)
                                and kw.value.value is True
                                for kw in call.keywords
                            )
                            results.append((stmt.lineno, has_exc_info))
                self.generic_visit(node)

        _Visitor().visit(self.tree)
        return results

    def test_broad_except_blocks_have_log_error_with_exc_info(self) -> None:
        """
        All log.error() calls inside except handlers must include exc_info=True.
        Expects at least 4 such calls.
        """
        calls = self._get_log_error_calls_in_except_blocks()
        self.assertGreaterEqual(
            len(calls),
            4,
            f"Expected ≥4 log.error() in except blocks, found {len(calls)}: {calls}",
        )
        missing = [(ln, has_ei) for ln, has_ei in calls if not has_ei]
        self.assertEqual(
            [],
            missing,
            f"log.error() calls in except blocks missing exc_info=True at lines: "
            f"{[ln for ln, _ in missing]}",
        )


# ── AC: F-strings converted to %s style ───────────────────────────────────────


class TestNoFStringsInLogCalls(unittest.TestCase):
    """AC: All f-strings converted to %s-style lazy formatting in log calls."""

    @classmethod
    def setUpClass(cls) -> None:
        source = BRAIN_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(source, filename=str(BRAIN_PY))

    def test_no_fstrings_in_log_calls(self) -> None:
        """
        No log.*(f"...") call should use a JoinedStr (f-string) as its
        first positional argument.
        """
        violations = []
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "log"
            ):
                # Check first positional arg for f-string
                if node.args and isinstance(node.args[0], ast.JoinedStr):
                    violations.append(node.lineno)
        self.assertEqual(
            [],
            violations,
            f"log.* calls with f-string (JoinedStr) first args at lines: {violations}",
        )


# ── AC: No root logger calls remain ───────────────────────────────────────────


class TestNoRootLoggerCalls(unittest.TestCase):
    """AC: No root logger calls (logging.info, logging.debug, etc.) remain."""

    _ROOT_LOGGER_PATTERN = re.compile(
        r"\blogging\.(debug|info|warning|error|exception|critical)\s*\("
    )

    def test_no_root_logger_calls(self) -> None:
        """Source must use the named logger (log.*), not the root logger (logging.*)."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        violations = []
        for i, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if self._ROOT_LOGGER_PATTERN.search(line):
                violations.append((i, line.rstrip()))
        self.assertEqual(
            [],
            violations,
            f"Found root logger calls (must use 'log.*' instead): {violations[:5]}",
        )


# ── AC: File imports cleanly (functionality preserved) ────────────────────────


class TestModuleImportsCleanly(unittest.TestCase):
    """AC: File still has same functionality; only logging mechanism changed."""

    def test_module_imports_cleanly(self) -> None:
        """cyrus_brain.py must import without errors (Windows deps mocked)."""
        try:
            import cyrus_brain  # noqa: F401
        except Exception as e:
            self.fail(f"cyrus_brain.py failed to import: {e}")

    def test_module_has_main_function(self) -> None:
        """main() async function must still be present after the refactor."""
        import cyrus_brain  # noqa: F401

        self.assertTrue(
            hasattr(cyrus_brain, "main"),
            "cyrus_brain must have a main() function",
        )

    def test_module_has_log_attribute(self) -> None:
        """cyrus_brain must expose a module-level 'log' logger."""
        import cyrus_brain  # noqa: F401

        self.assertTrue(
            hasattr(cyrus_brain, "log"),
            "cyrus_brain must have a module-level 'log' logger attribute",
        )

    def test_log_is_named_logger(self) -> None:
        """cyrus_brain.log must be the 'cyrus.brain' named logger."""
        import logging

        import cyrus_brain  # noqa: F401

        self.assertIsInstance(cyrus_brain.log, logging.Logger)
        self.assertEqual(
            cyrus_brain.log.name,
            "cyrus.brain",
            f"Expected logger name 'cyrus.brain', got '{cyrus_brain.log.name}'",
        )


# ── Edge cases ─────────────────────────────────────────────────────────────────


class TestEdgeCases(unittest.TestCase):
    """Edge and corner cases for the print → log conversion."""

    def test_leading_newlines_stripped_from_messages(self) -> None:
        """
        Messages that started with '\\n' in print() calls must not have
        leading '\\n' in log calls — logging handles its own line breaks.
        """
        source = BRAIN_PY.read_text(encoding="utf-8")
        violations = []
        for i, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            # Check for log.*("\\n... or log.*('\\n...
            if re.search(r'log\.\w+\s*\(\s*["\']\\n', line):
                violations.append((i, line.rstrip()))
        self.assertEqual(
            [],
            violations,
            f"log.* calls with leading \\n in message string at lines: {violations}",
        )

    def test_dynamic_log_message_uses_percent_style(self) -> None:
        """
        result.log_message forwarded to log.info must use %s placeholder,
        not direct string embedding.
        """
        source = BRAIN_PY.read_text(encoding="utf-8")
        # Look for the log call that forwards result.log_message
        found = any(
            "log.info(" in line and "log_message" in line
            for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertTrue(
            found,
            "result.log_message must be forwarded via "
            "log.info('%s', result.log_message)",
        )

    def test_no_end_or_flush_args_in_log_calls(self) -> None:
        """
        print() end= and flush= kwargs must not appear in log.* calls
        (logging does not support them; they must be dropped).
        """
        source = BRAIN_PY.read_text(encoding="utf-8")
        violations = []
        for i, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if "log." in line and ("end=" in line or "flush=" in line):
                violations.append((i, line.rstrip()))
        self.assertEqual(
            [],
            violations,
            f"log.* calls with end= or flush= at lines: {violations}",
        )

    def test_fatal_uiautomation_error_uses_log_error(self) -> None:
        """The FATAL UIAutomation error must be logged at error level, not printed."""
        source = BRAIN_PY.read_text(encoding="utf-8")
        lines = source.splitlines()
        # Find the FATAL message and check it uses an error-level call
        fatal_region: list[str] = []
        for i, line in enumerate(lines):
            if "FATAL" in line and not line.lstrip().startswith("#"):
                # Grab context: 2 lines before through 3 lines after
                start = max(0, i - 2)
                fatal_region = lines[start : i + 4]
                break
        self.assertTrue(
            fatal_region,
            "FATAL UIAutomation error not found in source",
        )
        # Must NOT be in print()
        fatal_in_print = any("print(" in ln for ln in fatal_region)
        self.assertFalse(
            fatal_in_print,
            "FATAL UIAutomation error must not use print()",
        )
        # Must use an error-level log call (log.error or .error( via getLogger chain)
        has_error_call = any(".error(" in ln for ln in fatal_region)
        self.assertTrue(
            has_error_call,
            f"FATAL message must be in an .error() call, got: {fatal_region}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
