"""
Acceptance-driven tests for Issue 015:
Add focus verification before keystroke sequences.

Tests verify every acceptance criterion from the issue:
  - _assert_vscode_focus() created in cyrus_common.py
  - Uses UIAutomation GetFocusedControl() to get the focused window
  - Verifies focused window title contains "Visual Studio Code"
  - Raises RuntimeError if focus is not VS Code
  - Called before every pyautogui keystroke sequence
  - Logs which window had focus if assertion fails
  - All clipboard manipulation operations preceded by focus check
  - No misdirected input can occur due to focus change
  - Existing functionality preserved (only adds safety gate)
  - Handles UIA exceptions gracefully

Strategy: Static analysis (AST) for structural checks; runtime tests mock Windows
dependencies so the module imports cleanly on any platform.
"""

import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Mock Windows-specific modules BEFORE any cyrus import ────────────────────
# cyrus_common.py and cyrus_brain.py import Windows-only packages at module
# level.  Mock them in sys.modules first so the import succeeds on any platform.
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

# Add cyrus2/ directory to sys.path so imports resolve correctly on any platform.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

import cyrus_brain  # noqa: E402
import cyrus_common  # noqa: E402

# Paths to source files for static analysis.
BRAIN_PY = _CYRUS2_DIR / "cyrus_brain.py"
COMMON_PY = _CYRUS2_DIR / "cyrus_common.py"


# ── AST helpers ───────────────────────────────────────────────────────────────


def _parse(path: Path) -> ast.Module:
    """Return the parsed AST for the given source file."""
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    """Return the first function (any depth) with *name*, or None."""
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node  # type: ignore[return-value]
    return None


def _call_name(call_node: ast.Call) -> str:
    """Return a dotted name string for a Call's func, e.g. 'pyautogui.press'."""
    func = call_node.func
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            return f"{func.value.id}.{func.attr}"
        return f"<expr>.{func.attr}"
    if isinstance(func, ast.Name):
        return func.id
    return "<unknown>"


def _find_guard_before_pyautogui(func_body: list[ast.stmt]) -> bool:
    """Return True if _assert_vscode_focus() is called before the first pyautogui call.

    Recursively inspects try/except and if/else branches since pyautogui calls
    may be wrapped in these constructs in the source.
    """

    def _stmt_calls(stmt: ast.stmt) -> list[str]:
        """Collect direct call-name strings from a statement (one level deep)."""
        results: list[str] = []
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            results.append(_call_name(stmt.value))
        elif isinstance(stmt, ast.Try):
            for s in stmt.body:
                results.extend(_stmt_calls(s))
            for handler in stmt.handlers:
                for s in handler.body:
                    results.extend(_stmt_calls(s))
        elif isinstance(stmt, ast.If):
            for s in stmt.body:
                results.extend(_stmt_calls(s))
            for s in stmt.orelse:
                results.extend(_stmt_calls(s))
        return results

    seen_guard = False
    for stmt in func_body:
        names = _stmt_calls(stmt)
        for name in names:
            if name == "_assert_vscode_focus":
                seen_guard = True
            elif name.startswith("pyautogui."):
                if not seen_guard:
                    return False
    return True


# ── AC: Function exists and is callable ──────────────────────────────────────


class TestFunctionExists(unittest.TestCase):
    """AC: Function _assert_vscode_focus() created in cyrus_common.py."""

    def test_function_exists_and_callable(self):
        """_assert_vscode_focus must exist in cyrus_common and be callable."""
        self.assertTrue(
            hasattr(cyrus_common, "_assert_vscode_focus"),
            "_assert_vscode_focus not found in cyrus_common",
        )
        self.assertTrue(
            callable(cyrus_common._assert_vscode_focus),
            "_assert_vscode_focus must be callable",
        )

    def test_function_is_module_level(self):
        """_assert_vscode_focus must be defined at module level in cyrus_common.py."""
        tree = _parse(COMMON_PY)
        top_level_funcs = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn(
            "_assert_vscode_focus",
            top_level_funcs,
            "_assert_vscode_focus must be a module-level function in cyrus_common.py",
        )


# ── AC: Uses UIAutomation to get focused window ───────────────────────────────


class TestUsesUIAutomation(unittest.TestCase):
    """AC: Uses UIAutomation to get currently focused window."""

    def test_calls_get_focused_control(self):
        """_assert_vscode_focus must call auto.GetFocusedControl()."""
        mock_auto = MagicMock()
        focused_ctrl = MagicMock()
        # Focused control Name contains VS Code — should pass without raising
        focused_ctrl.Name = "Visual Studio Code — main.py"
        focused_ctrl.GetParentControl.return_value = None
        mock_auto.GetFocusedControl.return_value = focused_ctrl

        with patch.object(cyrus_common, "auto", mock_auto, create=True):
            cyrus_common._assert_vscode_focus()  # should not raise

        mock_auto.GetFocusedControl.assert_called_once()

    def test_ast_references_get_focused_control(self):
        """Source of _assert_vscode_focus must reference GetFocusedControl."""
        tree = _parse(COMMON_PY)
        func = _find_function(tree, "_assert_vscode_focus")
        self.assertIsNotNone(func, "_assert_vscode_focus not found in AST")

        # Collect all attribute-access strings within the function
        attrs: set[str] = set()
        for node in ast.walk(func):
            if isinstance(node, ast.Attribute):
                attrs.add(node.attr)

        self.assertIn(
            "GetFocusedControl",
            attrs,
            "_assert_vscode_focus must call auto.GetFocusedControl()",
        )


# ── AC: Verifies focus contains "Visual Studio Code" ─────────────────────────


class TestPassesWhenVSCodeFocused(unittest.TestCase):
    """AC: Passes silently when VS Code has focus."""

    def _make_auto_mock(self, window_name: str) -> MagicMock:
        """Build a mock auto module whose GetFocusedControl returns a named control."""
        mock_auto = MagicMock()
        ctrl = MagicMock()
        ctrl.Name = window_name
        ctrl.GetParentControl.return_value = None
        mock_auto.GetFocusedControl.return_value = ctrl
        return mock_auto

    def test_passes_when_vscode_focused(self):
        """No exception when the focused window title contains 'Visual Studio Code'."""
        mock_auto = self._make_auto_mock("Visual Studio Code — main.py")
        with patch.object(cyrus_common, "auto", mock_auto, create=True):
            # Must not raise
            cyrus_common._assert_vscode_focus()

    def test_passes_for_various_vscode_titles(self):
        """Accepts any title containing 'Visual Studio Code' substring."""
        titles = [
            "Visual Studio Code",
            "main.py — Visual Studio Code",
            "● untitled — Visual Studio Code",
        ]
        for title in titles:
            with self.subTest(title=title):
                mock_auto = self._make_auto_mock(title)
                with patch.object(cyrus_common, "auto", mock_auto, create=True):
                    cyrus_common._assert_vscode_focus()  # must not raise


# ── AC: Raises RuntimeError if focus is not VS Code ──────────────────────────


class TestRaisesWhenWrongWindowFocused(unittest.TestCase):
    """AC: RuntimeError raised when focused window is not VS Code."""

    def _make_auto_mock(self, window_name: str) -> MagicMock:
        mock_auto = MagicMock()
        ctrl = MagicMock()
        ctrl.Name = window_name
        ctrl.GetParentControl.return_value = None
        mock_auto.GetFocusedControl.return_value = ctrl
        return mock_auto

    def test_raises_when_wrong_window_focused(self):
        """RuntimeError raised when a non-VS-Code window has focus."""
        mock_auto = self._make_auto_mock("Chrome — Google")
        with patch.object(cyrus_common, "auto", mock_auto, create=True):
            with self.assertRaises(RuntimeError) as ctx:
                cyrus_common._assert_vscode_focus()
        self.assertIn(
            "Chrome",
            str(ctx.exception),
            "RuntimeError message must include the wrong window name",
        )

    def test_raises_with_wrong_window_name_in_message(self):
        """RuntimeError message must include the name of the wrong window."""
        wrong_name = "Windows Terminal"
        mock_auto = self._make_auto_mock(wrong_name)
        with patch.object(cyrus_common, "auto", mock_auto, create=True):
            with self.assertRaises(RuntimeError) as ctx:
                cyrus_common._assert_vscode_focus()
        self.assertIn(wrong_name, str(ctx.exception))

    def test_raises_for_completely_unrelated_app(self):
        """RuntimeError raised for windows not containing 'Visual Studio Code'."""
        mock_auto = self._make_auto_mock("Notepad")
        with patch.object(cyrus_common, "auto", mock_auto, create=True):
            with self.assertRaises(RuntimeError):
                cyrus_common._assert_vscode_focus()


# ── AC: Logs which window had focus on failure ────────────────────────────────


class TestLogsFocusMismatchOnFailure(unittest.TestCase):
    """AC: Logs which window had focus if assertion fails."""

    def _make_auto_mock(self, window_name: str) -> MagicMock:
        mock_auto = MagicMock()
        ctrl = MagicMock()
        ctrl.Name = window_name
        ctrl.GetParentControl.return_value = None
        mock_auto.GetFocusedControl.return_value = ctrl
        return mock_auto

    def test_logs_focus_mismatch_on_failure(self):
        """log.error() must be called with the wrong window name before raising."""
        wrong_name = "Firefox"
        mock_auto = self._make_auto_mock(wrong_name)
        with patch.object(cyrus_common, "auto", mock_auto, create=True):
            with self.assertLogs("cyrus.common", level="ERROR") as log_ctx:
                with self.assertRaises(RuntimeError):
                    cyrus_common._assert_vscode_focus()
        # At least one logged message must mention the wrong window
        logged_messages = " ".join(log_ctx.output)
        self.assertIn(
            wrong_name,
            logged_messages,
            "log.error must include the wrong window name",
        )

    def test_no_log_on_success(self):
        """No error logging when VS Code has focus."""
        mock_auto = self._make_auto_mock("Visual Studio Code — project")
        with patch.object(cyrus_common, "auto", mock_auto, create=True):
            with self.assertNoLogs("cyrus.common", level="ERROR"):
                cyrus_common._assert_vscode_focus()


# ── AC: Handles UIA exceptions gracefully ────────────────────────────────────


class TestUiaExceptionHandling(unittest.TestCase):
    """AC: UIA exceptions are logged and re-raised as RuntimeError."""

    def test_uia_exception_reraises_as_runtime_error(self):
        """If GetFocusedControl raises, RuntimeError is propagated."""
        mock_auto = MagicMock()
        mock_auto.GetFocusedControl.side_effect = OSError("UIA COM error")
        with patch.object(cyrus_common, "auto", mock_auto, create=True):
            with self.assertRaises(RuntimeError):
                cyrus_common._assert_vscode_focus()

    def test_uia_exception_logs_warning(self):
        """If GetFocusedControl raises, a warning must be logged."""
        mock_auto = MagicMock()
        mock_auto.GetFocusedControl.side_effect = RuntimeError("COM failure")
        with patch.object(cyrus_common, "auto", mock_auto, create=True):
            with self.assertLogs("cyrus.common", level="WARNING"):
                with self.assertRaises(RuntimeError):
                    cyrus_common._assert_vscode_focus()


# ── AC: Called before every pyautogui keystroke sequence (structural / AST) ──


class TestAssertPrecedesPyautoguiInBrain(unittest.TestCase):
    """AC: _assert_vscode_focus precedes pyautogui calls in cyrus_brain.py."""

    @classmethod
    def setUpClass(cls):
        cls.tree = _parse(BRAIN_PY)
        cls.func = _find_function(cls.tree, "_submit_to_vscode_impl")

    def test_assert_vscode_focus_called_in_submit_impl(self):
        """_assert_vscode_focus must be called in _submit_to_vscode_impl."""
        self.assertIsNotNone(
            self.func,
            "_submit_to_vscode_impl not found in cyrus_brain.py",
        )
        call_names: set[str] = set()
        for node in ast.walk(self.func):
            if isinstance(node, ast.Call):
                call_names.add(_call_name(node))
        self.assertIn(
            "_assert_vscode_focus",
            call_names,
            "_assert_vscode_focus must be called in _submit_to_vscode_impl",
        )

    def test_assert_precedes_pyautogui_in_brain(self):
        """_assert_vscode_focus must precede every pyautogui call in submit impl."""
        self.assertIsNotNone(
            self.func,
            "_submit_to_vscode_impl not found in cyrus_brain.py",
        )
        result = _find_guard_before_pyautogui(self.func.body)
        self.assertTrue(
            result,
            "_assert_vscode_focus must be called before the first pyautogui call in "
            "_submit_to_vscode_impl",
        )


class TestAssertPrecedesPyautoguiInCommon(unittest.TestCase):
    """AC: _assert_vscode_focus precedes pyautogui calls in cyrus_common.py."""

    @classmethod
    def setUpClass(cls):
        cls.tree = _parse(COMMON_PY)
        cls.handle_response = _find_function(cls.tree, "handle_response")
        cls.handle_prompt = _find_function(cls.tree, "handle_prompt_response")

    def test_assert_called_in_handle_response(self):
        """_assert_vscode_focus must be called in PermissionWatcher.handle_response."""
        self.assertIsNotNone(self.handle_response, "handle_response not found")
        call_names: set[str] = set()
        for node in ast.walk(self.handle_response):
            if isinstance(node, ast.Call):
                call_names.add(_call_name(node))
        self.assertIn(
            "_assert_vscode_focus",
            call_names,
            "_assert_vscode_focus must be called in handle_response",
        )

    def test_assert_called_in_handle_prompt_response(self):
        """_assert_vscode_focus must be called in handle_prompt_response."""
        self.assertIsNotNone(self.handle_prompt, "handle_prompt_response not found")
        call_names: set[str] = set()
        for node in ast.walk(self.handle_prompt):
            if isinstance(node, ast.Call):
                call_names.add(_call_name(node))
        self.assertIn(
            "_assert_vscode_focus",
            call_names,
            "_assert_vscode_focus must be called in handle_prompt_response",
        )

    def test_assert_precedes_pyautogui_in_common(self):
        """_assert_vscode_focus must precede pyautogui sequences in handle_response."""
        self.assertIsNotNone(self.handle_response, "handle_response not found")
        result = _find_guard_before_pyautogui(self.handle_response.body)
        self.assertTrue(
            result,
            "_assert_vscode_focus must be called before the first pyautogui call in "
            "handle_response",
        )

    def test_clipboard_ops_preceded_by_focus_check(self):
        """_assert_vscode_focus must precede ctrl+a hotkey in handle_prompt_response."""
        self.assertIsNotNone(self.handle_prompt, "handle_prompt_response not found")
        result = _find_guard_before_pyautogui(self.handle_prompt.body)
        self.assertTrue(
            result,
            "_assert_vscode_focus must precede clipboard hotkey operations in "
            "handle_prompt_response",
        )


# ── AC: No misdirected input — operation aborts on focus failure ──────────────


class TestSubmitAbortsOnFocusFailure(unittest.TestCase):
    """AC: _submit_to_vscode_impl returns False if focus check fails."""

    def test_submit_aborts_on_focus_failure(self):
        """If _assert_vscode_focus raises RuntimeError, submit returns False."""
        with patch.object(
            cyrus_brain,
            "_assert_vscode_focus",
            side_effect=RuntimeError("wrong focus"),
        ):
            result = cyrus_brain._submit_to_vscode_impl("hello")
        self.assertFalse(result, "Submit must return False when focus check fails")

    def test_submit_does_not_call_pyautogui_on_focus_failure(self):
        """pyautogui must NOT be called if _assert_vscode_focus raises."""
        mock_pyautogui = MagicMock()
        with (
            patch.object(
                cyrus_brain,
                "_assert_vscode_focus",
                side_effect=RuntimeError("wrong focus"),
            ),
            patch.object(cyrus_brain, "pyautogui", mock_pyautogui),
        ):
            cyrus_brain._submit_to_vscode_impl("hello")
        mock_pyautogui.click.assert_not_called()
        mock_pyautogui.hotkey.assert_not_called()
        mock_pyautogui.press.assert_not_called()


class TestPermissionAbortsOnFocusFailure(unittest.TestCase):
    """AC: handle_response does not send keystrokes when focus check fails."""

    def _make_watcher(self) -> cyrus_common.PermissionWatcher:
        """Create a minimal PermissionWatcher stub for testing."""
        watcher = cyrus_common.PermissionWatcher.__new__(cyrus_common.PermissionWatcher)
        watcher._pending = True
        watcher._allow_btn = "keyboard"
        watcher._pending_since = 0.0
        watcher._announced = ""
        watcher._target_sub = "Visual Studio Code"
        watcher._chat_doc = MagicMock()
        watcher._prompt_pending = False
        watcher._prompt_input_ctrl = None
        watcher.project_name = "test"
        return watcher

    def test_permission_aborts_on_focus_failure(self):
        """handle_response must not press keys if focus check fails."""
        watcher = self._make_watcher()
        mock_pyautogui = MagicMock()
        with (
            patch.object(
                cyrus_common,
                "_assert_vscode_focus",
                side_effect=RuntimeError("no focus"),
            ),
            patch.object(cyrus_common, "pyautogui", mock_pyautogui),
            patch.object(cyrus_common, "auto", MagicMock()),
        ):
            watcher.handle_response("yes")
        mock_pyautogui.press.assert_not_called()
        mock_pyautogui.hotkey.assert_not_called()


# ── AC: Existing functionality preserved ─────────────────────────────────────


class TestSubmitSucceedsWhenFocused(unittest.TestCase):
    """AC: Normal submit path still works when VS Code has focus."""

    def test_submit_succeeds_when_focused(self):
        """_submit_to_vscode_impl returns True when focus passes and coords exist."""
        mock_win = MagicMock()
        mock_win.title = "Visual Studio Code"

        mock_pyautogui = MagicMock()
        mock_pyperclip = MagicMock()
        mock_pyperclip.paste.return_value = ""
        mock_gw = MagicMock()
        mock_gw.getAllWindows.return_value = [mock_win]

        # Provide coords so the function does not need to search via UIA
        saved_proj = cyrus_brain._active_project
        cyrus_brain._active_project = "_test_015"
        cyrus_brain._chat_input_coords["_test_015"] = (100, 200)
        cyrus_brain._vscode_win_cache.pop("_test_015", None)  # clear any stale entry
        try:
            with (
                patch.object(cyrus_brain, "_assert_vscode_focus"),
                patch.object(cyrus_brain, "_submit_via_extension", return_value=False),
                patch.object(cyrus_brain, "pyautogui", mock_pyautogui),
                patch.object(cyrus_brain, "pyperclip", mock_pyperclip),
                patch.object(cyrus_brain, "gw", mock_gw),
            ):
                result = cyrus_brain._submit_to_vscode_impl("test input")
        finally:
            cyrus_brain._active_project = saved_proj
            cyrus_brain._chat_input_coords.pop("_test_015", None)
            cyrus_brain._vscode_win_cache.pop("_test_015", None)

        # Verify focus guard does not block the submit when it passes silently
        self.assertTrue(result, "Submit must return True when focus check passes")


if __name__ == "__main__":
    unittest.main()
