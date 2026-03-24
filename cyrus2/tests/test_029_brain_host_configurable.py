"""
Acceptance-driven tests for Issue 029: Make Hook Brain Host Configurable.

Tests verify every acceptance criterion from the issue:
  - CYRUS_BRAIN_HOST env var is read by cyrus2/cyrus_hook.py
  - Defaults to 'localhost' when CYRUS_BRAIN_HOST is not set
  - Hook connects to {CYRUS_BRAIN_HOST}:BRAIN_PORT (uses the configured host)
  - Socket timeout is still respected regardless of host
  - CYRUS_BRAIN_HOST is documented in .env.example

Strategy:
  - Use importlib.reload() with monkeypatched env vars to test module-level
    BRAIN_HOST constant, since it is evaluated at import time.
  - Patch socket.create_connection to intercept connection attempts without
    opening real sockets.
  - Test _send() directly with patched sockets to verify (host, port) tuple.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure cyrus2/ is importable from tests/
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

import cyrus_hook  # noqa: E402,I001


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _reload_hook(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> object:
    """Reload cyrus_hook with a controlled environment.

    Clears CYRUS_BRAIN_HOST from the environment first, then applies any
    entries in ``env``.  Returns the freshly-reloaded module.

    Args:
        monkeypatch: pytest fixture for env-var manipulation.
        env: Environment overrides to apply before reloading.

    Returns:
        The reloaded cyrus_hook module object.
    """
    # Remove the variable so the "not set" path is cleanly testable
    monkeypatch.delenv("CYRUS_BRAIN_HOST", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    # Need to reload so the module-level BRAIN_HOST is re-evaluated
    return importlib.reload(cyrus_hook)


# ─────────────────────────────────────────────────────────────────────────────
# Default behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestBrainHostDefault:
    """BRAIN_HOST defaults to 'localhost' when CYRUS_BRAIN_HOST is not set."""

    def test_brain_host_defaults_to_localhost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When CYRUS_BRAIN_HOST env var is absent, BRAIN_HOST is 'localhost'.

        Backward-compatibility requirement: existing deployments that do not
        set CYRUS_BRAIN_HOST must continue to connect to localhost without
        any configuration change.
        """
        module = _reload_hook(monkeypatch, {})
        assert module.BRAIN_HOST == "localhost"

    def test_brain_host_default_is_string_localhost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BRAIN_HOST default value is the string 'localhost', not an IP."""
        module = _reload_hook(monkeypatch, {})
        assert isinstance(module.BRAIN_HOST, str)
        assert module.BRAIN_HOST == "localhost"


# ─────────────────────────────────────────────────────────────────────────────
# Env var is read
# ─────────────────────────────────────────────────────────────────────────────


class TestBrainHostEnvVar:
    """BRAIN_HOST reads the CYRUS_BRAIN_HOST environment variable."""

    def test_brain_host_reads_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When CYRUS_BRAIN_HOST is set, BRAIN_HOST reflects that value.

        Enables Docker deployments where the brain runs in a container and
        the hook runs on the host machine, requiring a non-localhost address.
        """
        module = _reload_hook(monkeypatch, {"CYRUS_BRAIN_HOST": "192.168.1.100"})
        assert module.BRAIN_HOST == "192.168.1.100"

    def test_brain_host_docker_internal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CYRUS_BRAIN_HOST=host.docker.internal is accepted as-is.

        Docker Desktop exposes the host's loopback via 'host.docker.internal'.
        Cyrus should pass the value straight through without validation.
        """
        module = _reload_hook(monkeypatch, {"CYRUS_BRAIN_HOST": "host.docker.internal"})
        assert module.BRAIN_HOST == "host.docker.internal"

    def test_brain_host_loopback_ip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CYRUS_BRAIN_HOST=127.0.0.1 works as an alternative loopback address."""
        module = _reload_hook(monkeypatch, {"CYRUS_BRAIN_HOST": "127.0.0.1"})
        assert module.BRAIN_HOST == "127.0.0.1"

    def test_brain_host_hostname(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CYRUS_BRAIN_HOST accepts arbitrary hostnames."""
        module = _reload_hook(monkeypatch, {"CYRUS_BRAIN_HOST": "brain.example.com"})
        assert module.BRAIN_HOST == "brain.example.com"


# ─────────────────────────────────────────────────────────────────────────────
# _send() uses the configured host
# ─────────────────────────────────────────────────────────────────────────────


class TestSendUsesConfiguredHost:
    """_send() connects to socket using BRAIN_HOST and BRAIN_PORT."""

    def test_send_uses_localhost_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_send() calls socket.create_connection(('localhost', port), ...) by default.

        Verifies that the (host, port) tuple passed to create_connection
        matches the default BRAIN_HOST of 'localhost'.
        """
        module = _reload_hook(monkeypatch, {})
        mock_socket = MagicMock()
        mock_socket.__enter__ = MagicMock(return_value=mock_socket)
        mock_socket.__exit__ = MagicMock(return_value=False)

        with patch(
            "cyrus_hook.socket.create_connection",
            return_value=mock_socket,
        ) as mock_conn:
            module._send({"event": "test"})

        mock_conn.assert_called_once()
        host, port = mock_conn.call_args[0][0]
        assert host == "localhost"
        assert port == module.BRAIN_PORT

    def test_send_uses_brain_host_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_send() uses the CYRUS_BRAIN_HOST value in create_connection.

        After setting CYRUS_BRAIN_HOST=192.168.1.50, the socket call must
        target that address instead of localhost.
        """
        module = _reload_hook(monkeypatch, {"CYRUS_BRAIN_HOST": "192.168.1.50"})
        mock_socket = MagicMock()
        mock_socket.__enter__ = MagicMock(return_value=mock_socket)
        mock_socket.__exit__ = MagicMock(return_value=False)

        with patch(
            "cyrus_hook.socket.create_connection",
            return_value=mock_socket,
        ) as mock_conn:
            module._send({"event": "test"})

        mock_conn.assert_called_once()
        host, port = mock_conn.call_args[0][0]
        assert host == "192.168.1.50"

    def test_send_timeout_still_respected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_send() always passes timeout=2 to create_connection regardless of host.

        The 2-second timeout prevents the hook from blocking Claude Code when
        the brain is unreachable, regardless of whether it is on localhost or
        a remote host.
        """
        module = _reload_hook(monkeypatch, {"CYRUS_BRAIN_HOST": "remote.host"})
        mock_socket = MagicMock()
        mock_socket.__enter__ = MagicMock(return_value=mock_socket)
        mock_socket.__exit__ = MagicMock(return_value=False)

        with patch(
            "cyrus_hook.socket.create_connection",
            return_value=mock_socket,
        ) as mock_conn:
            module._send({"event": "test"})

        _, kwargs = mock_conn.call_args
        assert kwargs.get("timeout") == 2


# ─────────────────────────────────────────────────────────────────────────────
# Graceful failure
# ─────────────────────────────────────────────────────────────────────────────


class TestGracefulFailure:
    """_send() fails silently when the brain is unreachable."""

    def test_send_silent_on_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_send() swallows ConnectionRefusedError when brain is not running.

        A crashing or blocking hook prevents Claude Code from functioning;
        therefore all exceptions inside _send must be swallowed silently.
        """
        module = _reload_hook(monkeypatch, {"CYRUS_BRAIN_HOST": "localhost"})
        with patch(
            "cyrus_hook.socket.create_connection",
            side_effect=ConnectionRefusedError("connection refused"),
        ):
            # Must not raise
            module._send({"event": "stop", "text": "hello"})

    def test_send_silent_on_invalid_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_send() swallows OSError when CYRUS_BRAIN_HOST is an invalid host.

        Setting CYRUS_BRAIN_HOST to an unreachable hostname must not cause
        the hook to crash or block Claude Code.
        """
        module = _reload_hook(monkeypatch, {"CYRUS_BRAIN_HOST": "invalid.host.example"})
        with patch(
            "cyrus_hook.socket.create_connection",
            side_effect=OSError("name or service not known"),
        ):
            # Must not raise
            module._send({"event": "stop", "text": "test"})

    def test_send_silent_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_send() swallows TimeoutError when the remote host is unreachable.

        Timeouts from a remote CYRUS_BRAIN_HOST must be silently dropped to
        avoid blocking Claude Code operations.
        """
        module = _reload_hook(monkeypatch, {"CYRUS_BRAIN_HOST": "10.0.0.1"})
        with patch(
            "cyrus_hook.socket.create_connection",
            side_effect=TimeoutError("timed out"),
        ):
            # Must not raise
            module._send({"event": "notification", "message": "test"})


# ─────────────────────────────────────────────────────────────────────────────
# .env.example documentation
# ─────────────────────────────────────────────────────────────────────────────


class TestEnvExampleDocumentation:
    """CYRUS_BRAIN_HOST is documented in .env.example."""

    def test_env_example_documents_cyrus_brain_host(self) -> None:
        """The .env.example file must contain CYRUS_BRAIN_HOST.

        Operators deploying Cyrus with Docker need to know the variable exists
        and what it does.  The .env.example file is the canonical reference for
        configurable environment variables.
        """
        env_example = Path(__file__).parent.parent.parent / ".env.example"
        assert env_example.exists(), ".env.example must exist"
        content = env_example.read_text()
        assert "CYRUS_BRAIN_HOST" in content, (
            ".env.example must document CYRUS_BRAIN_HOST"
        )

    def test_env_example_brain_host_has_default_value(self) -> None:
        """The .env.example CYRUS_BRAIN_HOST entry must show 'localhost' as default.

        The example should give operators a working default to copy from.
        """
        env_example = Path(__file__).parent.parent.parent / ".env.example"
        content = env_example.read_text()
        assert "CYRUS_BRAIN_HOST=localhost" in content, (
            ".env.example must show CYRUS_BRAIN_HOST=localhost as the default"
        )
