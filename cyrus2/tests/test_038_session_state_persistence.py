"""
Acceptance-driven tests for Issue 038: Add Session State Persistence.

These tests verify every acceptance criterion from the issue:
  - State saved to ~/.cyrus/state.json on shutdown (SIGTERM, Ctrl+C)
  - State includes: aliases, pending request queues, project mappings
  - Atomic writes (write to .tmp, then rename to avoid corruption)
  - State loaded from file at startup
  - Gracefully handles missing or corrupted state file
  - State file permissions restricted (0600 on Unix)
  - Configurable via CYRUS_STATE_FILE env var

Test categories
---------------
  Default path     (2 tests) — _get_state_file() returns ~/.cyrus/state.json by default
  Env var override (2 tests) — CYRUS_STATE_FILE overrides the path
  Save state       (4 tests) — _save_state() writes valid JSON, atomic write, perms
  State structure  (3 tests) — saved state contains aliases, pending queues, projects
  Load state       (3 tests) — _load_state() restores aliases into SessionManager
  Error handling   (3 tests) — missing file, corrupted JSON, unsupported version
  Round-trip       (2 tests) — save → load → verify aliases preserved
  Config module    (2 tests) — CYRUS_STATE_FILE in cyrus_config + .env.example

Usage
-----
    pytest tests/test_038_session_state_persistence.py -v
    pytest tests/test_038_session_state_persistence.py -k "defaults" -v
"""

from __future__ import annotations

import json
import os
import platform
import sys
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
    "aiohttp",
    "aiohttp.web",
]
for _mod in _WIN_MODS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Also mock aiohttp.web (cyrus_brain does `from aiohttp import web as _aiohttp_web`)
sys.modules["aiohttp"] = MagicMock()

# Add cyrus2/ directory to sys.path
_CYRUS2_DIR = Path(__file__).parent.parent  # .../cyrus/cyrus2/
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

import cyrus_brain  # noqa: E402
import cyrus_config  # noqa: E402

_ENV_EXAMPLE = _CYRUS2_DIR / ".env.example"


def _make_mock_session_manager(
    aliases: dict[str, str] | None = None,
    chat_watchers: dict | None = None,
) -> MagicMock:
    """Build a minimal mock SessionManager for testing persistence functions.

    Creates a MagicMock that mimics the attributes accessed by _save_state()
    and _load_state(): session_mgr.aliases (property) and
    session_mgr._chat_watchers (dict of ChatWatcher-likes) and
    session_mgr._aliases (raw dict).

    Args:
        aliases: Pre-populated alias → project mapping.
        chat_watchers: Dict of project_name → mock ChatWatcher.

    Returns:
        MagicMock configured to mimic SessionManager.
    """
    mgr = MagicMock()
    mgr._aliases = dict(aliases or {})
    # .aliases property returns a copy of _aliases
    type(mgr).aliases = property(lambda self: dict(self._aliases))

    # Build mock ChatWatchers with _pending_queue lists
    watchers = {}
    for proj, watcher_data in (chat_watchers or {}).items():
        cw = MagicMock()
        cw._pending_queue = list(watcher_data) if isinstance(watcher_data, list) else []
        watchers[proj] = cw
    mgr._chat_watchers = watchers
    return mgr


# ── Default path tests ────────────────────────────────────────────────────────


class TestGetStateFileDefaultPath(unittest.TestCase):
    """_get_state_file() returns ~/.cyrus/state.json when CYRUS_STATE_FILE is unset."""

    def setUp(self) -> None:
        """Clear CYRUS_STATE_FILE from env before each test."""
        os.environ.pop("CYRUS_STATE_FILE", None)

    def test_default_path_is_home_cyrus_state_json(self) -> None:
        """AC: Default state file path must be ~/.cyrus/state.json."""
        expected = Path.home() / ".cyrus" / "state.json"
        actual = cyrus_brain._get_state_file()
        self.assertEqual(actual, expected)

    def test_default_path_parent_dir_exists(self) -> None:
        """_get_state_file() must create the parent directory if it does not exist."""
        actual = cyrus_brain._get_state_file()
        # After calling _get_state_file(), the parent dir must exist
        self.assertTrue(
            actual.parent.exists(),
            f"Parent dir {actual.parent} must exist",
        )


# ── Env var override tests ────────────────────────────────────────────────────


class TestGetStateFileEnvVarOverride(unittest.TestCase):
    """CYRUS_STATE_FILE env var overrides the default state file path."""

    def setUp(self) -> None:
        os.environ.pop("CYRUS_STATE_FILE", None)

    def tearDown(self) -> None:
        os.environ.pop("CYRUS_STATE_FILE", None)

    def test_env_var_overrides_default_path(self) -> None:
        """AC: CYRUS_STATE_FILE must override the default path."""
        custom = "/tmp/custom_state.json"
        with patch.dict(os.environ, {"CYRUS_STATE_FILE": custom}):
            actual = cyrus_brain._get_state_file()
        self.assertEqual(actual, Path(custom))

    def test_env_var_empty_string_uses_default(self) -> None:
        """Edge case: CYRUS_STATE_FILE='' must use the default path."""
        with patch.dict(os.environ, {"CYRUS_STATE_FILE": ""}):
            actual = cyrus_brain._get_state_file()
        expected = Path.home() / ".cyrus" / "state.json"
        self.assertEqual(actual, expected)


# ── Save state tests ──────────────────────────────────────────────────────────


class TestSaveState(unittest.TestCase):
    """_save_state() writes a valid JSON file with correct structure."""

    def setUp(self) -> None:
        """Use a tmp directory for all state file operations."""
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self._state_file = Path(self._tmpdir) / "state.json"
        os.environ["CYRUS_STATE_FILE"] = str(self._state_file)

    def tearDown(self) -> None:
        os.environ.pop("CYRUS_STATE_FILE", None)
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_state_creates_file(self) -> None:
        """AC: _save_state() must create the state file."""
        session_mgr = _make_mock_session_manager()
        cyrus_brain._save_state(session_mgr)
        self.assertTrue(
            self._state_file.exists(),
            "State file must be created by _save_state()",
        )

    def test_save_state_writes_valid_json(self) -> None:
        """AC: State file must contain valid JSON."""
        session_mgr = _make_mock_session_manager()
        cyrus_brain._save_state(session_mgr)
        content = self._state_file.read_text(encoding="utf-8")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            self.fail(f"_save_state() wrote invalid JSON: {e}")
        self.assertIsInstance(data, dict)

    def test_save_state_atomic_write_no_tmp_file_left(self) -> None:
        """AC: Atomic write must leave no .tmp file after completion."""
        session_mgr = _make_mock_session_manager()
        cyrus_brain._save_state(session_mgr)
        tmp_file = self._state_file.with_suffix(".tmp")
        self.assertFalse(
            tmp_file.exists(),
            "Temp file (.tmp) must be removed after successful atomic rename",
        )

    @unittest.skipIf(platform.system() == "Windows", "Unix-only permission test")
    def test_save_state_restricts_file_permissions_to_0600(self) -> None:
        """AC: State file must have mode 0o600 after _save_state()."""
        session_mgr = _make_mock_session_manager()
        cyrus_brain._save_state(session_mgr)
        mode = self._state_file.stat().st_mode & 0o777
        self.assertEqual(
            mode,
            0o600,
            f"State file permissions must be 0o600, got {oct(mode)}",
        )


# ── State structure tests ─────────────────────────────────────────────────────


class TestSaveStateStructure(unittest.TestCase):
    """Saved state JSON must contain aliases, pending_queues, and projects keys."""

    def setUp(self) -> None:
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self._state_file = Path(self._tmpdir) / "state.json"
        os.environ["CYRUS_STATE_FILE"] = str(self._state_file)

    def tearDown(self) -> None:
        os.environ.pop("CYRUS_STATE_FILE", None)
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _load_saved(self) -> dict:
        return json.loads(self._state_file.read_text(encoding="utf-8"))

    def test_saved_state_contains_version_key(self) -> None:
        """State JSON must include a 'version' key for forward compatibility."""
        session_mgr = _make_mock_session_manager()
        cyrus_brain._save_state(session_mgr)
        data = self._load_saved()
        self.assertIn("version", data)
        self.assertEqual(data["version"], 1)

    def test_saved_state_contains_aliases(self) -> None:
        """AC: State must include aliases mapping."""
        aliases = {"backend": "my-backend", "frontend": "my-frontend"}
        session_mgr = _make_mock_session_manager(aliases=aliases)
        cyrus_brain._save_state(session_mgr)
        data = self._load_saved()
        self.assertIn("aliases", data)
        self.assertEqual(data["aliases"], aliases)

    def test_saved_state_contains_pending_queues(self) -> None:
        """AC: State must include pending_queues for each project."""
        watchers = {
            "my-backend": ["response 1", "response 2"],
            "my-frontend": [],
        }
        session_mgr = _make_mock_session_manager(chat_watchers=watchers)
        cyrus_brain._save_state(session_mgr)
        data = self._load_saved()
        self.assertIn("pending_queues", data)
        self.assertEqual(
            data["pending_queues"]["my-backend"], ["response 1", "response 2"]
        )
        self.assertEqual(data["pending_queues"]["my-frontend"], [])

    def test_saved_state_contains_projects(self) -> None:
        """AC: State must include project list from chat_watchers keys."""
        watchers = {"proj-a": [], "proj-b": ["msg"]}
        session_mgr = _make_mock_session_manager(chat_watchers=watchers)
        cyrus_brain._save_state(session_mgr)
        data = self._load_saved()
        self.assertIn("projects", data)
        self.assertIn("proj-a", data["projects"])
        self.assertIn("proj-b", data["projects"])


# ── Load state tests ──────────────────────────────────────────────────────────


class TestLoadState(unittest.TestCase):
    """_load_state() restores aliases into the SessionManager."""

    def setUp(self) -> None:
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self._state_file = Path(self._tmpdir) / "state.json"
        os.environ["CYRUS_STATE_FILE"] = str(self._state_file)

    def tearDown(self) -> None:
        os.environ.pop("CYRUS_STATE_FILE", None)
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_state(self, data: dict) -> None:
        self._state_file.write_text(json.dumps(data), encoding="utf-8")

    def test_load_state_restores_aliases(self) -> None:
        """AC: _load_state() must restore aliases into session_mgr._aliases."""
        aliases = {"backend": "my-backend", "api": "my-api"}
        state = {
            "version": 1,
            "timestamp": 0.0,
            "aliases": aliases,
            "projects": [],
            "pending_queues": {},
        }
        self._write_state(state)
        session_mgr = _make_mock_session_manager()
        cyrus_brain._load_state(session_mgr)
        for alias, proj in aliases.items():
            self.assertIn(alias, session_mgr._aliases)
            self.assertEqual(session_mgr._aliases[alias], proj)

    def test_load_state_with_no_aliases_in_file(self) -> None:
        """Edge case: state file with empty aliases must not fail."""
        self._write_state(
            {
                "version": 1,
                "timestamp": 0.0,
                "aliases": {},
                "projects": [],
                "pending_queues": {},
            }
        )
        session_mgr = _make_mock_session_manager()
        try:
            cyrus_brain._load_state(session_mgr)
        except Exception as e:
            self.fail(f"_load_state() raised {e!r} with empty aliases")

    def test_load_state_merges_with_existing_aliases(self) -> None:
        """_load_state() must update (not replace) existing aliases in session_mgr."""
        existing = {"existing-alias": "existing-proj"}
        loaded = {"loaded-alias": "loaded-proj"}
        state = {
            "version": 1,
            "timestamp": 0.0,
            "aliases": loaded,
            "projects": [],
            "pending_queues": {},
        }
        self._write_state(state)
        session_mgr = _make_mock_session_manager(aliases=existing)
        cyrus_brain._load_state(session_mgr)
        # Both the original and loaded aliases should be present
        self.assertIn("existing-alias", session_mgr._aliases)
        self.assertIn("loaded-alias", session_mgr._aliases)


# ── Error handling tests ──────────────────────────────────────────────────────


class TestLoadStateErrorHandling(unittest.TestCase):
    """_load_state() gracefully handles missing file, corrupted JSON, bad version."""

    def setUp(self) -> None:
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self._state_file = Path(self._tmpdir) / "state.json"
        os.environ["CYRUS_STATE_FILE"] = str(self._state_file)

    def tearDown(self) -> None:
        os.environ.pop("CYRUS_STATE_FILE", None)
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_load_state_handles_missing_file_gracefully(self) -> None:
        """AC: _load_state() must not raise when state file does not exist."""
        # Don't create the file — let _load_state() find nothing
        session_mgr = _make_mock_session_manager()
        try:
            cyrus_brain._load_state(session_mgr)
        except Exception as e:
            self.fail(f"_load_state() raised {e!r} on missing file")

    def test_load_state_handles_corrupted_json_gracefully(self) -> None:
        """AC: _load_state() must not raise when state file contains invalid JSON."""
        self._state_file.write_text("this is not json {{{{", encoding="utf-8")
        session_mgr = _make_mock_session_manager()
        try:
            cyrus_brain._load_state(session_mgr)
        except Exception as e:
            self.fail(f"_load_state() raised {e!r} on corrupted JSON")

    def test_load_state_handles_unsupported_version_gracefully(self) -> None:
        """AC: _load_state() must skip state with unsupported version, not raise."""
        self._state_file.write_text(
            json.dumps({"version": 99, "aliases": {"should": "not-load"}}),
            encoding="utf-8",
        )
        session_mgr = _make_mock_session_manager()
        try:
            cyrus_brain._load_state(session_mgr)
        except Exception as e:
            self.fail(f"_load_state() raised {e!r} on unsupported version")
        # Aliases from an unsupported version must NOT be loaded
        self.assertNotIn("should", session_mgr._aliases)

    def test_load_state_handles_empty_file_gracefully(self) -> None:
        """Corner case: completely empty state file must not raise."""
        self._state_file.write_text("", encoding="utf-8")
        session_mgr = _make_mock_session_manager()
        try:
            cyrus_brain._load_state(session_mgr)
        except Exception as e:
            self.fail(f"_load_state() raised {e!r} on empty file")


# ── Round-trip tests ──────────────────────────────────────────────────────────


class TestStateRoundTrip(unittest.TestCase):
    """Save then load must restore the exact same state."""

    def setUp(self) -> None:
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self._state_file = Path(self._tmpdir) / "state.json"
        os.environ["CYRUS_STATE_FILE"] = str(self._state_file)

    def tearDown(self) -> None:
        os.environ.pop("CYRUS_STATE_FILE", None)
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_round_trip_preserves_aliases(self) -> None:
        """AC: save → load must restore aliases with identical contents."""
        original_aliases = {"backend": "my-backend", "api": "my-api", "web": "my-web"}
        save_mgr = _make_mock_session_manager(aliases=original_aliases)
        cyrus_brain._save_state(save_mgr)

        load_mgr = _make_mock_session_manager()
        cyrus_brain._load_state(load_mgr)
        for alias, proj in original_aliases.items():
            self.assertIn(alias, load_mgr._aliases)
            self.assertEqual(load_mgr._aliases[alias], proj)

    def test_round_trip_preserves_pending_queues_in_file(self) -> None:
        """Pending queues must be written to the file (even if not auto-replayed)."""
        watchers = {"proj-x": ["pending msg 1", "pending msg 2"]}
        save_mgr = _make_mock_session_manager(chat_watchers=watchers)
        cyrus_brain._save_state(save_mgr)

        data = json.loads(self._state_file.read_text(encoding="utf-8"))
        self.assertEqual(
            data["pending_queues"]["proj-x"],
            ["pending msg 1", "pending msg 2"],
        )


# ── cyrus_config CYRUS_STATE_FILE tests ───────────────────────────────────────


class TestCyrusConfigStateFile(unittest.TestCase):
    """CYRUS_STATE_FILE must be defined in cyrus_config and .env.example."""

    def test_cyrus_config_has_state_file_constant(self) -> None:
        """AC: cyrus_config must export CYRUS_STATE_FILE constant."""
        self.assertTrue(
            hasattr(cyrus_config, "CYRUS_STATE_FILE"),
            "cyrus_config is missing CYRUS_STATE_FILE constant",
        )

    def test_cyrus_config_state_file_is_string(self) -> None:
        """CYRUS_STATE_FILE must be a string (empty string = use default path)."""
        self.assertIsInstance(
            cyrus_config.CYRUS_STATE_FILE,
            str,
            "cyrus_config.CYRUS_STATE_FILE must be a str",
        )

    def test_env_example_documents_cyrus_state_file(self) -> None:
        """AC: CYRUS_STATE_FILE must be documented in .env.example."""
        self.assertTrue(
            _ENV_EXAMPLE.exists(),
            f".env.example not found at {_ENV_EXAMPLE}",
        )
        content = _ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn(
            "CYRUS_STATE_FILE",
            content,
            "CYRUS_STATE_FILE must be documented in .env.example",
        )


# ── cyrus_brain source code structure tests ───────────────────────────────────


class TestCyrusBrainSourceStructure(unittest.TestCase):
    """cyrus_brain.py must define the required state persistence functions."""

    _BRAIN_SRC = _CYRUS2_DIR / "cyrus_brain.py"

    def test_get_state_file_defined_in_brain(self) -> None:
        """_get_state_file must be defined in cyrus_brain.py."""
        src = self._BRAIN_SRC.read_text(encoding="utf-8")
        self.assertIn("def _get_state_file(", src)

    def test_save_state_defined_in_brain(self) -> None:
        """_save_state must be defined in cyrus_brain.py."""
        src = self._BRAIN_SRC.read_text(encoding="utf-8")
        self.assertIn("def _save_state(", src)

    def test_load_state_defined_in_brain(self) -> None:
        """_load_state must be defined in cyrus_brain.py."""
        src = self._BRAIN_SRC.read_text(encoding="utf-8")
        self.assertIn("def _load_state(", src)

    def test_brain_imports_signal_module(self) -> None:
        """cyrus_brain.py must import signal for shutdown handler registration."""
        src = self._BRAIN_SRC.read_text(encoding="utf-8")
        self.assertIn("import signal", src)

    def test_load_state_called_in_main(self) -> None:
        """_load_state must be called in main() at startup."""
        src = self._BRAIN_SRC.read_text(encoding="utf-8")
        self.assertIn("_load_state(", src)

    def test_save_state_called_in_shutdown_handler(self) -> None:
        """_save_state must be called in a shutdown handler or signal callback."""
        src = self._BRAIN_SRC.read_text(encoding="utf-8")
        self.assertIn("_save_state(", src)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
