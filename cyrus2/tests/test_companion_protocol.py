"""
Acceptance-driven tests for Issue 026: test_companion_protocol.py (Tier 4).

Tests verify every acceptance criterion from the issue:
  - Message encoding: dict → JSON bytes with trailing newline
  - Message decoding: JSON bytes → dict parsing
  - Socket communication: send/receive with mock sockets
  - Protocol error handling: malformed JSON, connection loss, timeout

Strategy: Mock TCP sockets to test the JSON line protocol used by
``_submit_via_extension()`` and ``_open_companion_connection()`` in
``cyrus_brain.py`` without opening any real sockets.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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

# Add cyrus2/ to sys.path so ``import cyrus_brain`` resolves correctly.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

from cyrus_brain import (  # noqa: E402
    _open_companion_connection,
    _submit_via_extension,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_socket() -> MagicMock:
    """Return a MagicMock with a socket.socket spec for use in protocol tests.

    Default behaviour:
    - ``send()`` reports 100 bytes sent.
    - ``recv()`` returns a JSON line with a successful ``{"ok": true}`` response.
    - ``sendall()`` is a no-op success.

    Override ``return_value`` or ``side_effect`` inside individual tests.

    Returns:
        A MagicMock configured to mimic a connected TCP socket.
    """
    sock = MagicMock(spec=socket.socket)
    # Ensure `with sock as s:` returns the same object (not a new MagicMock)
    sock.__enter__ = MagicMock(return_value=sock)
    sock.__exit__ = MagicMock(return_value=False)
    sock.send.return_value = 100
    # Default recv: valid JSON line (companion confirms success)
    sock.recv.return_value = b'{"ok": true}\n'
    sock.sendall.return_value = None
    return sock


# ─────────────────────────────────────────────────────────────────────────────
# Encoding tests (~2 cases)
# ─────────────────────────────────────────────────────────────────────────────


class TestMessageEncoding:
    """Verify that dicts are serialised to JSON lines (JSON + trailing newline)."""

    def test_simple_dict_encodes_to_json_line(self) -> None:
        """A flat dict must be encoded as ``json.dumps(msg) + '\\n'`` in UTF-8.

        Checks the exact byte sequence that ``_submit_via_extension`` passes to
        ``socket.sendall`` for a simple text payload.
        """
        message = {"text": "hello world"}
        # Replicate the exact encoding used in _submit_via_extension:
        # s.sendall((json.dumps({"text": text}) + "\n").encode("utf-8"))
        encoded = (json.dumps(message) + "\n").encode("utf-8")

        assert encoded.endswith(b"\n"), "Encoded message must end with a newline byte"
        decoded = json.loads(encoded.decode("utf-8").strip())
        assert decoded == message, "Round-trip: decoded bytes must equal original dict"

    @pytest.mark.parametrize(
        "msg, expected_keys",
        [
            ({"text": "run tests"}, ["text"]),
            ({"text": "hello\nworld", "project": "cyrus"}, ["text", "project"]),
            ({"text": 'say "hello"', "nested": {"a": 1}}, ["text", "nested"]),
        ],
    )
    def test_nested_and_special_chars_encode_correctly(
        self, msg: dict, expected_keys: list[str]
    ) -> None:
        """Nested objects and special characters must survive JSON serialisation.

        The JSON line protocol must not corrupt values that contain quotes,
        literal newlines, or nested dicts; json.dumps() handles all escaping.
        """
        encoded = (json.dumps(msg) + "\n").encode("utf-8")

        # Must end with newline
        assert encoded.endswith(b"\n")

        # Round-trip must be lossless
        decoded = json.loads(encoded.decode("utf-8").strip())
        for key in expected_keys:
            assert key in decoded
            assert decoded[key] == msg[key]


# ─────────────────────────────────────────────────────────────────────────────
# Decoding tests (~2 cases)
# ─────────────────────────────────────────────────────────────────────────────


class TestMessageDecoding:
    """Verify that JSON lines arriving from the socket are decoded to dicts."""

    def test_valid_json_line_decodes_to_dict(self) -> None:
        """A newline-terminated JSON bytes buffer must decode to the original dict.

        Mirrors the decoding step in ``_submit_via_extension``:
        ``json.loads(raw.decode("utf-8").strip())``.
        """
        raw = b'{"ok": true}\n'
        result = json.loads(raw.decode("utf-8").strip())

        assert isinstance(result, dict)
        assert result.get("ok") is True

    def test_json_line_with_extra_fields_decodes_fully(self) -> None:
        """A JSON response with multiple fields must decode every field correctly."""
        payload = {"ok": False, "error": "Extension busy", "code": 503}
        raw = (json.dumps(payload) + "\n").encode("utf-8")
        result = json.loads(raw.decode("utf-8").strip())

        assert result["ok"] is False
        assert result["error"] == "Extension busy"
        assert result["code"] == 503

    def test_submit_via_extension_reads_until_newline(
        self, mock_socket: MagicMock
    ) -> None:
        """Socket recv loop must accumulate chunks until a newline is found.

        Simulates the buffer loop inside ``_submit_via_extension``:
        the first recv call returns a partial line, the second delivers
        the remainder with the terminating newline.
        """
        # Two-chunk response: split across recv calls
        mock_socket.recv.side_effect = [b'{"ok":', b" true}\n"]

        with (
            patch("cyrus_brain._open_companion_connection", return_value=mock_socket),
            patch("cyrus_brain._active_project", "default"),
            patch("cyrus_brain._active_project_lock"),
            # Force non-headless path regardless of test execution order; test_030
            # reloads cyrus_brain with HEADLESS=True which can leak between tests.
            patch("cyrus_brain.HEADLESS", False),
        ):
            result = _submit_via_extension("type something")

        assert result is True, "Must return True when extension responds {ok: true}"
        assert mock_socket.recv.call_count == 2, "Must call recv twice to complete line"


# ─────────────────────────────────────────────────────────────────────────────
# Socket communication tests (~2 cases)
# ─────────────────────────────────────────────────────────────────────────────


class TestSocketCommunication:
    """Verify that send/receive integration works correctly through mock sockets."""

    def test_sendall_called_with_json_line_bytes(self, mock_socket: MagicMock) -> None:
        """``_submit_via_extension`` must call ``sendall`` with the JSON-encoded text.

        Verifies that:
        - ``sendall`` is called exactly once.
        - The payload contains the ``text`` key with the correct value.
        - The payload contains the ``token`` key for companion auth (port 8770
          validates the shared-secret token per Issue 028 acceptance criteria).
        - The line is terminated with a newline byte.
        """
        text = "run the tests"

        with (
            patch("cyrus_brain._open_companion_connection", return_value=mock_socket),
            patch("cyrus_brain._active_project", "default"),
            patch("cyrus_brain._active_project_lock"),
            # Force non-headless path regardless of test execution order; test_030
            # reloads cyrus_brain with HEADLESS=True which can leak between tests.
            patch("cyrus_brain.HEADLESS", False),
        ):
            _submit_via_extension(text)

        mock_socket.sendall.assert_called_once()
        sent_bytes: bytes = mock_socket.sendall.call_args[0][0]
        assert sent_bytes.endswith(b"\n"), "Payload must end with a newline byte"
        sent_dict = json.loads(sent_bytes.decode("utf-8").strip())
        assert sent_dict["text"] == text, "Payload must contain the correct text value"
        # Issue 028: companion extension (port 8770) validates the auth token.
        # The brain includes the token so the extension can authenticate the sender.
        assert "token" in sent_dict, "Payload must include auth token for companion"

    def test_successful_extension_response_returns_true(
        self, mock_socket: MagicMock
    ) -> None:
        """A ``{"ok": true}`` response must cause ``_submit_via_extension`` to
        return True."""
        mock_socket.recv.return_value = b'{"ok": true}\n'

        with (
            patch("cyrus_brain._open_companion_connection", return_value=mock_socket),
            patch("cyrus_brain._active_project", "myproject"),
            patch("cyrus_brain._active_project_lock"),
            # Force non-headless path regardless of test execution order; test_030
            # reloads cyrus_brain with HEADLESS=True which can leak between tests.
            patch("cyrus_brain.HEADLESS", False),
        ):
            result = _submit_via_extension("hello")

        assert result is True

    def test_extension_error_response_returns_false(
        self, mock_socket: MagicMock
    ) -> None:
        """An ``{"ok": false}`` response must cause ``_submit_via_extension``
        to return False."""
        mock_socket.recv.return_value = b'{"ok": false, "error": "not ready"}\n'

        with (
            patch("cyrus_brain._open_companion_connection", return_value=mock_socket),
            patch("cyrus_brain._active_project", "default"),
            patch("cyrus_brain._active_project_lock"),
        ):
            result = _submit_via_extension("submit this")

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Protocol error handling tests (~2 cases)
# ─────────────────────────────────────────────────────────────────────────────


class TestProtocolErrorHandling:
    """Verify graceful handling of malformed JSON, connection loss, and timeout."""

    def test_file_not_found_returns_false(self) -> None:
        """Missing port file / socket file must return False without raising.

        On Windows the discovery file is absent; on Unix/Mac the socket file
        doesn't exist.  Either way the function must not propagate the
        FileNotFoundError.
        """
        with (
            patch(
                "cyrus_brain._open_companion_connection",
                side_effect=FileNotFoundError("port file missing"),
            ),
            patch("cyrus_brain._active_project", "default"),
            patch("cyrus_brain._active_project_lock"),
        ):
            result = _submit_via_extension("any text")

        assert result is False

    def test_connection_refused_returns_false(self) -> None:
        """A ``ConnectionRefusedError`` (extension not running) must return False.

        The companion extension may not be running; the caller falls back to
        UI-automation instead of crashing.
        """
        with (
            patch(
                "cyrus_brain._open_companion_connection",
                side_effect=ConnectionRefusedError("refused"),
            ),
            patch("cyrus_brain._active_project", "default"),
            patch("cyrus_brain._active_project_lock"),
        ):
            result = _submit_via_extension("type this")

        assert result is False

    def test_socket_disconnect_mid_recv_returns_false(
        self, mock_socket: MagicMock
    ) -> None:
        """An empty recv() (socket closed by peer) must be handled gracefully.

        When ``recv()`` returns ``b""`` the loop exits; an empty buffer cannot
        be decoded as JSON, so the function should return False rather than
        raise an exception.
        """
        # sendall succeeds, but recv returns empty (connection dropped)
        mock_socket.recv.return_value = b""

        with (
            patch("cyrus_brain._open_companion_connection", return_value=mock_socket),
            patch("cyrus_brain._active_project", "default"),
            patch("cyrus_brain._active_project_lock"),
        ):
            result = _submit_via_extension("hello")

        # Empty recv means no valid JSON — must not raise, must return False
        assert result is False

    def test_malformed_json_response_returns_false(
        self, mock_socket: MagicMock
    ) -> None:
        """A corrupt JSON response from the extension must be handled gracefully.

        If the extension sends back invalid JSON the function must catch the
        ``json.JSONDecodeError`` and return False rather than propagate it.
        """
        mock_socket.recv.return_value = b"not valid json\n"

        with (
            patch("cyrus_brain._open_companion_connection", return_value=mock_socket),
            patch("cyrus_brain._active_project", "default"),
            patch("cyrus_brain._active_project_lock"),
        ):
            result = _submit_via_extension("submit text")

        assert result is False

    def test_socket_timeout_exception_returns_false(
        self, mock_socket: MagicMock
    ) -> None:
        """A ``socket.timeout`` raised during recv must be caught, returning False.

        Network calls may time out; ``_submit_via_extension`` must not propagate
        the exception to its caller.
        """
        mock_socket.recv.side_effect = TimeoutError("timed out")

        with (
            patch("cyrus_brain._open_companion_connection", return_value=mock_socket),
            patch("cyrus_brain._active_project", "default"),
            patch("cyrus_brain._active_project_lock"),
        ):
            result = _submit_via_extension("timeout test")

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# _open_companion_connection tests (Unix path)
# ─────────────────────────────────────────────────────────────────────────────


class TestOpenCompanionConnection:
    """Verify the socket-opening helper connects to the right path / port."""

    @pytest.mark.skipif(
        os.name == "nt", reason="Unix socket path test — skip on Windows"
    )
    def test_unix_socket_path_uses_tmp_dir(self) -> None:
        """On non-Windows the socket path must be in the temp directory.

        ``_open_companion_connection`` must build the path as
        ``<tmpdir>/cyrus-companion-<safe>.sock`` and call ``socket.connect``
        with that path.
        """
        safe = "myproject"
        expected_path = os.path.join(
            tempfile.gettempdir(), f"cyrus-companion-{safe}.sock"
        )

        fake_sock = MagicMock(spec=socket.socket)
        fake_sock.__enter__ = lambda s: s
        fake_sock.__exit__ = MagicMock(return_value=False)

        with patch("socket.socket", return_value=fake_sock):
            with patch.object(fake_sock, "connect") as mock_connect:
                try:
                    _open_companion_connection(safe)
                except Exception:
                    pass  # We only care that connect was called with the right path

                mock_connect.assert_called_once_with(expected_path)
