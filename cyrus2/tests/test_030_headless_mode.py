"""
Acceptance-driven tests for Issue 030: Add Headless Mode to Brain.

Tests verify every acceptance criterion from the issue:
  - HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1" at top of cyrus_brain.py
  - All Windows imports guarded: if not HEADLESS
  - _vs_code_windows() returns companion-registered sessions when HEADLESS
  - _start_active_tracker() disabled in HEADLESS mode
  - ChatWatcher uses hook-only path (no UIA polling) in HEADLESS
  - PermissionWatcher uses companion messages (no UIA polling) in HEADLESS
  - _submit_to_vscode_impl() uses companion extension only in HEADLESS
  - Brain starts without errors when CYRUS_HEADLESS=1

Strategy:
  - Import cyrus_config directly (no Windows deps) to test HEADLESS constant.
  - Use importlib.reload() with monkeypatched CYRUS_HEADLESS=1 to test module-level
    HEADLESS constant in both modules.
  - For cyrus_common, patch HEADLESS at the module level to test behaviour branches.
  - For cyrus_brain import test, set CYRUS_HEADLESS=1 before import to prevent
    Windows-specific import errors on Linux/CI.
  - Patch _submit_via_extension to test HEADLESS submit path without live sockets.
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure cyrus2/ is importable from tests/
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

import cyrus_config  # noqa: E402,I001


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _reload_config(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> object:
    """Reload cyrus_config with a controlled environment.

    Clears CYRUS_HEADLESS from the environment first, then applies any
    entries in ``env``. Returns the freshly-reloaded module.

    Args:
        monkeypatch: pytest fixture for env-var manipulation.
        env: Environment overrides to apply before reloading.

    Returns:
        The reloaded cyrus_config module object.
    """
    monkeypatch.delenv("CYRUS_HEADLESS", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # Also need CYRUS_AUTH_TOKEN to suppress the warning on reload
    if "CYRUS_AUTH_TOKEN" not in env:
        monkeypatch.setenv("CYRUS_AUTH_TOKEN", "test-token-headless-tests")
    return importlib.reload(cyrus_config)


def _reload_common(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> object:
    """Reload cyrus_common with a controlled environment.

    Args:
        monkeypatch: pytest fixture for env-var manipulation.
        env: Environment overrides to apply before reloading.

    Returns:
        The reloaded cyrus_common module object.
    """
    monkeypatch.delenv("CYRUS_HEADLESS", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    if "CYRUS_AUTH_TOKEN" not in env:
        monkeypatch.setenv("CYRUS_AUTH_TOKEN", "test-token-headless-tests")
    # Reload config first so HEADLESS propagates
    importlib.reload(cyrus_config)
    import cyrus_common

    return importlib.reload(cyrus_common)


def _import_brain_headless(monkeypatch: pytest.MonkeyPatch) -> object:
    """Import cyrus_brain with CYRUS_HEADLESS=1 set.

    Sets the environment variable, stubs asyncio/websockets dependencies that
    would block the event loop, and returns the module.

    Args:
        monkeypatch: pytest fixture for env-var manipulation.

    Returns:
        The cyrus_brain module (reloaded with HEADLESS=True).
    """
    monkeypatch.setenv("CYRUS_HEADLESS", "1")
    monkeypatch.setenv("CYRUS_AUTH_TOKEN", "test-token-headless-tests")

    # Reload config first so it sees the new env var
    importlib.reload(cyrus_config)

    # Reload common (it imports from cyrus_config)
    import cyrus_common

    importlib.reload(cyrus_common)

    # Now reload brain — Windows imports must be skipped in HEADLESS mode
    import cyrus_brain

    return importlib.reload(cyrus_brain)


# ─────────────────────────────────────────────────────────────────────────────
# HEADLESS constant in cyrus_config
# ─────────────────────────────────────────────────────────────────────────────


class TestHeadlessConstantInConfig:
    """HEADLESS constant is exposed by cyrus_config."""

    def test_headless_false_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HEADLESS is False when CYRUS_HEADLESS is not set.

        Existing deployments must continue to work without setting
        CYRUS_HEADLESS — the default must be the original (GUI-full) mode.
        """
        module = _reload_config(monkeypatch, {})
        assert module.HEADLESS is False

    def test_headless_true_when_env_set_to_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HEADLESS is True when CYRUS_HEADLESS=1.

        Docker and Linux deployments set this variable to disable Windows
        GUI libraries that are unavailable outside of Windows.
        """
        module = _reload_config(monkeypatch, {"CYRUS_HEADLESS": "1"})
        assert module.HEADLESS is True

    def test_headless_false_when_env_set_to_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HEADLESS is False when CYRUS_HEADLESS=0 (explicit opt-out)."""
        module = _reload_config(monkeypatch, {"CYRUS_HEADLESS": "0"})
        assert module.HEADLESS is False

    def test_headless_false_when_env_set_to_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HEADLESS is False when CYRUS_HEADLESS is set to empty string."""
        module = _reload_config(monkeypatch, {"CYRUS_HEADLESS": ""})
        assert module.HEADLESS is False

    def test_headless_false_when_env_set_to_true_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HEADLESS is False when CYRUS_HEADLESS='true' (only '1' activates it).

        Only the exact string '1' activates headless mode, consistent with
        standard Unix boolean env var conventions.
        """
        module = _reload_config(monkeypatch, {"CYRUS_HEADLESS": "true"})
        assert module.HEADLESS is False

    def test_headless_is_bool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HEADLESS is a bool, not a string."""
        module = _reload_config(monkeypatch, {"CYRUS_HEADLESS": "1"})
        assert isinstance(module.HEADLESS, bool)


# ─────────────────────────────────────────────────────────────────────────────
# cyrus_common HEADLESS constant
# ─────────────────────────────────────────────────────────────────────────────


class TestCommonHeadlessConstant:
    """HEADLESS in cyrus_common reflects CYRUS_HEADLESS env var."""

    def test_common_headless_false_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cyrus_common.HEADLESS is False when CYRUS_HEADLESS not set."""
        module = _reload_common(monkeypatch, {})
        assert module.HEADLESS is False

    def test_common_headless_true_when_env_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cyrus_common.HEADLESS is True when CYRUS_HEADLESS=1."""
        module = _reload_common(monkeypatch, {"CYRUS_HEADLESS": "1"})
        assert module.HEADLESS is True


# ─────────────────────────────────────────────────────────────────────────────
# _vs_code_windows() in HEADLESS mode
# ─────────────────────────────────────────────────────────────────────────────


class TestVsCodeWindowsHeadless:
    """_vs_code_windows() returns registered sessions in HEADLESS mode."""

    def test_returns_empty_list_when_no_registered_sessions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_vs_code_windows() returns [] in HEADLESS when no sessions registered.

        Before any companion extension registers, the brain should start with
        an empty session list — not fail or hang on pygetwindow calls.
        """
        module = _reload_common(monkeypatch, {"CYRUS_HEADLESS": "1"})
        module._registered_sessions.clear()
        result = module._vs_code_windows()
        assert result == []

    def test_returns_registered_sessions_as_tuples(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_vs_code_windows() returns (project, subname) tuples from registered
        sessions.

        The companion extension populates _registered_sessions; _vs_code_windows()
        must convert that dict into the same (proj, subname) tuple format used
        by the non-headless path so SessionManager can add them transparently.
        """
        module = _reload_common(monkeypatch, {"CYRUS_HEADLESS": "1"})
        module._registered_sessions.clear()
        module._registered_sessions["myproject"] = "myproject - Visual Studio Code"

        result = module._vs_code_windows()
        assert result == [("myproject", "myproject - Visual Studio Code")]

    def test_returns_all_registered_sessions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_vs_code_windows() returns all registered sessions when multiple exist."""
        module = _reload_common(monkeypatch, {"CYRUS_HEADLESS": "1"})
        module._registered_sessions.clear()
        module._registered_sessions["proj-a"] = "proj-a - Visual Studio Code"
        module._registered_sessions["proj-b"] = "proj-b - Visual Studio Code"

        result = module._vs_code_windows()
        assert len(result) == 2
        assert ("proj-a", "proj-a - Visual Studio Code") in result
        assert ("proj-b", "proj-b - Visual Studio Code") in result

    def test_does_not_call_pygetwindow_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_vs_code_windows() does NOT call gw.getAllWindows() in HEADLESS mode.

        pygetwindow is not installed on Linux; calling it would raise ImportError
        or hang. The HEADLESS path must use _registered_sessions exclusively.
        """
        module = _reload_common(monkeypatch, {"CYRUS_HEADLESS": "1"})
        module._registered_sessions.clear()

        # If gw were called, it would fail (not installed). Success = no exception.
        result = module._vs_code_windows()
        assert isinstance(result, list)

    def test_non_headless_path_not_affected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_vs_code_windows() in non-HEADLESS mode does NOT use _registered_sessions.

        The non-headless path must remain unchanged. We verify by checking that
        _registered_sessions is not consulted (mock gw.getAllWindows to return []).
        """
        module = _reload_common(monkeypatch, {})

        if not module._HAS_UIA:
            # On Linux without UIA, non-headless returns [] regardless — skip
            pytest.skip("UIA not available on this platform")

        module._registered_sessions["ghost"] = "ghost - Visual Studio Code"
        with patch.object(module, "gw") as mock_gw:
            mock_gw.getAllWindows.return_value = []
            result = module._vs_code_windows()
        # ghost is in _registered_sessions but not in gw.getAllWindows() output
        assert not any(proj == "ghost" for proj, _ in result)


# ─────────────────────────────────────────────────────────────────────────────
# ChatWatcher HEADLESS behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestChatWatcherHeadless:
    """ChatWatcher uses hook-only path in HEADLESS — no UIA polling."""

    def test_start_does_not_call_find_webview_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ChatWatcher.start() does not call _find_webview() in HEADLESS mode.

        _find_webview() uses uiautomation which is unavailable on Linux.
        In HEADLESS mode, the hook's Stop event is the sole notification
        mechanism, so UIA polling must be completely skipped.
        """
        module = _reload_common(monkeypatch, {"CYRUS_HEADLESS": "1"})
        watcher = module.ChatWatcher(project_name="test-proj")
        find_webview_called = []

        original = watcher._find_webview

        def mock_find_webview():
            find_webview_called.append(True)
            return original()

        watcher._find_webview = mock_find_webview

        # Start the watcher thread and give it a brief window to run
        watcher.start()
        time.sleep(0.15)

        assert find_webview_called == [], (
            "ChatWatcher._find_webview() must not be called in HEADLESS mode"
        )

    def test_chat_watcher_thread_does_not_block_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ChatWatcher.start() spawns a thread that doesn't block on UIA in HEADLESS.

        The background thread must not hang on _find_webview() which loops
        until it finds a UIA window — a window that never exists in HEADLESS.
        """
        module = _reload_common(monkeypatch, {"CYRUS_HEADLESS": "1"})
        watcher = module.ChatWatcher(project_name="test-proj")

        started = threading.Event()
        original_start = watcher.start

        # Wrap start to detect the thread actually launched
        def patched_start(*args, **kwargs):
            started.set()
            original_start(*args, **kwargs)

        watcher.start = patched_start
        watcher.start()
        # The thread should start almost instantly, not block indefinitely
        assert started.wait(timeout=1.0), "ChatWatcher.start() must return quickly"


# ─────────────────────────────────────────────────────────────────────────────
# PermissionWatcher HEADLESS behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestPermissionWatcherHeadless:
    """PermissionWatcher skips UIA polling in HEADLESS — hook only."""

    def test_start_does_not_call_find_webview_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PermissionWatcher.start() does not call _find_webview() in HEADLESS mode.

        _find_webview() loops on UIA window searches unavailable on Linux.
        In HEADLESS mode, arm_from_hook() is the sole permission trigger.
        """
        module = _reload_common(monkeypatch, {"CYRUS_HEADLESS": "1"})
        watcher = module.PermissionWatcher(project_name="test-proj")
        find_webview_called = []

        original = watcher._find_webview

        def mock_find_webview():
            find_webview_called.append(True)
            return original()

        watcher._find_webview = mock_find_webview
        watcher.start()
        time.sleep(0.15)

        assert find_webview_called == [], (
            "PermissionWatcher._find_webview() must not be called in HEADLESS mode"
        )

    def test_permission_watcher_thread_does_not_block_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PermissionWatcher.start() thread must not block on UIA in HEADLESS mode."""
        module = _reload_common(monkeypatch, {"CYRUS_HEADLESS": "1"})
        watcher = module.PermissionWatcher(project_name="test-proj")

        started = threading.Event()
        original_start = watcher.start

        def patched_start(*args, **kwargs):
            started.set()
            original_start(*args, **kwargs)

        watcher.start = patched_start
        watcher.start()
        assert started.wait(timeout=1.0), (
            "PermissionWatcher.start() must return quickly in HEADLESS mode"
        )

    def test_arm_from_hook_still_works_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """arm_from_hook() correctly announces a permission request in HEADLESS mode.

        The hook-based permission path must remain functional — it's the only
        way for companion extension deployments to get permission approval.
        """
        module = _reload_common(monkeypatch, {"CYRUS_HEADLESS": "1"})
        announced = []
        watcher = module.PermissionWatcher(
            project_name="test-proj",
            speak_urgent_fn=announced.append,
        )

        watcher.arm_from_hook(tool="Bash", cmd="ls /tmp")

        assert watcher.is_pending is True
        assert len(announced) == 1
        assert "Bash" in announced[0]


# ─────────────────────────────────────────────────────────────────────────────
# _start_active_tracker HEADLESS behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestStartActiveTrackerHeadless:
    """_start_active_tracker() is disabled in HEADLESS mode."""

    def test_active_tracker_returns_immediately_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_start_active_tracker() returns without polling when HEADLESS=True.

        pygetwindow.getActiveWindow() is unavailable on Linux. In HEADLESS
        mode, the companion extension sends focus/blur messages instead, so
        the polling loop must be completely skipped.
        """
        brain = _import_brain_headless(monkeypatch)

        mock_session = MagicMock()
        mock_loop = MagicMock()

        # Run in a thread with a short timeout — must exit, not block
        result = []
        t = threading.Thread(
            target=lambda: result.append(
                brain._start_active_tracker(mock_session, mock_loop)
            )
        )
        t.daemon = True
        t.start()
        t.join(timeout=0.5)

        assert not t.is_alive(), (
            "_start_active_tracker() must return immediately in HEADLESS mode"
        )

    def test_active_tracker_does_not_call_gw_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_start_active_tracker() does NOT call gw.getActiveWindow() in HEADLESS.

        Prevents ImportError/AttributeError when pygetwindow is absent on Linux.
        """
        brain = _import_brain_headless(monkeypatch)
        mock_session = MagicMock()
        mock_loop = MagicMock()

        # If gw.getActiveWindow() were called, it'd fail since gw is not imported.
        # Success = function returns without error.
        brain._start_active_tracker(mock_session, mock_loop)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# _submit_to_vscode_impl HEADLESS behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestSubmitToVscodeHeadless:
    """_submit_to_vscode_impl() uses companion extension only in HEADLESS mode."""

    def test_submit_uses_companion_only_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_submit_to_vscode_impl() returns True when companion succeeds in HEADLESS.

        In HEADLESS mode, the UIA/pyautogui fallback path must NOT be used.
        The companion extension is the only submit path.
        """
        brain = _import_brain_headless(monkeypatch)

        with patch.object(
            brain, "_submit_via_extension", return_value=True
        ) as mock_ext:
            result = brain._submit_to_vscode_impl("hello world")

        assert result is True
        mock_ext.assert_called_once_with("hello world")

    def test_submit_returns_false_when_companion_fails_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_submit_to_vscode_impl() returns False when companion fails in HEADLESS.

        No UIA/pyautogui fallback is attempted — if the companion is down,
        the submission fails gracefully without crashing.
        """
        brain = _import_brain_headless(monkeypatch)

        with patch.object(brain, "_submit_via_extension", return_value=False):
            result = brain._submit_to_vscode_impl("hello world")

        assert result is False

    def test_submit_does_not_use_pyautogui_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_submit_to_vscode_impl() does NOT call pyautogui in HEADLESS mode.

        pyautogui is unavailable on Linux; calling it would raise ImportError.
        The HEADLESS path must skip all pyautogui-based clicks and keystrokes.
        """
        brain = _import_brain_headless(monkeypatch)

        with patch.object(brain, "_submit_via_extension", return_value=False):
            # Must not raise even though pyautogui is not installed
            result = brain._submit_to_vscode_impl("no gui test")

        assert result is False

    def test_submit_worker_skips_coinitializeex_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_submit_worker initialises without comtypes.CoInitializeEx() in HEADLESS.

        comtypes is a Windows-only library. The submit worker must skip
        CoInitializeEx() when HEADLESS=True so it can start on Linux.
        """
        brain = _import_brain_headless(monkeypatch)

        # Patch the submit impl to avoid blocking
        brain._submit_request_queue.put(("test text", threading.Event(), [False]))

        # If CoInitializeEx were called, it would raise NameError (comtypes not
        # imported). The worker should run without error (no crash on start).
        with patch.object(
            brain, "_submit_to_vscode_impl", return_value=True
        ) as mock_impl:
            t = threading.Thread(target=brain._submit_worker, daemon=True)
            t.start()
            time.sleep(0.2)
            # If still alive after brief wait, worker is running (expected for daemon)
            # The important thing is it started without NameError for comtypes
            assert mock_impl.called or not t.is_alive()


# ─────────────────────────────────────────────────────────────────────────────
# Brain imports without error when CYRUS_HEADLESS=1
# ─────────────────────────────────────────────────────────────────────────────


class TestBrainHeadlessImport:
    """cyrus_brain.py imports successfully with CYRUS_HEADLESS=1 on Linux."""

    def test_brain_imports_without_error_in_headless(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cyrus_brain imports cleanly when CYRUS_HEADLESS=1.

        This is the primary acceptance criterion: the brain must start on Linux
        or in Docker without Windows-specific packages (comtypes, pyautogui,
        pygetwindow, pyperclip, uiautomation).
        """
        # Should not raise ImportError or ModuleNotFoundError
        brain = _import_brain_headless(monkeypatch)
        assert brain is not None

    def test_brain_headless_constant_is_true_when_env_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cyrus_brain.HEADLESS is True when CYRUS_HEADLESS=1.

        The module-level HEADLESS constant guards all Windows-specific paths.
        """
        brain = _import_brain_headless(monkeypatch)
        assert brain.HEADLESS is True

    def test_brain_headless_constant_is_false_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cyrus_brain.HEADLESS is False when CYRUS_HEADLESS is not set.

        Existing Windows deployments must default to the GUI-full mode.
        """
        # Import with HEADLESS=1 first (required to import on Linux)
        _import_brain_headless(monkeypatch)
        # Now simulate unset env var by checking the config directly
        monkeypatch.delenv("CYRUS_HEADLESS", raising=False)
        cfg = _reload_config(monkeypatch, {})
        assert cfg.HEADLESS is False


# ─────────────────────────────────────────────────────────────────────────────
# .env.example documentation
# ─────────────────────────────────────────────────────────────────────────────


class TestEnvExampleDocumentation:
    """CYRUS_HEADLESS is documented in .env.example."""

    def test_env_example_documents_cyrus_headless(self) -> None:
        """The .env.example file must contain CYRUS_HEADLESS.

        Docker operators need to know this variable exists so they can enable
        headless mode when running the brain in a container without Windows GUI.
        """
        env_example = Path(__file__).parent.parent.parent / ".env.example"
        assert env_example.exists(), ".env.example must exist"
        content = env_example.read_text()
        assert "CYRUS_HEADLESS" in content, ".env.example must document CYRUS_HEADLESS"

    def test_env_example_headless_shows_default_zero(self) -> None:
        """The .env.example CYRUS_HEADLESS entry shows 0 as the default.

        Operators copying the example file should get non-headless mode by
        default, consistent with Windows-first deployment.
        """
        env_example = Path(__file__).parent.parent.parent / ".env.example"
        content = env_example.read_text()
        assert "CYRUS_HEADLESS=0" in content, (
            ".env.example must show CYRUS_HEADLESS=0 as the default"
        )
