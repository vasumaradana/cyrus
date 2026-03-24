"""
Acceptance-driven tests for Issue 007:
Break up execute_cyrus_command into dispatch table.

Tests verify every acceptance criterion from the issue:
  - _execute_cyrus_command() refactored into dispatch dict _COMMAND_HANDLERS
  - Each handler is < 50 lines and handles a single command type
  - All original behavior preserved (no logic changes)
  - Unit tests added for each handler
  - Error handling improved: specific exceptions logged instead of silently swallowed

Strategy: Static analysis (AST) for structural checks; runtime tests mock Windows
dependencies so the module imports cleanly on any platform.
"""

import ast
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Mock Windows-specific modules BEFORE any cyrus_brain import ──────────────
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

import cyrus_brain  # noqa: E402
from cyrus_brain import (  # noqa: E402
    _COMMAND_HANDLERS,
    CommandResult,
    _execute_cyrus_command,
    _handle_last_message,
    _handle_pause,
    _handle_rename_session,
    _handle_switch_project,
    _handle_unlock,
    _handle_which_project,
)

# Path to the brain source for static analysis.
BRAIN_PY = _CYRUS2_DIR / "cyrus_brain.py"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_session_mgr(aliases=None, last_resp=None):
    """Return a lightweight SessionManager stub for handler tests."""
    mgr = MagicMock()
    mgr.aliases = aliases or {}
    mgr.last_response.return_value = last_resp
    return mgr


def _make_loop():
    """Return a mock event loop."""
    return MagicMock(spec=asyncio.AbstractEventLoop)


def _close_coro_side_effect(coro, loop):
    """Side-effect for patched run_coroutine_threadsafe.

    Closes any coroutine passed to the mock so the garbage collector does not
    emit a ``RuntimeWarning: coroutine '…' was never awaited`` when it
    destroys the orphaned coroutine object.
    """
    if asyncio.iscoroutine(coro):
        coro.close()


# ── AC: _COMMAND_HANDLERS dict structure ─────────────────────────────────────


class TestCommandHandlersDict(unittest.TestCase):
    """AC: _execute_cyrus_command() refactored into dispatch dict _COMMAND_HANDLERS."""

    def test_command_handlers_is_dict(self):
        """_COMMAND_HANDLERS must be a dict."""
        self.assertIsInstance(
            _COMMAND_HANDLERS,
            dict,
            "_COMMAND_HANDLERS must be a plain dict",
        )

    def test_command_handlers_has_6_entries(self):
        """AC: dispatch table must contain all 6 command types."""
        self.assertEqual(
            len(_COMMAND_HANDLERS),
            6,
            f"Expected 6 entries in _COMMAND_HANDLERS, got {len(_COMMAND_HANDLERS)}",
        )

    def test_command_handlers_keys_match_expected_types(self):
        """AC: dispatch table keys must match all 6 command type strings."""
        expected = {
            "switch",
            "unlock",
            "which_project",
            "last_message",
            "rename",
            "pause",
        }
        actual = set(_COMMAND_HANDLERS.keys())
        self.assertEqual(
            actual,
            expected,
            f"Key mismatch — missing: {expected - actual}, extra: {actual - expected}",
        )

    def test_command_handlers_values_are_callable(self):
        """All handler values in _COMMAND_HANDLERS must be callable functions."""
        for name, handler in _COMMAND_HANDLERS.items():
            self.assertTrue(
                callable(handler),
                f"_COMMAND_HANDLERS['{name}'] is not callable",
            )


# ── AC: Each handler < 50 lines (AST-based line count) ───────────────────────


class TestHandlerLineCounts(unittest.TestCase):
    """AC: Each handler is < 50 lines and handles a single command type."""

    @classmethod
    def setUpClass(cls):
        source = BRAIN_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(source)
        cls.handler_names = [
            "_handle_switch_project",
            "_handle_unlock",
            "_handle_which_project",
            "_handle_last_message",
            "_handle_rename_session",
            "_handle_pause",
        ]

    def _get_function_line_count(self, func_name: str) -> int:
        """Return the number of lines in a top-level function (end - start + 1)."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                return node.end_lineno - node.lineno + 1
        raise AssertionError(f"Function '{func_name}' not found in cyrus_brain.py")

    def test_all_handler_functions_exist_in_source(self):
        """All 6 handler functions must be defined in cyrus_brain.py."""
        defined = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef)
        }
        for name in self.handler_names:
            self.assertIn(
                name, defined, f"Handler '{name}' not found in cyrus_brain.py"
            )

    def test_each_handler_under_50_lines(self):
        """AC: Each handler must be < 50 lines."""
        for name in self.handler_names:
            count = self._get_function_line_count(name)
            self.assertLess(
                count,
                50,
                f"Handler '{name}' has {count} lines — must be < 50",
            )


# ── AC: CommandResult dataclass ───────────────────────────────────────────────


class TestCommandResultDataclass(unittest.TestCase):
    """CommandResult must be a dataclass with the expected fields and defaults."""

    def test_command_result_default_fields(self):
        """CommandResult() with no args must have safe defaults."""
        result = CommandResult()
        self.assertIsNone(result.spoken)
        self.assertEqual(result.speak_project, "")
        self.assertIsNone(result.new_active_project)
        self.assertIsNone(result.new_project_locked)
        self.assertFalse(result.skip_tts)
        self.assertEqual(result.log_message, "")

    def test_command_result_fields_settable(self):
        """CommandResult fields can be set at construction."""
        result = CommandResult(
            spoken="hello",
            speak_project="proj",
            new_active_project="proj",
            new_project_locked=True,
            skip_tts=True,
            log_message="[Brain] hello",
        )
        self.assertEqual(result.spoken, "hello")
        self.assertEqual(result.speak_project, "proj")
        self.assertEqual(result.new_active_project, "proj")
        self.assertTrue(result.new_project_locked)
        self.assertTrue(result.skip_tts)
        self.assertEqual(result.log_message, "[Brain] hello")


# ── AC: _handle_switch_project behavior ───────────────────────────────────────


class TestHandleSwitchProject(unittest.TestCase):
    """AC: switch_project handler preserves original behavior."""

    def test_switch_project_found_locks_to_target(self):
        """switch_project found: sets new_active_project + new_project_locked=True."""
        session_mgr = _make_session_mgr(aliases={"web": "web-proj"})

        with patch("cyrus_brain._resolve_project", return_value="web-proj"):
            result = _handle_switch_project(
                cmd={"project": "web"},
                spoken="",
                session_mgr=session_mgr,
                loop=_make_loop(),
                active_project="",
            )

        self.assertEqual(result.new_active_project, "web-proj")
        self.assertTrue(result.new_project_locked)
        self.assertIsNotNone(result.spoken)
        self.assertIn("web-proj", result.spoken)
        session_mgr.on_session_switch.assert_called_once_with("web-proj")

    def test_switch_project_found_uses_custom_spoken(self):
        """switch_project found: respects caller-provided spoken text."""
        session_mgr = _make_session_mgr()

        with patch("cyrus_brain._resolve_project", return_value="api-proj"):
            result = _handle_switch_project(
                cmd={"project": "api"},
                spoken="Switching to api.",
                session_mgr=session_mgr,
                loop=_make_loop(),
                active_project="",
            )

        self.assertEqual(result.spoken, "Switching to api.")

    def test_switch_project_not_found_returns_error_spoken(self):
        """switch_project not found: returns error message, no state changes."""
        session_mgr = _make_session_mgr()

        with patch("cyrus_brain._resolve_project", return_value=None):
            result = _handle_switch_project(
                cmd={"project": "unknown"},
                spoken="",
                session_mgr=session_mgr,
                loop=_make_loop(),
                active_project="",
            )

        self.assertIsNone(result.new_active_project)
        self.assertIsNone(result.new_project_locked)
        self.assertIn("unknown", result.spoken)
        session_mgr.on_session_switch.assert_not_called()

    def test_switch_project_not_found_does_not_lock(self):
        """switch_project not found: new_project_locked must be None (no change)."""
        with patch("cyrus_brain._resolve_project", return_value=None):
            result = _handle_switch_project(
                cmd={"project": "missing"},
                spoken="",
                session_mgr=_make_session_mgr(),
                loop=_make_loop(),
                active_project="current",
            )

        self.assertIsNone(result.new_project_locked)


# ── AC: _handle_unlock behavior ───────────────────────────────────────────────


class TestHandleUnlock(unittest.TestCase):
    """AC: unlock handler preserves original behavior."""

    def test_unlock_sets_project_locked_false(self):
        """unlock: result.new_project_locked must be False."""
        result = _handle_unlock(
            cmd={},
            spoken="",
            session_mgr=_make_session_mgr(),
            loop=_make_loop(),
            active_project="proj",
        )
        self.assertFalse(result.new_project_locked)

    def test_unlock_default_spoken_text(self):
        """unlock: default spoken text must indicate follow mode."""
        result = _handle_unlock(
            cmd={},
            spoken="",
            session_mgr=_make_session_mgr(),
            loop=_make_loop(),
            active_project="",
        )
        self.assertIsNotNone(result.spoken)
        self.assertIn("focus", result.spoken.lower())

    def test_unlock_custom_spoken_text(self):
        """unlock: respects caller-provided spoken text."""
        result = _handle_unlock(
            cmd={},
            spoken="Unlocking now.",
            session_mgr=_make_session_mgr(),
            loop=_make_loop(),
            active_project="",
        )
        self.assertEqual(result.spoken, "Unlocking now.")

    def test_unlock_does_not_change_active_project(self):
        """unlock: must not modify new_active_project."""
        result = _handle_unlock(
            cmd={},
            spoken="",
            session_mgr=_make_session_mgr(),
            loop=_make_loop(),
            active_project="current-proj",
        )
        self.assertIsNone(result.new_active_project)


# ── AC: _handle_which_project behavior ───────────────────────────────────────


class TestHandleWhichProject(unittest.TestCase):
    """AC: which_project handler preserves original behavior."""

    def test_which_project_locked_status(self):
        """which_project locked: spoken text must include 'locked'."""
        cyrus_brain._project_locked = True
        result = _handle_which_project(
            cmd={},
            spoken="",
            session_mgr=_make_session_mgr(),
            loop=_make_loop(),
            active_project="my-proj",
        )
        self.assertIn("locked", result.spoken)
        self.assertIn("my-proj", result.spoken)

    def test_which_project_unlocked_status(self):
        """which_project unlocked: spoken text must include 'following focus'."""
        cyrus_brain._project_locked = False
        result = _handle_which_project(
            cmd={},
            spoken="",
            session_mgr=_make_session_mgr(),
            loop=_make_loop(),
            active_project="my-proj",
        )
        self.assertIn("focus", result.spoken.lower())

    def test_which_project_no_active_project(self):
        """which_project with no active project: spoken text uses 'none'."""
        cyrus_brain._project_locked = False
        result = _handle_which_project(
            cmd={},
            spoken="",
            session_mgr=_make_session_mgr(),
            loop=_make_loop(),
            active_project="",
        )
        self.assertIn("none", result.spoken.lower())

    def test_which_project_custom_spoken(self):
        """which_project: respects caller-provided spoken text."""
        result = _handle_which_project(
            cmd={},
            spoken="You are on web project.",
            session_mgr=_make_session_mgr(),
            loop=_make_loop(),
            active_project="web",
        )
        self.assertEqual(result.spoken, "You are on web project.")


# ── AC: _handle_last_message behavior ─────────────────────────────────────────


class TestHandleLastMessage(unittest.TestCase):
    """AC: last_message handler preserves original behavior."""

    def test_last_message_found_returns_project_specific_tts(self):
        """last_message found: speak_project must be the active project."""
        session_mgr = _make_session_mgr(last_resp="Here is your answer.")
        result = _handle_last_message(
            cmd={},
            spoken="",
            session_mgr=session_mgr,
            loop=_make_loop(),
            active_project="api-proj",
        )
        self.assertEqual(result.spoken, "Here is your answer.")
        self.assertEqual(result.speak_project, "api-proj")
        self.assertFalse(result.skip_tts)

    def test_last_message_not_found_returns_fallback_spoken(self):
        """last_message not found: returns fallback spoken text."""
        session_mgr = _make_session_mgr(last_resp=None)
        result = _handle_last_message(
            cmd={},
            spoken="",
            session_mgr=session_mgr,
            loop=_make_loop(),
            active_project="api-proj",
        )
        self.assertIsNotNone(result.spoken)
        self.assertNotEqual(result.spoken, "")

    def test_last_message_not_found_speak_project_empty(self):
        """last_message not found: speak_project defaults to '' (normal TTS routing)."""
        session_mgr = _make_session_mgr(last_resp=None)
        result = _handle_last_message(
            cmd={},
            spoken="",
            session_mgr=session_mgr,
            loop=_make_loop(),
            active_project="api-proj",
        )
        self.assertEqual(result.speak_project, "")

    def test_last_message_custom_spoken_when_not_found(self):
        """last_message not found: uses custom spoken if provided."""
        session_mgr = _make_session_mgr(last_resp=None)
        result = _handle_last_message(
            cmd={},
            spoken="Nothing to replay.",
            session_mgr=session_mgr,
            loop=_make_loop(),
            active_project="",
        )
        self.assertEqual(result.spoken, "Nothing to replay.")


# ── AC: _handle_rename_session behavior ───────────────────────────────────────


class TestHandleRenameSession(unittest.TestCase):
    """AC: rename_session handler preserves original behavior."""

    def test_rename_session_success_calls_rename_alias(self):
        """rename success: calls session_mgr.rename_alias."""
        session_mgr = _make_session_mgr(
            aliases={"web": "web-proj"},
            last_resp=None,
        )

        with patch("cyrus_brain._resolve_project", return_value="web-proj"):
            result = _handle_rename_session(
                cmd={"name": "frontend", "old": "web"},
                spoken="",
                session_mgr=session_mgr,
                loop=_make_loop(),
                active_project="web-proj",
            )

        session_mgr.rename_alias.assert_called_once()
        self.assertIn("frontend", result.spoken)

    def test_rename_session_success_returns_confirmation_spoken(self):
        """rename success: spoken text confirms new name."""
        session_mgr = _make_session_mgr(aliases={"web": "web-proj"})

        with patch("cyrus_brain._resolve_project", return_value="web-proj"):
            result = _handle_rename_session(
                cmd={"name": "frontend", "old": "web"},
                spoken="",
                session_mgr=session_mgr,
                loop=_make_loop(),
                active_project="web-proj",
            )

        self.assertIn("frontend", result.spoken)

    def test_rename_session_no_project_returns_error(self):
        """rename no matching project: returns error spoken, no rename."""
        session_mgr = _make_session_mgr(aliases={})

        with patch("cyrus_brain._resolve_project", return_value=None):
            result = _handle_rename_session(
                cmd={"name": "frontend", "old": "missing"},
                spoken="",
                session_mgr=session_mgr,
                loop=_make_loop(),
                active_project="",
            )

        session_mgr.rename_alias.assert_not_called()
        self.assertIsNotNone(result.spoken)

    def test_rename_session_no_new_name_returns_error(self):
        """rename empty new name: returns error spoken, no rename."""
        session_mgr = _make_session_mgr(aliases={"web": "web-proj"})

        with patch("cyrus_brain._resolve_project", return_value="web-proj"):
            result = _handle_rename_session(
                cmd={"name": "   ", "old": "web"},
                spoken="",
                session_mgr=session_mgr,
                loop=_make_loop(),
                active_project="web-proj",
            )

        session_mgr.rename_alias.assert_not_called()
        self.assertIsNotNone(result.spoken)

    def test_rename_session_uses_active_project_when_no_old_hint(self):
        """rename with no 'old' hint: falls back to active_project."""
        session_mgr = _make_session_mgr(aliases={"web": "web-proj"})

        with patch("cyrus_brain._resolve_project") as mock_resolve:
            # No old hint provided — should not call _resolve_project
            _handle_rename_session(
                cmd={"name": "frontend", "old": ""},
                spoken="",
                session_mgr=session_mgr,
                loop=_make_loop(),
                active_project="web-proj",
            )
            # _resolve_project should NOT be called when old hint is empty
            mock_resolve.assert_not_called()
        # rename_alias should be called since active_project is not empty
        session_mgr.rename_alias.assert_called_once()


# ── AC: _handle_pause behavior ─────────────────────────────────────────────────


class TestHandlePause(unittest.TestCase):
    """AC: pause handler preserves original behavior."""

    def test_pause_returns_skip_tts_true(self):
        """pause: skip_tts must be True (voice service handles the response)."""
        loop = _make_loop()
        with patch(
            "asyncio.run_coroutine_threadsafe",
            side_effect=_close_coro_side_effect,
        ):
            result = _handle_pause(
                cmd={},
                spoken="",
                session_mgr=_make_session_mgr(),
                loop=loop,
                active_project="",
            )
        self.assertTrue(result.skip_tts)

    def test_pause_sends_pause_message(self):
        """pause: must call asyncio.run_coroutine_threadsafe with pause message."""
        loop = _make_loop()
        with patch(
            "asyncio.run_coroutine_threadsafe",
            side_effect=_close_coro_side_effect,
        ) as mock_rct:
            _handle_pause(
                cmd={},
                spoken="",
                session_mgr=_make_session_mgr(),
                loop=loop,
                active_project="",
            )
        self.assertTrue(mock_rct.called)

    def test_pause_spoken_is_none(self):
        """pause: spoken must be None (nothing to say)."""
        loop = _make_loop()
        with patch(
            "asyncio.run_coroutine_threadsafe",
            side_effect=_close_coro_side_effect,
        ):
            result = _handle_pause(
                cmd={},
                spoken="",
                session_mgr=_make_session_mgr(),
                loop=loop,
                active_project="",
            )
        self.assertIsNone(result.spoken)


# ── AC: Dispatcher behavior ────────────────────────────────────────────────────


class TestDispatcher(unittest.TestCase):
    """AC: _execute_cyrus_command uses dispatch table; error handling improved."""

    def setUp(self):
        """Reset module-level globals before each test."""
        cyrus_brain._active_project = ""
        cyrus_brain._project_locked = False
        cyrus_brain._speak_queue = MagicMock()

    def test_dispatcher_calls_correct_handler(self):
        """Dispatcher must call the handler registered for the command type."""
        mock_handler = MagicMock(return_value=CommandResult())
        loop = _make_loop()

        with patch.dict("cyrus_brain._COMMAND_HANDLERS", {"test_cmd": mock_handler}):
            _execute_cyrus_command(
                ctype="test_cmd",
                cmd={},
                spoken="",
                session_mgr=_make_session_mgr(),
                loop=loop,
            )

        mock_handler.assert_called_once()

    def test_dispatcher_unknown_command_does_not_raise(self):
        """Dispatcher must not raise for unknown command types."""
        try:
            _execute_cyrus_command(
                ctype="not_a_real_command",
                cmd={},
                spoken="",
                session_mgr=_make_session_mgr(),
                loop=_make_loop(),
            )
        except Exception as exc:  # noqa: BLE001
            self.fail(f"Dispatcher raised for unknown command: {exc}")

    def test_dispatcher_unknown_command_logs_warning(self):
        """Dispatcher must log a warning for unknown command types."""
        with self.assertLogs("root", level="WARNING") as cm:
            _execute_cyrus_command(
                ctype="totally_unknown",
                cmd={},
                spoken="",
                session_mgr=_make_session_mgr(),
                loop=_make_loop(),
            )
        self.assertTrue(
            any("totally_unknown" in msg for msg in cm.output),
            f"Expected 'totally_unknown' in warning logs; got: {cm.output}",
        )

    def test_dispatcher_handler_exception_is_caught(self):
        """Dispatcher must catch handler exceptions and not re-raise."""

        def bad_handler(*_args, **_kwargs):
            raise ValueError("simulated handler failure")

        with patch.dict("cyrus_brain._COMMAND_HANDLERS", {"bad_cmd": bad_handler}):
            try:
                _execute_cyrus_command(
                    ctype="bad_cmd",
                    cmd={},
                    spoken="",
                    session_mgr=_make_session_mgr(),
                    loop=_make_loop(),
                )
            except Exception as exc:  # noqa: BLE001
                self.fail(f"Dispatcher re-raised handler exception: {exc}")

    def test_dispatcher_handler_exception_is_logged(self):
        """Dispatcher must log.exception for handler failures."""

        def bad_handler(*_args, **_kwargs):
            raise RuntimeError("test error")

        with patch.dict("cyrus_brain._COMMAND_HANDLERS", {"err_cmd": bad_handler}):
            with self.assertLogs("root", level="ERROR") as cm:
                _execute_cyrus_command(
                    ctype="err_cmd",
                    cmd={},
                    spoken="",
                    session_mgr=_make_session_mgr(),
                    loop=_make_loop(),
                )
        self.assertTrue(
            any("err_cmd" in msg for msg in cm.output),
            f"Expected command name in error log; got: {cm.output}",
        )

    def test_dispatcher_applies_new_active_project(self):
        """Dispatcher must update _active_project when handler returns new value."""
        mock_handler = MagicMock(
            return_value=CommandResult(new_active_project="new-proj")
        )
        loop = _make_loop()

        with patch.dict("cyrus_brain._COMMAND_HANDLERS", {"set_proj": mock_handler}):
            with patch("asyncio.run_coroutine_threadsafe"):
                _execute_cyrus_command(
                    ctype="set_proj",
                    cmd={},
                    spoken="",
                    session_mgr=_make_session_mgr(),
                    loop=loop,
                )

        self.assertEqual(cyrus_brain._active_project, "new-proj")

    def test_dispatcher_applies_new_project_locked(self):
        """Dispatcher must update _project_locked when handler returns new value."""
        mock_handler = MagicMock(return_value=CommandResult(new_project_locked=True))
        loop = _make_loop()

        with patch.dict("cyrus_brain._COMMAND_HANDLERS", {"lock_proj": mock_handler}):
            _execute_cyrus_command(
                ctype="lock_proj",
                cmd={},
                spoken="",
                session_mgr=_make_session_mgr(),
                loop=loop,
            )

        self.assertTrue(cyrus_brain._project_locked)

    def test_dispatcher_queues_tts_when_spoken(self):
        """Dispatcher must queue TTS when result has spoken text."""
        mock_handler = MagicMock(
            return_value=CommandResult(spoken="hello", speak_project="proj")
        )
        loop = _make_loop()

        with patch.dict("cyrus_brain._COMMAND_HANDLERS", {"say_cmd": mock_handler}):
            with patch("asyncio.run_coroutine_threadsafe") as mock_rct:
                _execute_cyrus_command(
                    ctype="say_cmd",
                    cmd={},
                    spoken="",
                    session_mgr=_make_session_mgr(),
                    loop=loop,
                )

        self.assertTrue(mock_rct.called)

    def test_dispatcher_skips_tts_when_skip_tts_true(self):
        """Dispatcher must not queue TTS when result.skip_tts is True."""
        mock_handler = MagicMock(
            return_value=CommandResult(spoken="hello", skip_tts=True)
        )
        loop = _make_loop()

        with patch.dict("cyrus_brain._COMMAND_HANDLERS", {"quiet_cmd": mock_handler}):
            with patch("asyncio.run_coroutine_threadsafe") as mock_rct:
                _execute_cyrus_command(
                    ctype="quiet_cmd",
                    cmd={},
                    spoken="",
                    session_mgr=_make_session_mgr(),
                    loop=loop,
                )

        # run_coroutine_threadsafe should NOT be called at all when skip_tts=True
        # (mock_handler has no side-effects that would call it)
        mock_rct.assert_not_called()

    def test_dispatcher_passes_active_project_snapshot_to_handler(self):
        """Dispatcher must pass the current _active_project to the handler."""
        cyrus_brain._active_project = "snapshot-proj"
        received_active = []

        def capture_handler(cmd, spoken, session_mgr, loop, active_project):
            received_active.append(active_project)
            return CommandResult()

        with patch.dict("cyrus_brain._COMMAND_HANDLERS", {"snap_cmd": capture_handler}):
            _execute_cyrus_command(
                ctype="snap_cmd",
                cmd={},
                spoken="",
                session_mgr=_make_session_mgr(),
                loop=_make_loop(),
            )

        self.assertEqual(received_active, ["snapshot-proj"])


# ── AC: No residual elif chain ─────────────────────────────────────────────────


class TestNoResidualElifChain(unittest.TestCase):
    """AC: _execute_cyrus_command must not contain the old if/elif chain."""

    @classmethod
    def setUpClass(cls):
        cls.source = BRAIN_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _get_execute_cyrus_command_source(self) -> str:
        """Extract the source lines of _execute_cyrus_command."""
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "_execute_cyrus_command"
            ):
                lines = self.source.splitlines()
                return "\n".join(lines[node.lineno - 1 : node.end_lineno])
        return ""

    def test_no_elif_ctype_in_execute_cyrus_command(self):
        """AC: _execute_cyrus_command must not contain 'elif ctype ==' chains."""
        func_src = self._get_execute_cyrus_command_source()
        self.assertNotIn(
            "elif ctype ==",
            func_src,
            "_execute_cyrus_command still contains 'elif ctype ==' — "
            "refactoring to dispatch table not complete",
        )

    def test_command_handlers_referenced_in_execute(self):
        """_execute_cyrus_command must reference _COMMAND_HANDLERS (dispatch table)."""
        func_src = self._get_execute_cyrus_command_source()
        self.assertIn(
            "_COMMAND_HANDLERS",
            func_src,
            "_execute_cyrus_command must look up handlers in _COMMAND_HANDLERS",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
