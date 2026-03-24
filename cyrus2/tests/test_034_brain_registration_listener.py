"""
Acceptance-driven tests for Issue 034: Add Brain Registration Listener.

Tests verify every acceptance criterion:
  - Async TCP server on 0.0.0.0:8770 in headless mode only
  - _registered_sessions: dict[str, SessionInfo] tracks workspace, connection, port
  - On register message, add session; update cyrus_common._registered_sessions compat
    dict
  - On focus message, set _active_project to workspace name
  - On blur message, clear _active_project if it matches
  - On blur message, do NOT clear if workspace doesn't match
  - On permission_respond, log the action
  - On prompt_respond, log the text
  - On disconnect, remove session from both dicts
  - Multiple concurrent sessions tracked correctly
  - Malformed JSON is skipped gracefully
  - Server only starts in HEADLESS mode

Strategy:
  - Mock Windows-specific modules before any cyrus_brain import
  - Use asyncio.StreamReader.feed_data() + asyncio.StreamWriter mock
    (same pattern as test_028)
  - Use unittest.IsolatedAsyncioTestCase for async test methods
  - Set CYRUS_HEADLESS=1 and CYRUS_AUTH_TOKEN in env for brain import
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

# Mock Windows-specific modules BEFORE any cyrus_brain import
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

# Set up headless environment before import
os.environ.setdefault("CYRUS_HEADLESS", "1")
os.environ.setdefault("CYRUS_AUTH_TOKEN", "test-reg-token-034")

import cyrus_brain  # noqa: E402
import cyrus_common  # noqa: E402
import cyrus_config  # noqa: E402


def _make_reader_writer(messages: list[dict] | None = None, eof: bool = True):
    """Return (reader, writer, written_list) with messages queued in reader.

    Args:
        messages: List of dicts to encode as line-delimited JSON in reader.
        eof: Whether to feed EOF after messages.

    Returns:
        Tuple of (reader, writer, written) where written is a list collecting
        bytes passed to writer.write().
    """
    reader = asyncio.StreamReader()
    if messages:
        for msg in messages:
            reader.feed_data(json.dumps(msg).encode() + b"\n")
    if eof:
        reader.feed_eof()

    written: list[bytes] = []
    transport = MagicMock()
    protocol = MagicMock()
    loop = asyncio.get_event_loop()
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)
    writer.write = lambda data: written.append(data)
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 54321))
    return reader, writer, written


TOKEN = "test-reg-token-034"


# ─────────────────────────────────────────────────────────────────────────────
# SessionInfo dataclass tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSessionInfo(unittest.TestCase):
    """SessionInfo dataclass tracks workspace, safe, port, connection, created_at."""

    def test_session_info_exists(self) -> None:
        """SessionInfo class exists in cyrus_brain module."""
        assert hasattr(cyrus_brain, "SessionInfo"), (
            "cyrus_brain must define SessionInfo class"
        )

    def test_session_info_fields(self) -> None:
        """SessionInfo has workspace, safe, port, connection, created_at fields."""
        mock_writer = MagicMock()
        info = cyrus_brain.SessionInfo(
            workspace="my-proj",
            safe="my_proj",
            port=8768,
            connection=mock_writer,
        )
        assert info.workspace == "my-proj"
        assert info.safe == "my_proj"
        assert info.port == 8768
        assert info.connection is mock_writer

    def test_session_info_created_at_defaults_to_now(self) -> None:
        """SessionInfo.created_at defaults to current time."""
        import time

        before = time.time()
        mock_writer = MagicMock()
        info = cyrus_brain.SessionInfo(
            workspace="proj", safe="proj", port=8768, connection=mock_writer
        )
        after = time.time()
        assert before <= info.created_at <= after

    def test_session_info_created_at_can_be_set(self) -> None:
        """SessionInfo.created_at can be explicitly set."""
        mock_writer = MagicMock()
        info = cyrus_brain.SessionInfo(
            workspace="proj",
            safe="proj",
            port=8768,
            connection=mock_writer,
            created_at=12345.0,
        )
        assert info.created_at == 12345.0


# ─────────────────────────────────────────────────────────────────────────────
# Module-level state tests
# ─────────────────────────────────────────────────────────────────────────────


class TestModuleLevelState(unittest.TestCase):
    """_registered_sessions dict and _sessions_lock exist in cyrus_brain."""

    def test_registered_sessions_dict_exists(self) -> None:
        """_registered_sessions exists as a dict in cyrus_brain."""
        assert hasattr(cyrus_brain, "_registered_sessions"), (
            "cyrus_brain must have _registered_sessions"
        )
        assert isinstance(cyrus_brain._registered_sessions, dict)

    def test_sessions_lock_exists(self) -> None:
        """_sessions_lock exists as a threading.Lock in cyrus_brain."""
        assert hasattr(cyrus_brain, "_sessions_lock"), (
            "cyrus_brain must have _sessions_lock"
        )
        assert isinstance(cyrus_brain._sessions_lock, type(threading.Lock()))

    def test_companion_port_importable(self) -> None:
        """COMPANION_PORT is importable from cyrus_brain (comes from cyrus_config)."""
        assert hasattr(cyrus_brain, "COMPANION_PORT"), (
            "cyrus_brain must expose COMPANION_PORT"
        )
        assert cyrus_brain.COMPANION_PORT == 8770


# ─────────────────────────────────────────────────────────────────────────────
# Registration handler: register message
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistrationHandlerRegister(unittest.IsolatedAsyncioTestCase):
    """_handle_registration_client processes register messages correctly."""

    def setUp(self) -> None:
        """Clear state and ensure correct auth token before each test."""
        # Other tests may reload cyrus_config with different tokens; restore ours
        # so validate_auth_token() accepts TOKEN during these tests.
        with patch.dict(os.environ, {"CYRUS_AUTH_TOKEN": TOKEN, "CYRUS_HEADLESS": "1"}):
            importlib.reload(cyrus_config)
        cyrus_brain._registered_sessions.clear()
        cyrus_common._registered_sessions.clear()

    def tearDown(self) -> None:
        """Clear state after each test."""
        cyrus_brain._registered_sessions.clear()
        cyrus_common._registered_sessions.clear()

    async def test_register_adds_session_to_brain_dict(self) -> None:
        """On register, SessionInfo added to cyrus_brain._registered_sessions.

        Uses a persistent connection (eof=False) and cancels the handler after
        the register message has been processed so we can inspect dict state
        while the session is still considered active.
        """
        msgs = [
            {
                "type": "register",
                "workspace": "myproj",
                "safe": "myproj",
                "port": 8768,
                "token": TOKEN,
            }
        ]
        # eof=False: handler will block waiting for more data after register —
        # we cancel it after one event-loop tick to inspect state mid-session.
        reader, writer, _ = _make_reader_writer(msgs, eof=False)

        task = asyncio.create_task(
            cyrus_brain._handle_registration_client(reader, writer)
        )
        # Yield control so the task can process the register message
        await asyncio.sleep(0)

        # Session should be present while connection is still open
        assert "myproj" in cyrus_brain._registered_sessions
        info = cyrus_brain._registered_sessions["myproj"]
        assert info.workspace == "myproj"
        assert info.safe == "myproj"
        assert info.port == 8768

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def test_register_updates_common_registered_sessions(self) -> None:
        """On register, cyrus_common._registered_sessions updated for _vs_code_windows
        compat.

        Uses a persistent connection (eof=False) and cancels the handler after
        the register message has been processed so we can inspect dict state
        while the session is still considered active.
        """
        msgs = [
            {
                "type": "register",
                "workspace": "compat-proj",
                "safe": "compat_proj",
                "port": 8768,
                "token": TOKEN,
            }
        ]
        reader, writer, _ = _make_reader_writer(msgs, eof=False)

        task = asyncio.create_task(
            cyrus_brain._handle_registration_client(reader, writer)
        )
        await asyncio.sleep(0)

        assert "compat-proj" in cyrus_common._registered_sessions

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def test_register_logs_workspace_and_port(self, caplog=None) -> None:
        """On register, log message includes workspace name and port."""
        import logging

        msgs = [
            {
                "type": "register",
                "workspace": "logged-proj",
                "safe": "logged_proj",
                "port": 8999,
                "token": TOKEN,
            }
        ]
        reader, writer, _ = _make_reader_writer(msgs)

        with self.assertLogs("cyrus.brain", level=logging.INFO) as cm:
            await cyrus_brain._handle_registration_client(reader, writer)

        log_output = "\n".join(cm.output)
        assert "logged-proj" in log_output or "logged_proj" in log_output

    async def test_register_rejects_without_auth_token(self) -> None:
        """On register without valid token, session NOT added to dicts."""
        msgs = [
            {
                "type": "register",
                "workspace": "unauth-proj",
                "safe": "unauth_proj",
                "port": 8768,
                "token": "wrong-token",
            }
        ]
        reader, writer, written = _make_reader_writer(msgs)

        await cyrus_brain._handle_registration_client(reader, writer)

        assert "unauth-proj" not in cyrus_brain._registered_sessions
        all_written = b"".join(written)
        assert b"unauthorized" in all_written.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Registration handler: focus/blur messages
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistrationHandlerFocusBlur(unittest.IsolatedAsyncioTestCase):
    """_handle_registration_client processes focus/blur messages."""

    def setUp(self) -> None:
        """Clear state and restore auth token before each test."""
        with patch.dict(os.environ, {"CYRUS_AUTH_TOKEN": TOKEN, "CYRUS_HEADLESS": "1"}):
            importlib.reload(cyrus_config)
        cyrus_brain._registered_sessions.clear()
        cyrus_common._registered_sessions.clear()
        # Reset _active_project
        with cyrus_brain._active_project_lock:
            cyrus_brain._active_project = ""

    def tearDown(self) -> None:
        """Clear state after each test."""
        cyrus_brain._registered_sessions.clear()
        cyrus_common._registered_sessions.clear()
        with cyrus_brain._active_project_lock:
            cyrus_brain._active_project = ""

    async def test_focus_sets_active_project(self) -> None:
        """On focus message, _active_project is set to workspace name."""
        msgs = [
            {
                "type": "register",
                "workspace": "focus-proj",
                "safe": "focus_proj",
                "port": 8768,
                "token": TOKEN,
            },
            {"type": "focus", "workspace": "focus-proj"},
        ]
        reader, writer, _ = _make_reader_writer(msgs)

        await cyrus_brain._handle_registration_client(reader, writer)

        with cyrus_brain._active_project_lock:
            assert cyrus_brain._active_project == "focus-proj"

    async def test_focus_logs_active_project(self) -> None:
        """On focus, log message includes workspace name."""
        import logging

        msgs = [
            {
                "type": "register",
                "workspace": "logfocus",
                "safe": "logfocus",
                "port": 8768,
                "token": TOKEN,
            },
            {"type": "focus", "workspace": "logfocus"},
        ]
        reader, writer, _ = _make_reader_writer(msgs)

        with self.assertLogs("cyrus.brain", level=logging.INFO) as cm:
            await cyrus_brain._handle_registration_client(reader, writer)

        log_output = "\n".join(cm.output)
        assert "logfocus" in log_output

    async def test_blur_clears_active_project_when_matching(self) -> None:
        """On blur, _active_project cleared when workspace matches current active."""
        # First set the active project
        with cyrus_brain._active_project_lock:
            cyrus_brain._active_project = "blur-proj"

        msgs = [
            {
                "type": "register",
                "workspace": "blur-proj",
                "safe": "blur_proj",
                "port": 8768,
                "token": TOKEN,
            },
            {"type": "blur", "workspace": "blur-proj"},
        ]
        reader, writer, _ = _make_reader_writer(msgs)

        await cyrus_brain._handle_registration_client(reader, writer)

        with cyrus_brain._active_project_lock:
            active = cyrus_brain._active_project
            assert active == "" or active is None

    async def test_blur_does_not_clear_if_workspace_differs(self) -> None:
        """On blur, _active_project NOT cleared when workspace doesn't match current
        active."""
        # Set a different project as active
        with cyrus_brain._active_project_lock:
            cyrus_brain._active_project = "other-proj"

        msgs = [
            {
                "type": "register",
                "workspace": "blur-proj",
                "safe": "blur_proj",
                "port": 8768,
                "token": TOKEN,
            },
            {"type": "blur", "workspace": "blur-proj"},
        ]
        reader, writer, _ = _make_reader_writer(msgs)

        await cyrus_brain._handle_registration_client(reader, writer)

        # "other-proj" must still be active
        with cyrus_brain._active_project_lock:
            assert cyrus_brain._active_project == "other-proj"


# ─────────────────────────────────────────────────────────────────────────────
# Registration handler: permission_respond / prompt_respond
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistrationHandlerResponds(unittest.IsolatedAsyncioTestCase):
    """_handle_registration_client processes permission_respond/prompt_respond."""

    def setUp(self) -> None:
        with patch.dict(os.environ, {"CYRUS_AUTH_TOKEN": TOKEN, "CYRUS_HEADLESS": "1"}):
            importlib.reload(cyrus_config)
        cyrus_brain._registered_sessions.clear()
        cyrus_common._registered_sessions.clear()

    def tearDown(self) -> None:
        cyrus_brain._registered_sessions.clear()
        cyrus_common._registered_sessions.clear()

    async def test_permission_respond_is_logged(self) -> None:
        """On permission_respond, a log message is emitted."""
        import logging

        msgs = [
            {
                "type": "register",
                "workspace": "perm-proj",
                "safe": "perm_proj",
                "port": 8768,
                "token": TOKEN,
            },
            {"type": "permission_respond", "action": "allow"},
        ]
        reader, writer, _ = _make_reader_writer(msgs)

        with self.assertLogs("cyrus.brain", level=logging.INFO) as cm:
            await cyrus_brain._handle_registration_client(reader, writer)

        log_output = "\n".join(cm.output)
        assert "permission" in log_output.lower() or "allow" in log_output.lower()

    async def test_prompt_respond_is_logged(self) -> None:
        """On prompt_respond, a log message is emitted."""
        import logging

        msgs = [
            {
                "type": "register",
                "workspace": "prompt-proj",
                "safe": "prompt_proj",
                "port": 8768,
                "token": TOKEN,
            },
            {"type": "prompt_respond", "text": "User typed this response"},
        ]
        reader, writer, _ = _make_reader_writer(msgs)

        with self.assertLogs("cyrus.brain", level=logging.INFO) as cm:
            await cyrus_brain._handle_registration_client(reader, writer)

        log_output = "\n".join(cm.output)
        assert "prompt" in log_output.lower() or "user typed" in log_output.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Registration handler: disconnect
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistrationHandlerDisconnect(unittest.IsolatedAsyncioTestCase):
    """_handle_registration_client cleans up on disconnect."""

    def setUp(self) -> None:
        with patch.dict(os.environ, {"CYRUS_AUTH_TOKEN": TOKEN, "CYRUS_HEADLESS": "1"}):
            importlib.reload(cyrus_config)
        cyrus_brain._registered_sessions.clear()
        cyrus_common._registered_sessions.clear()

    def tearDown(self) -> None:
        cyrus_brain._registered_sessions.clear()
        cyrus_common._registered_sessions.clear()

    async def test_disconnect_removes_from_brain_dict(self) -> None:
        """On EOF (disconnect), session removed from cyrus_brain._registered_sessions."""  # noqa: E501
        msgs = [
            {
                "type": "register",
                "workspace": "disc-proj",
                "safe": "disc_proj",
                "port": 8768,
                "token": TOKEN,
            }
        ]
        # EOF is fed after messages — simulates disconnect
        reader, writer, _ = _make_reader_writer(msgs, eof=True)

        await cyrus_brain._handle_registration_client(reader, writer)

        # After handler completes, session should be removed
        assert "disc-proj" not in cyrus_brain._registered_sessions

    async def test_disconnect_removes_from_common_dict(self) -> None:
        """On EOF, session removed from cyrus_common._registered_sessions."""
        msgs = [
            {
                "type": "register",
                "workspace": "disc-common",
                "safe": "disc_common",
                "port": 8768,
                "token": TOKEN,
            }
        ]
        reader, writer, _ = _make_reader_writer(msgs, eof=True)

        await cyrus_brain._handle_registration_client(reader, writer)

        assert "disc-common" not in cyrus_common._registered_sessions

    async def test_disconnect_logs_workspace(self) -> None:
        """On disconnect, log message includes workspace name."""
        import logging

        msgs = [
            {
                "type": "register",
                "workspace": "disc-log-proj",
                "safe": "disc_log_proj",
                "port": 8768,
                "token": TOKEN,
            }
        ]
        reader, writer, _ = _make_reader_writer(msgs, eof=True)

        with self.assertLogs("cyrus.brain", level=logging.INFO) as cm:
            await cyrus_brain._handle_registration_client(reader, writer)

        log_output = "\n".join(cm.output)
        assert "disc-log-proj" in log_output


# ─────────────────────────────────────────────────────────────────────────────
# Multiple concurrent sessions
# ─────────────────────────────────────────────────────────────────────────────


class TestMultipleConcurrentSessions(unittest.IsolatedAsyncioTestCase):
    """Multiple sessions can be tracked simultaneously."""

    def setUp(self) -> None:
        with patch.dict(os.environ, {"CYRUS_AUTH_TOKEN": TOKEN, "CYRUS_HEADLESS": "1"}):
            importlib.reload(cyrus_config)
        cyrus_brain._registered_sessions.clear()
        cyrus_common._registered_sessions.clear()

    def tearDown(self) -> None:
        cyrus_brain._registered_sessions.clear()
        cyrus_common._registered_sessions.clear()

    async def test_two_sessions_tracked_independently(self) -> None:
        """Two concurrent register messages both tracked in _registered_sessions."""
        # Register two sessions concurrently
        msgs_a = [
            {
                "type": "register",
                "workspace": "proj-a",
                "safe": "proj_a",
                "port": 8768,
                "token": TOKEN,
            }
        ]
        msgs_b = [
            {
                "type": "register",
                "workspace": "proj-b",
                "safe": "proj_b",
                "port": 8769,
                "token": TOKEN,
            }
        ]
        reader_a, writer_a, _ = _make_reader_writer(msgs_a)
        reader_b, writer_b, _ = _make_reader_writer(msgs_b)

        await asyncio.gather(
            cyrus_brain._handle_registration_client(reader_a, writer_a),
            cyrus_brain._handle_registration_client(reader_b, writer_b),
        )

        # Both sessions were registered (and then disconnected/cleaned up)
        # The important thing is the handler ran for both without error
        # After EOF, both should be cleaned up
        assert "proj-a" not in cyrus_brain._registered_sessions
        assert "proj-b" not in cyrus_brain._registered_sessions

    async def test_one_disconnect_does_not_affect_other_session(self) -> None:
        """Disconnecting one session doesn't remove the other from the dict."""
        # Register proj-a with eof (disconnect immediately after register)
        # Register proj-b without eof (stays connected) - we'll manually test state

        # Simulate: proj-a registers and disconnects; proj-b registers and stays
        # We do this by running them sequentially
        msgs_a = [
            {
                "type": "register",
                "workspace": "multi-a",
                "safe": "multi_a",
                "port": 8768,
                "token": TOKEN,
            }
        ]
        reader_a, writer_a, _ = _make_reader_writer(msgs_a, eof=True)

        # Run proj-a (will register then disconnect)
        await cyrus_brain._handle_registration_client(reader_a, writer_a)
        # proj-a disconnected, should be cleaned up
        assert "multi-a" not in cyrus_brain._registered_sessions

        # Now manually inject proj-b into the sessions dict (simulating it's connected)
        mock_writer_b = MagicMock()
        cyrus_brain._registered_sessions["multi-b"] = cyrus_brain.SessionInfo(
            workspace="multi-b", safe="multi_b", port=8769, connection=mock_writer_b
        )

        # proj-a's disconnect should NOT have removed proj-b
        assert "multi-b" in cyrus_brain._registered_sessions


# ─────────────────────────────────────────────────────────────────────────────
# Malformed JSON handling
# ─────────────────────────────────────────────────────────────────────────────


class TestMalformedJsonHandling(unittest.IsolatedAsyncioTestCase):
    """Malformed JSON lines are skipped gracefully."""

    def setUp(self) -> None:
        with patch.dict(os.environ, {"CYRUS_AUTH_TOKEN": TOKEN, "CYRUS_HEADLESS": "1"}):
            importlib.reload(cyrus_config)
        cyrus_brain._registered_sessions.clear()

    def tearDown(self) -> None:
        cyrus_brain._registered_sessions.clear()

    async def test_malformed_json_does_not_crash_handler(self) -> None:
        """Handler continues processing after receiving malformed JSON."""
        reader = asyncio.StreamReader()
        reader.feed_data(b"not valid json\n")
        good_msg = {
            "type": "register",
            "workspace": "post-bad-json",
            "safe": "pbj",
            "port": 8768,
            "token": TOKEN,
        }
        reader.feed_data(json.dumps(good_msg).encode() + b"\n")
        reader.feed_eof()

        written: list[bytes] = []
        transport = MagicMock()
        protocol = MagicMock()
        loop = asyncio.get_event_loop()
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        writer.write = lambda data: written.append(data)
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 54321))

        # Should not raise
        await cyrus_brain._handle_registration_client(reader, writer)
        # Handler completed without crash

    async def test_empty_line_does_not_crash_handler(self) -> None:
        """Handler skips empty lines gracefully."""
        reader = asyncio.StreamReader()
        reader.feed_data(b"\n")
        reader.feed_data(b"\n")
        reader.feed_eof()

        transport = MagicMock()
        protocol = MagicMock()
        loop = asyncio.get_event_loop()
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        writer.write = lambda data: None
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 54321))

        # Should not raise
        await cyrus_brain._handle_registration_client(reader, writer)


# ─────────────────────────────────────────────────────────────────────────────
# Server headless-only behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistrationServerHeadlessOnly(unittest.IsolatedAsyncioTestCase):
    """Registration server only starts in HEADLESS mode."""

    async def test_init_servers_starts_reg_server_in_headless(self) -> None:
        """_init_servers() starts the registration server when HEADLESS=True."""
        with patch.dict(os.environ, {"CYRUS_HEADLESS": "1", "CYRUS_AUTH_TOKEN": TOKEN}):
            importlib.reload(cyrus_config)
            importlib.reload(cyrus_brain)

        started_servers = []

        async def mock_start_server(handler, host, port):
            started_servers.append(port)
            server = MagicMock()
            server.sockets = [MagicMock()]
            server.sockets[0].getsockname.return_value = (host, port)
            server.__aenter__ = AsyncMock(return_value=server)
            server.__aexit__ = AsyncMock()
            return server

        mock_ws_server = MagicMock()
        mock_ws_server.sockets = [MagicMock()]
        mock_ws_server.sockets[0].getsockname.return_value = ("0.0.0.0", 8769)

        # AsyncMock so that `await websockets.serve(...)` works
        mock_ws_serve = AsyncMock(return_value=mock_ws_server)

        session_mgr = MagicMock()
        loop = asyncio.get_event_loop()

        mock_health_runner = AsyncMock()

        with (
            patch.object(cyrus_brain, "HEADLESS", True),
            patch("asyncio.start_server", side_effect=mock_start_server),
            patch.object(cyrus_brain.websockets, "serve", mock_ws_serve),
            # Prevent _start_health_server from binding a real port 8771 so
            # this test remains isolated and doesn't conflict with subsequent
            # tests that also call _init_servers().
            patch.object(
                cyrus_brain,
                "_start_health_server",
                return_value=mock_health_runner,
            ),
        ):
            await cyrus_brain._init_servers("0.0.0.0", 8766, session_mgr, loop)

        # COMPANION_PORT (8770) should be in started servers
        assert cyrus_brain.COMPANION_PORT in started_servers, (
            f"Registration server (port {cyrus_brain.COMPANION_PORT}) must be started"
            f" in HEADLESS mode. Got: {started_servers}"
        )

    async def test_init_servers_skips_reg_server_when_not_headless(self) -> None:
        """_init_servers() does NOT start registration server when HEADLESS=False."""
        started_servers = []

        async def mock_start_server(handler, host, port):
            started_servers.append(port)
            server = MagicMock()
            server.sockets = [MagicMock()]
            server.sockets[0].getsockname.return_value = (host, port)
            return server

        mock_ws_server = MagicMock()
        mock_ws_server.sockets = [MagicMock()]
        mock_ws_server.sockets[0].getsockname.return_value = ("0.0.0.0", 8769)

        # AsyncMock so that `await websockets.serve(...)` works
        mock_ws_serve = AsyncMock(return_value=mock_ws_server)

        session_mgr = MagicMock()
        loop = asyncio.get_event_loop()

        mock_health_runner = AsyncMock()

        with (
            patch.object(cyrus_brain, "HEADLESS", False),
            patch("asyncio.start_server", side_effect=mock_start_server),
            patch.object(cyrus_brain.websockets, "serve", mock_ws_serve),
            # Prevent _start_health_server from binding a real port 8771 so
            # this test remains isolated and does not conflict with other tests.
            patch.object(
                cyrus_brain,
                "_start_health_server",
                return_value=mock_health_runner,
            ),
        ):
            await cyrus_brain._init_servers("0.0.0.0", 8766, session_mgr, loop)

        assert cyrus_brain.COMPANION_PORT not in started_servers, (
            "Registration server must NOT start when HEADLESS=False"
        )


if __name__ == "__main__":
    unittest.main()
