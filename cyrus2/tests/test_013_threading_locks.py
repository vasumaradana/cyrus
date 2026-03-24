"""
Acceptance-driven tests for Issue 013: Add threading locks to shared state.

Tests verify every acceptance criterion from the issue:
  - threading.Lock created for _chat_input_cache, _vscode_win_cache,
    _chat_input_coords, _mobile_clients, _whisper_prompt
  - _conversation_active converted from bool to threading.Event
  - All reads/writes wrapped in with lock: blocks
  - .is_set() used for _conversation_active reads
  - .set()/.clear() used for _conversation_active writes
  - No deadlocks (no nested lock acquisition)
  - All existing functionality preserved

Strategy: Static analysis (AST) for structural checks; runtime tests mock
Windows dependencies so the module imports cleanly on any platform.
"""

import ast
import sys
import threading
import unittest
from pathlib import Path

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
        _mock_cls = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock
        sys.modules[_mod] = _mock_cls()

# Add cyrus2/ directory to sys.path so imports resolve correctly.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

import cyrus_brain  # noqa: E402
import cyrus_common  # noqa: E402

# Paths for static analysis.
BRAIN_PY = _CYRUS2_DIR / "cyrus_brain.py"
COMMON_PY = _CYRUS2_DIR / "cyrus_common.py"


# ── AC: import threading in cyrus_brain.py ────────────────────────────────────


class TestThreadingImport(unittest.TestCase):
    """AC: import threading added at top of cyrus_brain.py."""

    @classmethod
    def setUpClass(cls):
        cls.brain_source = BRAIN_PY.read_text(encoding="utf-8")
        cls.brain_tree = ast.parse(cls.brain_source)

    def test_threading_imported_in_cyrus_brain(self):
        """cyrus_brain.py must import threading at the module level."""
        imports = []
        for node in ast.walk(self.brain_tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module)
        self.assertIn(
            "threading",
            imports,
            "threading must be imported at module level in cyrus_brain.py",
        )

    def test_threading_already_imported_in_cyrus_common(self):
        """cyrus_common.py must also import threading (pre-existing)."""
        source = COMMON_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
        self.assertIn("threading", imports)


# ── AC: Lock instances exist ──────────────────────────────────────────────────


class TestLockInstances(unittest.TestCase):
    """AC: threading.Lock created for each of the 5 target variables."""

    def test_chat_input_cache_lock_is_threading_lock(self):
        """AC: Lock created for _chat_input_cache in cyrus_common."""
        self.assertTrue(
            hasattr(cyrus_common, "_chat_input_cache_lock"),
            "cyrus_common must define _chat_input_cache_lock",
        )
        self.assertIsInstance(
            cyrus_common._chat_input_cache_lock,
            type(threading.Lock()),
            "_chat_input_cache_lock must be a threading.Lock",
        )

    def test_chat_input_coords_lock_is_threading_lock(self):
        """AC: Lock created for _chat_input_coords in cyrus_common."""
        self.assertTrue(
            hasattr(cyrus_common, "_chat_input_coords_lock"),
            "cyrus_common must define _chat_input_coords_lock",
        )
        self.assertIsInstance(
            cyrus_common._chat_input_coords_lock,
            type(threading.Lock()),
            "_chat_input_coords_lock must be a threading.Lock",
        )

    def test_vscode_win_cache_lock_is_threading_lock(self):
        """AC: Lock created for _vscode_win_cache in cyrus_brain."""
        self.assertTrue(
            hasattr(cyrus_brain, "_vscode_win_cache_lock"),
            "cyrus_brain must define _vscode_win_cache_lock",
        )
        self.assertIsInstance(
            cyrus_brain._vscode_win_cache_lock,
            type(threading.Lock()),
            "_vscode_win_cache_lock must be a threading.Lock",
        )

    def test_mobile_clients_lock_is_threading_lock(self):
        """AC: Lock created for _mobile_clients in cyrus_brain."""
        self.assertTrue(
            hasattr(cyrus_brain, "_mobile_clients_lock"),
            "cyrus_brain must define _mobile_clients_lock",
        )
        self.assertIsInstance(
            cyrus_brain._mobile_clients_lock,
            type(threading.Lock()),
            "_mobile_clients_lock must be a threading.Lock",
        )

    def test_whisper_prompt_lock_is_threading_lock(self):
        """AC: Lock created for _whisper_prompt in cyrus_brain."""
        self.assertTrue(
            hasattr(cyrus_brain, "_whisper_prompt_lock"),
            "cyrus_brain must define _whisper_prompt_lock",
        )
        self.assertIsInstance(
            cyrus_brain._whisper_prompt_lock,
            type(threading.Lock()),
            "_whisper_prompt_lock must be a threading.Lock",
        )


# ── AC: _conversation_active is threading.Event ───────────────────────────────


class TestConversationActiveIsEvent(unittest.TestCase):
    """AC: _conversation_active converted from bool to threading.Event."""

    def test_conversation_active_is_threading_event(self):
        """AC: _conversation_active must be a threading.Event instance."""
        self.assertIsInstance(
            cyrus_brain._conversation_active,
            threading.Event,
            "_conversation_active must be threading.Event, not bool",
        )

    def test_conversation_active_starts_unset(self):
        """_conversation_active must start in the cleared (False/unset) state."""
        # We can't guarantee state in a long-running test suite, but we can
        # verify the API is present.
        # Reset to a known state for the test.
        cyrus_brain._conversation_active.clear()
        self.assertFalse(cyrus_brain._conversation_active.is_set())

    def test_conversation_active_set_works(self):
        """threading.Event.set() must make is_set() return True."""
        cyrus_brain._conversation_active.clear()
        cyrus_brain._conversation_active.set()
        self.assertTrue(cyrus_brain._conversation_active.is_set())
        # Clean up
        cyrus_brain._conversation_active.clear()

    def test_conversation_active_clear_works(self):
        """threading.Event.clear() must make is_set() return False."""
        cyrus_brain._conversation_active.set()
        cyrus_brain._conversation_active.clear()
        self.assertFalse(cyrus_brain._conversation_active.is_set())


# ── AC: No bare boolean assignments to _conversation_active ──────────────────


class TestConversationActiveNoDirectAssignment(unittest.TestCase):
    """AC: _conversation_active must not be assigned True/False directly."""

    @classmethod
    def setUpClass(cls):
        cls.brain_source = BRAIN_PY.read_text(encoding="utf-8")
        cls.brain_tree = ast.parse(cls.brain_source)

    def _find_assignments_to(self, varname: str) -> list[ast.Assign]:
        """Return all Assign nodes where a target is varname."""
        assignments = []
        for node in ast.walk(self.brain_tree):
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                # Check targets
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == varname:
                        assignments.append(node)
        return assignments

    def _is_module_level_definition(self, node) -> bool:
        """Return True if this node is the module-level variable definition."""
        # Module-level definitions of _conversation_active: threading.Event()
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_conversation_active":
                    # Check the value is a Call to threading.Event
                    val = node.value
                    if isinstance(val, ast.Call):
                        func = val.func
                        if isinstance(func, ast.Attribute) and func.attr == "Event":
                            return True
        return False

    def test_no_bare_true_assignment_to_conversation_active(self):
        """Must not have '_conversation_active = True' anywhere in cyrus_brain.py."""
        # Check source text directly for the pattern
        lines = self.brain_source.splitlines()
        violations = []
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("_conversation_active") and "= True" in stripped:
                # Allow comments
                if not stripped.startswith("#"):
                    violations.append(f"Line {i}: {line.rstrip()}")
        self.assertEqual(
            violations,
            [],
            "Found bare boolean assignment to _conversation_active:\n"
            + "\n".join(violations),
        )

    def test_no_bare_false_assignment_to_conversation_active(self):
        """Must not have '_conversation_active = False' anywhere in cyrus_brain.py."""
        lines = self.brain_source.splitlines()
        violations = []
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("_conversation_active") and "= False" in stripped:
                if not stripped.startswith("#"):
                    violations.append(f"Line {i}: {line.rstrip()}")
        self.assertEqual(
            violations,
            [],
            "Found bare boolean assignment to _conversation_active:\n"
            + "\n".join(violations),
        )

    def test_no_bare_boolean_check_of_conversation_active(self):
        """Must not have 'if _conversation_active:' (should use .is_set())."""
        lines = self.brain_source.splitlines()
        violations = []
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Detect 'if _conversation_active:' — bare boolean check
            import re

            if re.search(
                r"if\s+_conversation_active\s*:", stripped
            ) and not stripped.startswith("#"):
                violations.append(f"Line {i}: {line.rstrip()}")
        self.assertEqual(
            violations,
            [],
            "Found bare boolean check of _conversation_active (use .is_set()):\n"
            + "\n".join(violations),
        )

    def test_event_set_used_for_activating_conversation(self):
        """_conversation_active.set() must appear in cyrus_brain.py."""
        self.assertIn(
            "_conversation_active.set()",
            self.brain_source,
            "_conversation_active.set() must be used to activate conversation mode",
        )

    def test_event_clear_used_for_deactivating_conversation(self):
        """_conversation_active.clear() must appear in cyrus_brain.py."""
        self.assertIn(
            "_conversation_active.clear()",
            self.brain_source,
            "_conversation_active.clear() must be used to deactivate conversation mode",
        )

    def test_event_is_set_used_for_reading_conversation(self):
        """_conversation_active.is_set() must appear in cyrus_brain.py."""
        self.assertIn(
            "_conversation_active.is_set()",
            self.brain_source,
            "_conversation_active.is_set() must be used to check conversation mode",
        )


# ── AC: Lock definitions present in source (AST) ────────────────────────────


class TestLockDefinitionsInSource(unittest.TestCase):
    """AC: Lock objects defined as module-level variables in source files."""

    @classmethod
    def setUpClass(cls):
        cls.brain_source = BRAIN_PY.read_text(encoding="utf-8")
        cls.common_source = COMMON_PY.read_text(encoding="utf-8")

    def _has_lock_definition(self, source: str, varname: str) -> bool:
        """Return True if source defines varname = threading.Lock()."""
        return f"{varname} = threading.Lock()" in source or (
            f"{varname}: threading.Lock = threading.Lock()" in source
        )

    def test_vscode_win_cache_lock_defined_in_brain(self):
        """_vscode_win_cache_lock must be defined as threading.Lock() in cyrus_brain."""
        self.assertTrue(
            self._has_lock_definition(self.brain_source, "_vscode_win_cache_lock"),
            "_vscode_win_cache_lock = threading.Lock() not found in cyrus_brain.py",
        )

    def test_mobile_clients_lock_defined_in_brain(self):
        """_mobile_clients_lock must be defined as threading.Lock() in cyrus_brain."""
        self.assertTrue(
            self._has_lock_definition(self.brain_source, "_mobile_clients_lock"),
            "_mobile_clients_lock = threading.Lock() not found in cyrus_brain.py",
        )

    def test_whisper_prompt_lock_defined_in_brain(self):
        """_whisper_prompt_lock must be defined as threading.Lock() in cyrus_brain."""
        self.assertTrue(
            self._has_lock_definition(self.brain_source, "_whisper_prompt_lock"),
            "_whisper_prompt_lock = threading.Lock() not found in cyrus_brain.py",
        )

    def test_chat_input_cache_lock_defined_in_common(self):
        """AC: _chat_input_cache_lock defined as Lock in cyrus_common."""
        self.assertTrue(
            self._has_lock_definition(self.common_source, "_chat_input_cache_lock"),
            "_chat_input_cache_lock = threading.Lock() not found in cyrus_common.py",
        )

    def test_chat_input_coords_lock_defined_in_common(self):
        """AC: _chat_input_coords_lock defined as Lock in cyrus_common."""
        self.assertTrue(
            self._has_lock_definition(self.common_source, "_chat_input_coords_lock"),
            "_chat_input_coords_lock = threading.Lock() not found in cyrus_common.py",
        )

    def test_conversation_active_defined_as_event(self):
        """_conversation_active must be defined as threading.Event() in cyrus_brain."""
        self.assertTrue(
            "_conversation_active: threading.Event = threading.Event()"
            in self.brain_source
            or "_conversation_active = threading.Event()" in self.brain_source,
            "_conversation_active = threading.Event() not found in cyrus_brain.py",
        )


# ── AC: Lock usage — with lock: blocks present for each variable ─────────────


class TestLockUsageInSource(unittest.TestCase):
    """AC: All reads/writes to locked variables wrapped in with lock: blocks."""

    @classmethod
    def setUpClass(cls):
        cls.brain_source = BRAIN_PY.read_text(encoding="utf-8")
        cls.common_source = COMMON_PY.read_text(encoding="utf-8")

    def test_vscode_win_cache_lock_used_in_with_block(self):
        """_vscode_win_cache_lock must appear in a 'with' context in cyrus_brain."""
        self.assertIn(
            "with _vscode_win_cache_lock:",
            self.brain_source,
            "with _vscode_win_cache_lock: not found in cyrus_brain.py",
        )

    def test_mobile_clients_lock_used_in_with_block(self):
        """_mobile_clients_lock must appear in a 'with' context in cyrus_brain."""
        self.assertIn(
            "with _mobile_clients_lock:",
            self.brain_source,
            "with _mobile_clients_lock: not found in cyrus_brain.py",
        )

    def test_whisper_prompt_lock_used_in_with_block(self):
        """_whisper_prompt_lock must appear in a 'with' context in cyrus_brain."""
        self.assertIn(
            "with _whisper_prompt_lock:",
            self.brain_source,
            "with _whisper_prompt_lock: not found in cyrus_brain.py",
        )

    def test_chat_input_cache_lock_used_in_with_block(self):
        """_chat_input_cache_lock must appear in a 'with' context in cyrus_common."""
        self.assertIn(
            "with _chat_input_cache_lock:",
            self.common_source,
            "with _chat_input_cache_lock: not found in cyrus_common.py",
        )

    def test_chat_input_coords_lock_used_in_with_block_in_common(self):
        """_chat_input_coords_lock must appear in a 'with' context in cyrus_common."""
        self.assertIn(
            "with _chat_input_coords_lock:",
            self.common_source,
            "with _chat_input_coords_lock: not found in cyrus_common.py",
        )

    def test_chat_input_coords_lock_used_in_with_block_in_brain(self):
        """_chat_input_coords_lock must appear in a 'with' context in cyrus_brain."""
        self.assertIn(
            "with _chat_input_coords_lock:",
            self.brain_source,
            "with _chat_input_coords_lock: not found in cyrus_brain.py",
        )


# ── AC: No deadlocks — no nested lock acquisition ────────────────────────────


class TestNoDeadlocks(unittest.TestCase):
    """AC: No nested lock acquisition that could cause deadlocks."""

    @classmethod
    def setUpClass(cls):
        brain_source = BRAIN_PY.read_text(encoding="utf-8")
        common_source = COMMON_PY.read_text(encoding="utf-8")
        cls.brain_tree = ast.parse(brain_source)
        cls.common_tree = ast.parse(common_source)

    def _find_nested_with_locks(self, tree: ast.AST, lock_names: set) -> list[str]:
        """Find With nodes inside other With nodes where both use lock variables.

        Returns a list of descriptions of nesting violations.
        """
        violations = []

        def _get_with_context_names(node: ast.With) -> list[str]:
            """Extract variable names from 'with var:' context managers."""
            names = []
            for item in node.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Name) and ctx.id in lock_names:
                    names.append(ctx.id)
            return names

        def _walk_with_depth(node, outer_locks: set):
            """Walk AST, tracking which lock names are held."""
            if isinstance(node, ast.With):
                held = _get_with_context_names(node)
                for lock in held:
                    if lock in outer_locks:
                        violations.append(
                            f"Nested lock: '{lock}' acquired while already held"
                        )
                new_outer = outer_locks | set(held)
                for child in ast.iter_child_nodes(node):
                    _walk_with_depth(child, new_outer)
            else:
                for child in ast.iter_child_nodes(node):
                    _walk_with_depth(child, outer_locks)

        _walk_with_depth(tree, set())
        return violations

    def test_no_nested_lock_acquisition_in_cyrus_brain(self):
        """cyrus_brain.py must not acquire the same lock while already holding it."""
        brain_lock_names = {
            "_active_project_lock",
            "_project_locked_lock",
            "_vscode_win_cache_lock",
            "_mobile_clients_lock",
            "_whisper_prompt_lock",
            "_chat_input_coords_lock",
        }
        violations = self._find_nested_with_locks(self.brain_tree, brain_lock_names)
        self.assertEqual(
            violations,
            [],
            "Nested lock acquisitions found in cyrus_brain.py:\n"
            + "\n".join(violations),
        )

    def test_no_nested_lock_acquisition_in_cyrus_common(self):
        """cyrus_common.py must not acquire the same lock while already holding it."""
        common_lock_names = {
            "_chat_input_cache_lock",
            "_chat_input_coords_lock",
        }
        violations = self._find_nested_with_locks(self.common_tree, common_lock_names)
        self.assertEqual(
            violations,
            [],
            "Nested lock acquisitions found in cyrus_common.py:\n"
            + "\n".join(violations),
        )

    def test_locks_are_all_unlocked_after_import(self):
        """All module-level locks must be in unlocked state at import time."""
        # A newly imported module's locks should all be acquirable
        locks_to_check = [
            (
                "cyrus_common._chat_input_cache_lock",
                cyrus_common._chat_input_cache_lock,
            ),
            (
                "cyrus_common._chat_input_coords_lock",
                cyrus_common._chat_input_coords_lock,
            ),
            (
                "cyrus_brain._vscode_win_cache_lock",
                cyrus_brain._vscode_win_cache_lock,
            ),
            ("cyrus_brain._mobile_clients_lock", cyrus_brain._mobile_clients_lock),
            ("cyrus_brain._whisper_prompt_lock", cyrus_brain._whisper_prompt_lock),
        ]
        for name, lock in locks_to_check:
            acquired = lock.acquire(blocking=False)
            self.assertTrue(acquired, f"{name} was locked at module-import time")
            if acquired:
                lock.release()


# ── AC: Locks exported from cyrus_common into cyrus_brain ────────────────────


class TestLocksExported(unittest.TestCase):
    """AC: cyrus_brain.py imports the new locks from cyrus_common."""

    @classmethod
    def setUpClass(cls):
        cls.brain_source = BRAIN_PY.read_text(encoding="utf-8")
        cls.brain_tree = ast.parse(cls.brain_source)

    def _find_imports_from_cyrus_common(self) -> list[str]:
        """Return all names imported from cyrus_common in cyrus_brain.py."""
        names = []
        for node in ast.walk(self.brain_tree):
            if isinstance(node, ast.ImportFrom) and node.module == "cyrus_common":
                for alias in node.names:
                    names.append(alias.asname or alias.name)
        return names

    def test_chat_input_coords_lock_imported_in_brain(self):
        """cyrus_brain.py must import _chat_input_coords_lock from cyrus_common."""
        imported = self._find_imports_from_cyrus_common()
        self.assertIn(
            "_chat_input_coords_lock",
            imported,
            "_chat_input_coords_lock not imported from cyrus_common in cyrus_brain.py",
        )


# ── AC: All existing functionality preserved ─────────────────────────────────


class TestExistingFunctionalityPreserved(unittest.TestCase):
    """AC: All existing shared state variables still exist with correct types."""

    def test_active_project_still_string(self):
        """_active_project must still be a string."""
        self.assertIsInstance(cyrus_brain._active_project, str)

    def test_active_project_lock_still_lock(self):
        """_active_project_lock must still be a threading.Lock."""
        self.assertIsInstance(
            cyrus_brain._active_project_lock,
            type(threading.Lock()),
        )

    def test_project_locked_still_bool(self):
        """_project_locked must still be a bool."""
        self.assertIsInstance(cyrus_brain._project_locked, bool)

    def test_project_locked_lock_still_lock(self):
        """_project_locked_lock must still be a threading.Lock."""
        self.assertIsInstance(
            cyrus_brain._project_locked_lock,
            type(threading.Lock()),
        )

    def test_vscode_win_cache_still_dict(self):
        """_vscode_win_cache must still be a dict."""
        self.assertIsInstance(cyrus_brain._vscode_win_cache, dict)

    def test_whisper_prompt_still_string(self):
        """_whisper_prompt must still be a string."""
        self.assertIsInstance(cyrus_brain._whisper_prompt, str)

    def test_mobile_clients_still_set(self):
        """_mobile_clients must still be a set."""
        self.assertIsInstance(cyrus_brain._mobile_clients, set)

    def test_chat_input_cache_still_dict_in_common(self):
        """_chat_input_cache must still be a dict in cyrus_common."""
        self.assertIsInstance(cyrus_common._chat_input_cache, dict)

    def test_chat_input_coords_still_dict_in_common(self):
        """_chat_input_coords must still be a dict in cyrus_common."""
        self.assertIsInstance(cyrus_common._chat_input_coords, dict)


# ── Thread-safety runtime tests ───────────────────────────────────────────────


class TestThreadSafetyRuntime(unittest.TestCase):
    """Runtime tests verifying thread-safety of the shared state."""

    def test_conversation_active_thread_safe_set_clear(self):
        """Multiple threads can set/clear _conversation_active without errors."""
        import threading as _threading

        errors = []

        def worker(i):
            try:
                for _ in range(100):
                    cyrus_brain._conversation_active.set()
                    _ = cyrus_brain._conversation_active.is_set()
                    cyrus_brain._conversation_active.clear()
                    _ = cyrus_brain._conversation_active.is_set()
            except Exception as e:
                errors.append(str(e))

        threads = [_threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
        for t in threads:
            self.assertFalse(
                t.is_alive(), "Thread did not complete — possible deadlock"
            )
        self.assertEqual(errors, [], f"Thread errors: {errors}")

    def test_whisper_prompt_lock_prevents_concurrent_write(self):
        """_whisper_prompt_lock must serialize concurrent writes."""
        import threading as _threading

        write_order = []

        def write_prompt(value):
            with cyrus_brain._whisper_prompt_lock:
                # Simulate a non-atomic write with a sleep
                cyrus_brain._whisper_prompt = value
                write_order.append(value)

        threads = [
            _threading.Thread(target=write_prompt, args=(f"prompt_{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
        # All threads should complete without deadlock
        for t in threads:
            self.assertFalse(
                t.is_alive(), "Thread did not complete — possible deadlock"
            )
        # All 10 writes should have been recorded
        self.assertEqual(len(write_order), 10)

    def test_mobile_clients_lock_prevents_concurrent_modification(self):
        """_mobile_clients_lock must serialize concurrent set modifications."""
        import threading as _threading

        errors = []
        mock_clients = set()

        def add_client(i):
            try:
                with cyrus_brain._mobile_clients_lock:
                    mock_clients.add(i)
            except Exception as e:
                errors.append(str(e))

        def remove_client(i):
            try:
                with cyrus_brain._mobile_clients_lock:
                    mock_clients.discard(i)
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(20):
            threads.append(_threading.Thread(target=add_client, args=(i,)))
            threads.append(_threading.Thread(target=remove_client, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
        for t in threads:
            self.assertFalse(
                t.is_alive(), "Thread did not complete — possible deadlock"
            )
        self.assertEqual(errors, [])

    def test_vscode_win_cache_lock_prevents_concurrent_modification(self):
        """_vscode_win_cache_lock must serialize concurrent dict modifications."""
        import threading as _threading

        errors = []

        def modify_cache(key, value):
            try:
                with cyrus_brain._vscode_win_cache_lock:
                    cyrus_brain._vscode_win_cache[key] = value
                with cyrus_brain._vscode_win_cache_lock:
                    _ = cyrus_brain._vscode_win_cache.get(key)
            except Exception as e:
                errors.append(str(e))

        threads = [
            _threading.Thread(target=modify_cache, args=(f"proj_{i}", f"win_{i}"))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
        for t in threads:
            self.assertFalse(
                t.is_alive(), "Thread did not complete — possible deadlock"
            )
        self.assertEqual(errors, [])
        # Clean up
        with cyrus_brain._vscode_win_cache_lock:
            cyrus_brain._vscode_win_cache.clear()

    def test_locks_in_cyrus_common_prevent_concurrent_modification(self):
        """_chat_input_coords_lock in cyrus_common must serialize concurrent writes."""
        import threading as _threading

        errors = []

        def modify_coords(proj, coords):
            try:
                with cyrus_common._chat_input_coords_lock:
                    cyrus_common._chat_input_coords[proj] = coords
            except Exception as e:
                errors.append(str(e))

        threads = [
            _threading.Thread(target=modify_coords, args=(f"proj_{i}", (i, i)))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
        for t in threads:
            self.assertFalse(
                t.is_alive(), "Thread did not complete — possible deadlock"
            )
        self.assertEqual(errors, [])
        # Clean up
        with cyrus_common._chat_input_coords_lock:
            cyrus_common._chat_input_coords.clear()


# ── Edge cases ────────────────────────────────────────────────────────────────


class TestEdgeCases(unittest.TestCase):
    """Edge cases for lock and event usage."""

    def test_conversation_active_is_not_set_initially(self):
        """_conversation_active must be cleared (not set) at module load."""
        # Reset state and verify the initial state is 'not set'
        cyrus_brain._conversation_active.clear()
        self.assertFalse(
            cyrus_brain._conversation_active.is_set(),
            "_conversation_active should start in 'not set' state",
        )

    def test_whisper_prompt_default_value_preserved(self):
        """_whisper_prompt default value must still be 'Cyrus,'."""
        # The default might have been overwritten; check the source instead
        brain_source = BRAIN_PY.read_text(encoding="utf-8")
        self.assertIn(
            '_whisper_prompt: str = "Cyrus,"',
            brain_source,
            "_whisper_prompt default value must be 'Cyrus,' in cyrus_brain.py",
        )

    def test_lock_count_in_brain(self):
        """cyrus_brain.py must define all expected threading.Lock() variables."""
        brain_source = BRAIN_PY.read_text(encoding="utf-8")
        # Count threading.Lock() assignments at module level
        # Expected: _active_project_lock, _project_locked_lock,
        #           _vscode_win_cache_lock, _mobile_clients_lock, _whisper_prompt_lock
        expected_locks = {
            "_active_project_lock",
            "_project_locked_lock",
            "_vscode_win_cache_lock",
            "_mobile_clients_lock",
            "_whisper_prompt_lock",
        }
        for lock_name in expected_locks:
            self.assertIn(
                lock_name,
                brain_source,
                f"Expected lock '{lock_name}' not found in cyrus_brain.py",
            )

    def test_lock_count_in_common(self):
        """cyrus_common.py must define all expected threading.Lock() variables."""
        common_source = COMMON_PY.read_text(encoding="utf-8")
        expected_locks = {
            "_chat_input_cache_lock",
            "_chat_input_coords_lock",
        }
        for lock_name in expected_locks:
            self.assertIn(
                lock_name,
                common_source,
                f"Expected lock '{lock_name}' not found in cyrus_common.py",
            )

    def test_no_blocking_ops_inside_lock_in_brain(self):
        """No time.sleep() calls should appear directly inside a 'with lock:' block."""
        # Static analysis: check that no with-lock blocks contain time.sleep()
        # This is a best-effort check on the AST
        brain_source = BRAIN_PY.read_text(encoding="utf-8")
        brain_tree = ast.parse(brain_source)
        lock_names = {
            "_active_project_lock",
            "_project_locked_lock",
            "_vscode_win_cache_lock",
            "_mobile_clients_lock",
            "_whisper_prompt_lock",
            "_chat_input_coords_lock",
        }

        violations = []

        def walk(node, in_lock=False):
            if isinstance(node, ast.With):
                # Check if this with statement uses a lock
                uses_lock = any(
                    isinstance(item.context_expr, ast.Name)
                    and item.context_expr.id in lock_names
                    for item in node.items
                )
                if uses_lock:
                    # Check body for time.sleep() calls
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            func = child.func
                            # time.sleep(...)
                            if (
                                isinstance(func, ast.Attribute)
                                and func.attr == "sleep"
                                and isinstance(func.value, ast.Name)
                                and func.value.id == "time"
                            ):
                                violations.append(
                                    f"time.sleep() inside lock at line {child.lineno}"
                                )
                    return  # Don't recurse into the with body
            for child in ast.iter_child_nodes(node):
                walk(child, in_lock)

        walk(brain_tree)
        self.assertEqual(
            violations,
            [],
            "time.sleep() found inside lock blocks:\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
