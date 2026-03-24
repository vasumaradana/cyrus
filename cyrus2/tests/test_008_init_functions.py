"""
Acceptance-driven tests for Issue 008: Break up main() functions into subsystems.

Tests verify every acceptance criterion from the issue:
  - main() in cyrus2/cyrus_brain.py reduced to < 50 lines
  - main() in cyrus2/main.py reduced to < 50 lines
  - Each subsystem in a separate _init_*() function
  - _init_*() functions return initialized objects/state
  - All original initialization behavior preserved (no logic changes)
  - Startup sequence documented with a comment block

Strategy: Static analysis (AST) for structural checks; runtime tests mock Windows
dependencies so the module imports cleanly on any platform.
"""

import ast
import asyncio
import sys
import threading
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

# Add cyrus2/ directory to sys.path so `import cyrus_brain` resolves correctly.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

import cyrus_brain  # noqa: E402

# Paths for static analysis.
BRAIN_PY = _CYRUS2_DIR / "cyrus_brain.py"
MAIN_PY = _CYRUS2_DIR / "main.py"

# Names of the _init_*() functions required in cyrus_brain.py.
REQUIRED_BRAIN_INIT_FUNCS = [
    "_init_queues",
    "_init_session",
    "_init_background_threads",
    "_init_async_tasks",
    "_init_servers",
]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_main_line_count(source_path: Path) -> int:
    """Return the line count of the main() function in *source_path* via AST."""
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "main"
        ):
            return node.end_lineno - node.lineno + 1
    raise AssertionError(f"main() function not found in {source_path}")


def _get_function_names(source_path: Path) -> set[str]:
    """Return all top-level (module-level) function names in *source_path*."""
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _get_calls_inside_function(source_path: Path, func_name: str) -> set[str]:
    """Return all simple function call names inside *func_name* in *source_path*."""
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    # Find the target function node
    target = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            target = node
            break
    if target is None:
        raise AssertionError(f"Function '{func_name}' not found in {source_path}")
    # Collect all Name-based calls within the function
    calls: set[str] = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)
    return calls


# ── AC: main() line counts ────────────────────────────────────────────────────


class TestMainLineCounts(unittest.TestCase):
    """AC: main() in both files reduced to < 50 lines."""

    def test_brain_main_line_count(self):
        """AC: main() in cyrus_brain.py must be < 50 lines."""
        self.assertTrue(BRAIN_PY.exists(), f"cyrus_brain.py not found at {BRAIN_PY}")
        count = _get_main_line_count(BRAIN_PY)
        self.assertLess(
            count,
            50,
            f"main() in cyrus_brain.py has {count} lines — must be < 50 to demonstrate "
            "orchestration via _init_*() extraction.",
        )

    def test_voice_main_line_count(self):
        """AC: main() in main.py must be < 50 lines (already a thin wrapper)."""
        self.assertTrue(MAIN_PY.exists(), f"main.py not found at {MAIN_PY}")
        count = _get_main_line_count(MAIN_PY)
        self.assertLess(
            count,
            50,
            f"main() in main.py has {count} lines — must be < 50.",
        )


# ── AC: Subsystem functions exist ─────────────────────────────────────────────


class TestInitFunctionsExistStatic(unittest.TestCase):
    """AC: Each subsystem in a separate _init_*() function — static analysis."""

    @classmethod
    def setUpClass(cls):
        cls.defined = _get_function_names(BRAIN_PY)

    def test_init_queues_defined(self):
        """_init_queues() must be defined in cyrus_brain.py."""
        self.assertIn(
            "_init_queues", self.defined, "_init_queues not found in cyrus_brain.py"
        )

    def test_init_session_defined(self):
        """_init_session() must be defined in cyrus_brain.py."""
        self.assertIn(
            "_init_session", self.defined, "_init_session not found in cyrus_brain.py"
        )

    def test_init_background_threads_defined(self):
        """_init_background_threads() must be defined in cyrus_brain.py."""
        self.assertIn(
            "_init_background_threads",
            self.defined,
            "_init_background_threads not found in cyrus_brain.py",
        )

    def test_init_async_tasks_defined(self):
        """_init_async_tasks() must be defined in cyrus_brain.py."""
        self.assertIn(
            "_init_async_tasks",
            self.defined,
            "_init_async_tasks not found in cyrus_brain.py",
        )

    def test_init_servers_defined(self):
        """_init_servers() must be defined in cyrus_brain.py."""
        self.assertIn(
            "_init_servers", self.defined, "_init_servers not found in cyrus_brain.py"
        )


class TestInitFunctionsCallableRuntime(unittest.TestCase):
    """AC: Each subsystem in a separate _init_*() function — runtime checks."""

    def test_init_queues_is_callable(self):
        """_init_queues must be callable in the imported cyrus_brain module."""
        fn = getattr(cyrus_brain, "_init_queues", None)
        self.assertIsNotNone(fn, "_init_queues not found in imported cyrus_brain")
        self.assertTrue(callable(fn), "_init_queues is not callable")

    def test_init_session_is_callable(self):
        """_init_session must be callable in the imported cyrus_brain module."""
        fn = getattr(cyrus_brain, "_init_session", None)
        self.assertIsNotNone(fn, "_init_session not found in imported cyrus_brain")
        self.assertTrue(callable(fn), "_init_session is not callable")

    def test_init_background_threads_is_callable(self):
        """_init_background_threads must be callable in the imported module."""
        fn = getattr(cyrus_brain, "_init_background_threads", None)
        self.assertIsNotNone(
            fn, "_init_background_threads not found in imported cyrus_brain"
        )
        self.assertTrue(callable(fn), "_init_background_threads is not callable")

    def test_init_async_tasks_is_callable(self):
        """_init_async_tasks must be callable in the imported cyrus_brain module."""
        fn = getattr(cyrus_brain, "_init_async_tasks", None)
        self.assertIsNotNone(fn, "_init_async_tasks not found in imported cyrus_brain")
        self.assertTrue(callable(fn), "_init_async_tasks is not callable")

    def test_init_servers_is_callable(self):
        """_init_servers must be callable in the imported cyrus_brain module."""
        fn = getattr(cyrus_brain, "_init_servers", None)
        self.assertIsNotNone(fn, "_init_servers not found in imported cyrus_brain")
        self.assertTrue(callable(fn), "_init_servers is not callable")


# ── AC: Subsystem functions return initialized state ─────────────────────────


class TestInitQueuesReturnsState(unittest.TestCase):
    """AC: _init_queues() returns initialized queue objects."""

    def test_returns_tuple_of_two_queues(self):
        """_init_queues() must return a (speak_queue, utterance_queue) tuple."""
        result = cyrus_brain._init_queues()
        self.assertIsInstance(result, tuple, "_init_queues() must return a tuple")
        self.assertEqual(
            len(result),
            2,
            f"_init_queues() must return exactly 2 items, got {len(result)}",
        )

    def test_speak_queue_is_asyncio_queue(self):
        """First return value (speak_queue) must be an asyncio.Queue."""
        speak_queue, _ = cyrus_brain._init_queues()
        self.assertIsInstance(
            speak_queue,
            asyncio.Queue,
            f"speak_queue must be asyncio.Queue, got {type(speak_queue).__name__}",
        )

    def test_utterance_queue_is_asyncio_queue(self):
        """Second return value (utterance_queue) must be an asyncio.Queue."""
        _, utterance_queue = cyrus_brain._init_queues()
        self.assertIsInstance(
            utterance_queue,
            asyncio.Queue,
            "utterance_queue must be asyncio.Queue, "
            f"got {type(utterance_queue).__name__}",
        )

    def test_queues_are_empty_on_creation(self):
        """Both queues must start empty — no stale data from previous init."""
        speak_queue, utterance_queue = cyrus_brain._init_queues()
        self.assertTrue(speak_queue.empty(), "speak_queue must be empty on creation")
        self.assertTrue(
            utterance_queue.empty(), "utterance_queue must be empty on creation"
        )

    def test_returns_distinct_queue_objects(self):
        """speak_queue and utterance_queue must be different objects."""
        speak_queue, utterance_queue = cyrus_brain._init_queues()
        self.assertIsNot(
            speak_queue,
            utterance_queue,
            "speak_queue and utterance_queue must be distinct Queue objects",
        )


class TestInitSessionReturnsManager(unittest.TestCase):
    """AC: _init_session() returns initialized SessionManager."""

    def test_returns_session_manager(self):
        """_init_session() must return the SessionManager via _make_session_manager."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_mgr = MagicMock()
        with (
            patch.object(cyrus_brain, "_make_session_manager", return_value=mock_mgr),
            patch.object(cyrus_brain, "_vs_code_windows", return_value=[]),
        ):
            result = cyrus_brain._init_session(mock_loop)
        self.assertIs(
            result, mock_mgr, "_init_session() must return the session manager"
        )

    def test_calls_session_manager_start(self):
        """_init_session() must call session_mgr.start() to begin session scanning."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_mgr = MagicMock()
        with (
            patch.object(cyrus_brain, "_make_session_manager", return_value=mock_mgr),
            patch.object(cyrus_brain, "_vs_code_windows", return_value=[]),
        ):
            cyrus_brain._init_session(mock_loop)
        mock_mgr.start.assert_called_once()

    def test_handles_no_vscode_windows(self):
        """_init_session() must not raise when no VS Code windows are open."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_mgr = MagicMock()
        with (
            patch.object(cyrus_brain, "_make_session_manager", return_value=mock_mgr),
            patch.object(cyrus_brain, "_vs_code_windows", return_value=[]),
        ):
            # Should not raise
            result = cyrus_brain._init_session(mock_loop)
        self.assertIs(result, mock_mgr)

    def test_seeds_active_project_from_first_vscode_window(self):
        """_init_session() must seed _active_project from the first VS Code window."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_mgr = MagicMock()
        # Simulate two VS Code windows found
        with (
            patch.object(cyrus_brain, "_make_session_manager", return_value=mock_mgr),
            patch.object(
                cyrus_brain,
                "_vs_code_windows",
                return_value=[("my-project", None), ("other", None)],
            ),
        ):
            cyrus_brain._init_session(mock_loop)
        with cyrus_brain._active_project_lock:
            proj = cyrus_brain._active_project
        self.assertEqual(
            proj,
            "my-project",
            f"_active_project should be 'my-project', got '{proj}'",
        )


class TestInitBackgroundThreadsStartsDaemons(unittest.TestCase):
    """AC: _init_background_threads() starts the required daemon threads."""

    def test_starts_two_daemon_threads(self):
        """_init_background_threads() must start exactly 2 daemon threads."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_mgr = MagicMock()
        started_threads: list[threading.Thread] = []

        def track_start(self_thread, *args, **kwargs):
            started_threads.append(self_thread)
            # Don't actually start — we just want to count daemon threads

        with (
            patch.object(cyrus_brain, "_start_active_tracker"),
            patch.object(cyrus_brain, "_submit_worker"),
            patch.object(threading.Thread, "start", track_start),
        ):
            cyrus_brain._init_background_threads(mock_mgr, mock_loop)

        self.assertEqual(
            len(started_threads),
            2,
            f"Expected 2 daemon threads to be started, got {len(started_threads)}",
        )
        for t in started_threads:
            self.assertTrue(t.daemon, f"Thread {t} must be a daemon thread")


# ── AC: main() orchestrates all _init_* functions ─────────────────────────────


class TestBrainMainCallsAllInits(unittest.TestCase):
    """AC: main() calls all _init_*() subsystem functions — static analysis."""

    @classmethod
    def setUpClass(cls):
        cls.calls_in_main = _get_calls_inside_function(BRAIN_PY, "main")

    def test_main_calls_init_queues(self):
        """main() must call _init_queues() to initialize communication queues."""
        self.assertIn(
            "_init_queues",
            self.calls_in_main,
            "main() must call _init_queues()",
        )

    def test_main_calls_init_session(self):
        """main() must call _init_session() to start the session manager."""
        self.assertIn(
            "_init_session",
            self.calls_in_main,
            "main() must call _init_session()",
        )

    def test_main_calls_init_background_threads(self):
        """main() must call _init_background_threads() to start daemon threads."""
        self.assertIn(
            "_init_background_threads",
            self.calls_in_main,
            "main() must call _init_background_threads()",
        )

    def test_main_calls_init_async_tasks(self):
        """main() must call _init_async_tasks() to schedule coroutine tasks."""
        self.assertIn(
            "_init_async_tasks",
            self.calls_in_main,
            "main() must call _init_async_tasks()",
        )

    def test_main_calls_init_servers(self):
        """main() must call _init_servers() to bind TCP and WebSocket servers."""
        self.assertIn(
            "_init_servers",
            self.calls_in_main,
            "main() must call _init_servers()",
        )


# ── AC: Startup sequence documented ───────────────────────────────────────────


class TestStartupSequenceDocumented(unittest.TestCase):
    """AC: Startup sequence clear and documented."""

    def test_startup_sequence_comment_in_brain(self):
        """cyrus_brain.py main() must contain a 'Startup sequence' comment block."""
        self.assertTrue(BRAIN_PY.exists(), f"cyrus_brain.py not found at {BRAIN_PY}")
        source = BRAIN_PY.read_text(encoding="utf-8")
        self.assertIn(
            "Startup sequence",
            source,
            "cyrus_brain.py must contain a 'Startup sequence' comment in main()",
        )


# ── AC: All _init_*() functions have docstrings ───────────────────────────────


class TestInitFunctionDocstrings(unittest.TestCase):
    """AC: All exported _init_*() functions have docstrings explaining context."""

    @classmethod
    def setUpClass(cls):
        source = BRAIN_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(source)

    def _get_docstring(self, func_name: str) -> str | None:
        """Return the docstring for a function, or None if absent."""
        for node in ast.walk(self.tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == func_name
            ):
                return ast.get_docstring(node)
        return None  # function not found — will be caught by existence tests

    def test_init_queues_has_docstring(self):
        """_init_queues() must have a docstring."""
        ds = self._get_docstring("_init_queues")
        self.assertIsNotNone(ds, "_init_queues() must have a docstring")
        self.assertGreater(len(ds), 0, "_init_queues() docstring must not be empty")

    def test_init_session_has_docstring(self):
        """_init_session() must have a docstring."""
        ds = self._get_docstring("_init_session")
        self.assertIsNotNone(ds, "_init_session() must have a docstring")
        self.assertGreater(len(ds), 0, "_init_session() docstring must not be empty")

    def test_init_background_threads_has_docstring(self):
        """_init_background_threads() must have a docstring."""
        ds = self._get_docstring("_init_background_threads")
        self.assertIsNotNone(ds, "_init_background_threads() must have a docstring")
        self.assertGreater(
            len(ds), 0, "_init_background_threads() docstring must not be empty"
        )

    def test_init_async_tasks_has_docstring(self):
        """_init_async_tasks() must have a docstring."""
        ds = self._get_docstring("_init_async_tasks")
        self.assertIsNotNone(ds, "_init_async_tasks() must have a docstring")
        self.assertGreater(
            len(ds), 0, "_init_async_tasks() docstring must not be empty"
        )

    def test_init_servers_has_docstring(self):
        """_init_servers() must have a docstring."""
        ds = self._get_docstring("_init_servers")
        self.assertIsNotNone(ds, "_init_servers() must have a docstring")
        self.assertGreater(len(ds), 0, "_init_servers() docstring must not be empty")


# ── Edge cases ─────────────────────────────────────────────────────────────────


class TestEdgeCases(unittest.TestCase):
    """Edge and corner cases for the _init_*() functions."""

    def test_init_queues_returns_fresh_queues_on_each_call(self):
        """Each _init_queues() call returns a fresh queue pair (no stale state)."""
        q1a, q1b = cyrus_brain._init_queues()
        q2a, q2b = cyrus_brain._init_queues()
        self.assertIsNot(q1a, q2a, "Each call must return a new speak_queue object")
        self.assertIsNot(q1b, q2b, "Each call must return a new utterance_queue object")

    def test_init_session_passes_loop_to_make_session_manager(self):
        """_init_session() must pass the event loop to _make_session_manager."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_mgr = MagicMock()
        with (
            patch.object(
                cyrus_brain, "_make_session_manager", return_value=mock_mgr
            ) as mock_factory,
            patch.object(cyrus_brain, "_vs_code_windows", return_value=[]),
        ):
            cyrus_brain._init_session(mock_loop)
        mock_factory.assert_called_once_with(mock_loop)

    def test_brain_main_line_count_is_strictly_less_than_50(self):
        """Boundary check: main() is strictly < 50 (not == 50)."""
        count = _get_main_line_count(BRAIN_PY)
        self.assertLess(
            count,
            50,
            f"main() has {count} lines — must be strictly < 50",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
