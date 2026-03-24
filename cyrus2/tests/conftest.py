"""
Shared pytest fixtures for the Cyrus 2.0 test suite.

This module is auto-loaded by pytest for every test in cyrus2/tests/.
Import fixtures by name in any test function or method; pytest injects them
automatically.

Available fixtures
------------------
tmp_path            Built-in pytest fixture — yields a ``pathlib.Path`` temp
                    directory that is unique per test invocation and cleaned up
                    afterwards.
                    Reference: https://docs.pytest.org/en/stable/how-to/tmp_path.html

mock_logger         A ``logging.Logger`` instance wired to the root logger hierarchy
                    so pytest's ``caplog`` fixture can capture its output.  Use this
                    fixture instead of ``logging.getLogger()`` directly in tests so
                    every test gets a fresh, consistently-named logger.

mock_config         A ``dict`` of default Cyrus runtime configuration values.  Mirrors
                    the keys set by ``argparse`` in ``cyrus_brain.py`` /
                    ``cyrus_server.py``.  Each test receives an independent copy —
                    mutations do not leak between tests.

mock_send           A ``unittest.mock.MagicMock`` that replaces the IPC ``_send()``
                    callable.  Automatically reset before each test so call counts
                    start at zero.  Configure ``side_effect`` or ``return_value``
                    as needed inside individual tests.

mock_silero_model   A ``unittest.mock.MagicMock`` that stands in for the Silero VAD
                    model returned by ``load_silero_vad()``.  By default the model
                    returns a result whose ``.item()`` yields ``0.8`` (confident
                    speech).  Override ``return_value`` or ``side_effect`` inside
                    individual tests to simulate silence or model failures.

Usage example
-------------
    def test_something(mock_logger, mock_config, mock_send):
        mock_config["port"] = 9999          # mutate without affecting other tests
        mock_send({"type": "chime"})
        mock_send.assert_called_once()
        mock_logger.info("logged during test")

    def test_vad_high_confidence(mock_silero_model):
        # Default: model reports 0.8 confidence (speech)
        result = mock_silero_model(None, 16000)
        assert result.item() == 0.8

    def test_vad_silence(mock_silero_model):
        mock_silero_model.return_value.item.return_value = 0.2  # silence
        result = mock_silero_model(None, 16000)
        assert result.item() == 0.2
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def mock_logger() -> logging.Logger:
    """Return a ``logging.Logger`` scoped to the current test.

    The logger is named ``"cyrus.test"`` so it participates in the normal
    logger hierarchy and pytest's ``caplog`` fixture can intercept its output
    via ``caplog.at_level(logging.DEBUG, logger="cyrus.test")``.

    Each test receives the same logger object; log handlers are *not* added
    here — rely on ``caplog`` for output capture rather than inspecting
    handler state directly.

    Returns:
        A ``logging.Logger`` instance named ``"cyrus.test"``.

    Example::

        def test_warning_logged(mock_logger, caplog):
            with caplog.at_level(logging.WARNING, logger="cyrus.test"):
                mock_logger.warning("something went wrong")
            assert "something went wrong" in caplog.text
    """
    return logging.getLogger("cyrus.test")


@pytest.fixture()
def mock_config() -> dict[str, Any]:
    """Return a default Cyrus runtime configuration dict for testing.

    Provides sensible defaults that mirror the values produced by argparse in
    ``cyrus_brain.py`` and ``cyrus_server.py``.  Each test receives its own
    independent copy so mutations inside one test never affect another.

    Keys
    ----
    host : str
        Hostname or IP the service binds to.  Default: ``"127.0.0.1"``.
    port : int
        TCP port for the inter-process communication socket.  Default: ``8765``.
    log_level : str
        Logging verbosity.  One of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``,
        ``CRITICAL``.  Default: ``"INFO"``.
    voice_host : str
        Hostname where ``cyrus_voice.py`` listens.  Default: ``"127.0.0.1"``.
    voice_port : int
        TCP port for the brain→voice websocket.  Default: ``8766``.

    Returns:
        A fresh ``dict`` with default configuration values.

    Example::

        def test_custom_port(mock_config):
            mock_config["port"] = 9999
            service = MyService(mock_config)
            assert service.port == 9999
    """
    # Return a new dict each call so tests cannot pollute each other
    return {
        "host": "127.0.0.1",
        "port": 8765,
        "log_level": "INFO",
        "voice_host": "127.0.0.1",
        "voice_port": 8766,
    }


@pytest.fixture()
def mock_send() -> MagicMock:
    """Return a fresh ``MagicMock`` that replaces the IPC ``_send()`` callable.

    ``_send()`` is the fire-and-forget function that serialises a dict as
    JSON and writes it to the brain↔voice TCP socket.  Replacing it with a
    ``MagicMock`` lets tests assert on the messages Cyrus would have sent
    without opening any real sockets.

    The mock is reset to zero calls at the start of every test (pytest creates
    a new ``MagicMock`` for each test invocation because the fixture scope is
    ``function``).

    Returns:
        A ``MagicMock`` with no pre-configured ``side_effect`` or
        ``return_value``.

    Example::

        def test_chime_sent_on_wake(mock_send):
            handle_wake_word(send=mock_send)
            mock_send.assert_called_once_with({"type": "chime"})

        def test_ipc_error_handled(mock_send):
            mock_send.side_effect = ConnectionError("socket closed")
            # Verify the caller handles the error gracefully
            result = safely_send(mock_send, {"type": "speak", "text": "hi"})
            assert result is False
    """
    return MagicMock()


@pytest.fixture()
def mock_silero_model() -> MagicMock:
    """Return a fresh ``MagicMock`` that stands in for the Silero VAD model.

    The Silero VAD model is loaded once by ``vad_loop()`` via
    ``load_silero_vad()`` and then called on every audio frame as::

        prob = model(tensor, sample_rate).item()

    This fixture returns a mock that, by default, reports confident speech
    (``item()`` returns ``0.8``).  Individual tests can override this::

        mock_silero_model.return_value.item.return_value = 0.2  # silence

    The mock also supports ``reset_states()`` which ``vad_loop()`` calls
    after each utterance to flush the model's internal RNN state.

    Returns:
        A ``MagicMock`` preconfigured so ``model(tensor, sr).item()``
        returns ``0.8`` and ``model.reset_states()`` is a no-op.

    Example::

        def test_speech_detected(mock_silero_model):
            # 0.8 > SPEECH_THRESHOLD (0.5) → frame is voiced
            result = mock_silero_model(None, 16000)
            assert result.item() == 0.8

        def test_silence_detected(mock_silero_model):
            mock_silero_model.return_value.item.return_value = 0.2
            result = mock_silero_model(None, 16000)
            assert result.item() < 0.5
    """
    model = MagicMock()
    # Default: return confident speech probability (above SPEECH_THRESHOLD = 0.5)
    model.return_value.item.return_value = 0.8
    return model
