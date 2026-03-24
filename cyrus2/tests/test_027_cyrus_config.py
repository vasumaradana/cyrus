"""
Acceptance-driven tests for Issue 027: Create Centralized Config Module.

These tests verify every acceptance criterion from the issue:
  - cyrus2/cyrus_config.py created with all required constants
  - Ports defined: BRAIN_PORT=8766, HOOK_PORT=8767, MOBILE_PORT=8769,
    COMPANION_PORT=8770, SERVER_PORT=8765
  - Timeouts defined: TTS_TIMEOUT=25.0, SOCKET_TIMEOUT=10, VAD poll intervals
  - All values read from env vars with fallback defaults
  - .env.example file created documenting all configurable options

Test categories
---------------
  Defaults             (7 tests) — all constants have correct default values
  Env var overrides    (7 tests) — CYRUS_* env vars override every constant
  Error cases          (4 tests) — invalid / malformed env var values
  Edge cases           (3 tests) — zero values, large values, partial overrides
  .env.example         (3 tests) — file exists, all keys present, correct format
  Module interface     (3 tests) — imports cleanly, no side effects, re-importable

Usage
-----
    pytest tests/test_027_cyrus_config.py -v
    pytest tests/test_027_cyrus_config.py -k "defaults" -v
"""

from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# ── Path setup ────────────────────────────────────────────────────────────────
# cyrus_config.py lives in cyrus2/ — make that importable as a top-level module
# by inserting the cyrus2/ directory at the front of sys.path.

_CYRUS2_DIR = Path(__file__).parent.parent  # .../cyrus/cyrus2/
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

import cyrus_config  # noqa: E402 — must come after sys.path setup


def _reload_with_env(**kwargs: str) -> object:
    """Reload cyrus_config with the given environment overrides in effect.

    Uses ``patch.dict`` to inject env vars, reloads the module, then returns
    the freshly-evaluated module object.  Restores the original ``sys.modules``
    entry after the with-block so the default module is available again for
    subsequent tests.

    Args:
        **kwargs: Mapping of env var names to string values (all values are str
                  because os.environ stores strings).

    Returns:
        The reloaded ``cyrus_config`` module with the given overrides applied.
    """
    with patch.dict(os.environ, kwargs, clear=False):
        return importlib.reload(cyrus_config)


# ── Default value tests ────────────────────────────────────────────────────────


class TestConfigDefaults(unittest.TestCase):
    """Verify every constant has the correct hardcoded default value.

    These tests run without setting any CYRUS_* environment variables so they
    verify the fallback values used in production when no .env is loaded.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure a clean module state with no overrides in effect."""
        # Strip any CYRUS_* vars that might have leaked from the environment
        cyrus_env_keys = [k for k in os.environ if k.startswith("CYRUS_")]
        cls._saved_env: dict[str, str] = {k: os.environ.pop(k) for k in cyrus_env_keys}
        importlib.reload(cyrus_config)

    @classmethod
    def tearDownClass(cls) -> None:
        """Restore any CYRUS_* vars stripped in setUpClass."""
        os.environ.update(cls._saved_env)
        importlib.reload(cyrus_config)

    # ── Port defaults ──────────────────────────────────────────────────────────

    def test_brain_port_default(self) -> None:
        """BRAIN_PORT must default to 8766 (voice ↔ brain TCP socket)."""
        self.assertEqual(cyrus_config.BRAIN_PORT, 8766)

    def test_hook_port_default(self) -> None:
        """HOOK_PORT must default to 8767 (Claude Code Stop hook)."""
        self.assertEqual(cyrus_config.HOOK_PORT, 8767)

    def test_mobile_port_default(self) -> None:
        """MOBILE_PORT must default to 8769 (mobile WebSocket endpoint)."""
        self.assertEqual(cyrus_config.MOBILE_PORT, 8769)

    def test_companion_port_default(self) -> None:
        """COMPANION_PORT must default to 8770 (VS Code companion extension)."""
        self.assertEqual(cyrus_config.COMPANION_PORT, 8770)

    def test_server_port_default(self) -> None:
        """SERVER_PORT must default to 8765 (cyrus_server.py WebSocket)."""
        self.assertEqual(cyrus_config.SERVER_PORT, 8765)

    # ── Timeout defaults ───────────────────────────────────────────────────────

    def test_tts_timeout_default(self) -> None:
        """TTS_TIMEOUT must default to 25.0 seconds."""
        self.assertAlmostEqual(cyrus_config.TTS_TIMEOUT, 25.0)

    def test_socket_timeout_default(self) -> None:
        """SOCKET_TIMEOUT must default to 10 seconds."""
        self.assertEqual(cyrus_config.SOCKET_TIMEOUT, 10)

    # ── VAD threshold defaults ─────────────────────────────────────────────────

    def test_speech_threshold_default(self) -> None:
        """SPEECH_THRESHOLD must default to 0.6 (Silero VAD probability gate)."""
        self.assertAlmostEqual(cyrus_config.SPEECH_THRESHOLD, 0.6)

    def test_silence_window_default(self) -> None:
        """SILENCE_WINDOW must default to 1500 ms of silence to end utterance."""
        self.assertEqual(cyrus_config.SILENCE_WINDOW, 1500)

    def test_min_speech_duration_default(self) -> None:
        """MIN_SPEECH_DURATION must default to 500 ms minimum speech."""
        self.assertEqual(cyrus_config.MIN_SPEECH_DURATION, 500)

    # ── Poll interval defaults ─────────────────────────────────────────────────

    def test_chat_watcher_poll_interval_default(self) -> None:
        """CHAT_WATCHER_POLL_INTERVAL must default to 0.5 seconds."""
        self.assertAlmostEqual(cyrus_config.CHAT_WATCHER_POLL_INTERVAL, 0.5)

    def test_permission_watcher_poll_interval_default(self) -> None:
        """PERMISSION_WATCHER_POLL_INTERVAL must default to 0.3 seconds."""
        self.assertAlmostEqual(cyrus_config.PERMISSION_WATCHER_POLL_INTERVAL, 0.3)

    def test_max_speech_words_default(self) -> None:
        """MAX_SPEECH_WORDS must default to 200 words."""
        self.assertEqual(cyrus_config.MAX_SPEECH_WORDS, 200)


# ── Env var override tests ────────────────────────────────────────────────────


class TestConfigEnvOverrides(unittest.TestCase):
    """Verify that CYRUS_* environment variables override every constant.

    Each test patches exactly one env var, reloads the module, and asserts
    the value changed.  Cleanup restores the original module state.
    """

    def tearDown(self) -> None:
        """Reload with no overrides so the next test sees clean defaults."""
        # Remove any CYRUS_* vars we may have set
        for key in list(os.environ.keys()):
            if key.startswith("CYRUS_"):
                del os.environ[key]
        importlib.reload(cyrus_config)

    def test_brain_port_override(self) -> None:
        """CYRUS_BRAIN_PORT=9000 must change BRAIN_PORT to 9000."""
        mod = _reload_with_env(CYRUS_BRAIN_PORT="9000")
        self.assertEqual(mod.BRAIN_PORT, 9000)

    def test_hook_port_override(self) -> None:
        """CYRUS_HOOK_PORT=9001 must change HOOK_PORT to 9001."""
        mod = _reload_with_env(CYRUS_HOOK_PORT="9001")
        self.assertEqual(mod.HOOK_PORT, 9001)

    def test_mobile_port_override(self) -> None:
        """CYRUS_MOBILE_PORT=9002 must change MOBILE_PORT to 9002."""
        mod = _reload_with_env(CYRUS_MOBILE_PORT="9002")
        self.assertEqual(mod.MOBILE_PORT, 9002)

    def test_server_port_override(self) -> None:
        """CYRUS_SERVER_PORT=9003 must change SERVER_PORT to 9003."""
        mod = _reload_with_env(CYRUS_SERVER_PORT="9003")
        self.assertEqual(mod.SERVER_PORT, 9003)

    def test_tts_timeout_override(self) -> None:
        """CYRUS_TTS_TIMEOUT=30.0 must change TTS_TIMEOUT to 30.0."""
        mod = _reload_with_env(CYRUS_TTS_TIMEOUT="30.0")
        self.assertAlmostEqual(mod.TTS_TIMEOUT, 30.0)

    def test_speech_threshold_override(self) -> None:
        """CYRUS_SPEECH_THRESHOLD=0.8 must change SPEECH_THRESHOLD to 0.8."""
        mod = _reload_with_env(CYRUS_SPEECH_THRESHOLD="0.8")
        self.assertAlmostEqual(mod.SPEECH_THRESHOLD, 0.8)

    def test_silence_window_override(self) -> None:
        """CYRUS_SILENCE_WINDOW=2000 must change SILENCE_WINDOW to 2000."""
        mod = _reload_with_env(CYRUS_SILENCE_WINDOW="2000")
        self.assertEqual(mod.SILENCE_WINDOW, 2000)

    def test_max_speech_words_override(self) -> None:
        """CYRUS_MAX_SPEECH_WORDS=100 must change MAX_SPEECH_WORDS to 100."""
        mod = _reload_with_env(CYRUS_MAX_SPEECH_WORDS="100")
        self.assertEqual(mod.MAX_SPEECH_WORDS, 100)


# ── Error case tests ──────────────────────────────────────────────────────────


class TestConfigErrorCases(unittest.TestCase):
    """Verify behavior when env vars contain invalid values.

    The module uses plain int()/float() conversion, so invalid values must
    raise ValueError at import / reload time.  Tests verify this expected
    behavior so callers know what to expect when misconfigured.
    """

    def tearDown(self) -> None:
        """Reload with no overrides so next test sees clean defaults."""
        for key in list(os.environ.keys()):
            if key.startswith("CYRUS_"):
                del os.environ[key]
        importlib.reload(cyrus_config)

    def test_invalid_brain_port_raises_value_error(self) -> None:
        """Non-integer CYRUS_BRAIN_PORT must raise ValueError on import."""
        with self.assertRaises(ValueError):
            _reload_with_env(CYRUS_BRAIN_PORT="not_a_port")

    def test_invalid_tts_timeout_raises_value_error(self) -> None:
        """Non-float CYRUS_TTS_TIMEOUT must raise ValueError on import."""
        with self.assertRaises(ValueError):
            _reload_with_env(CYRUS_TTS_TIMEOUT="fast")

    def test_empty_brain_port_raises_value_error(self) -> None:
        """Empty string CYRUS_BRAIN_PORT must raise ValueError on import."""
        with self.assertRaises(ValueError):
            _reload_with_env(CYRUS_BRAIN_PORT="")

    def test_float_as_port_raises_value_error(self) -> None:
        """Float string for integer port (e.g. '8766.5') must raise ValueError."""
        with self.assertRaises(ValueError):
            _reload_with_env(CYRUS_BRAIN_PORT="8766.5")


# ── Edge case tests ───────────────────────────────────────────────────────────


class TestConfigEdgeCases(unittest.TestCase):
    """Edge cases: extreme values, combined overrides, type correctness."""

    def tearDown(self) -> None:
        """Reload with no overrides so next test sees clean defaults."""
        for key in list(os.environ.keys()):
            if key.startswith("CYRUS_"):
                del os.environ[key]
        importlib.reload(cyrus_config)

    def test_port_types_are_int(self) -> None:
        """All port constants must be Python int (not str or float)."""
        for attr in (
            "BRAIN_PORT",
            "HOOK_PORT",
            "MOBILE_PORT",
            "COMPANION_PORT",
            "SERVER_PORT",
        ):
            val = getattr(cyrus_config, attr)
            self.assertIsInstance(
                val,
                int,
                f"{attr} must be int, got {type(val).__name__}",
            )

    def test_float_constants_are_float(self) -> None:
        """TTS_TIMEOUT, SPEECH_THRESHOLD, poll intervals must be float."""
        for attr in (
            "TTS_TIMEOUT",
            "SPEECH_THRESHOLD",
            "CHAT_WATCHER_POLL_INTERVAL",
            "PERMISSION_WATCHER_POLL_INTERVAL",
        ):
            val = getattr(cyrus_config, attr)
            self.assertIsInstance(
                val,
                float,
                f"{attr} must be float, got {type(val).__name__}",
            )

    def test_large_port_value_accepted(self) -> None:
        """Port value at upper TCP bound (65535) must be accepted."""
        mod = _reload_with_env(CYRUS_BRAIN_PORT="65535")
        self.assertEqual(mod.BRAIN_PORT, 65535)

    def test_partial_override_leaves_others_unchanged(self) -> None:
        """Overriding one port must not change any other port constant."""
        mod = _reload_with_env(CYRUS_BRAIN_PORT="9999")
        self.assertEqual(mod.BRAIN_PORT, 9999)
        # Other ports must retain their defaults
        self.assertEqual(mod.HOOK_PORT, 8767)
        self.assertEqual(mod.MOBILE_PORT, 8769)
        self.assertEqual(mod.SERVER_PORT, 8765)

    def test_zero_socket_timeout_accepted(self) -> None:
        """SOCKET_TIMEOUT=0 must be accepted (disables timeout in socket API)."""
        mod = _reload_with_env(CYRUS_SOCKET_TIMEOUT="0")
        self.assertEqual(mod.SOCKET_TIMEOUT, 0)


# ── .env.example tests ────────────────────────────────────────────────────────


class TestEnvExample(unittest.TestCase):
    """.env.example documents every configurable environment variable.

    The file must:
      - Exist at cyrus2/.env.example
      - Contain every CYRUS_* key defined in cyrus_config.py
      - Use KEY=value format (one entry per line)
    """

    _ENV_EXAMPLE = _CYRUS2_DIR / ".env.example"

    # All CYRUS_* keys that must appear in .env.example
    _REQUIRED_KEYS = [
        "CYRUS_BRAIN_PORT",
        "CYRUS_HOOK_PORT",
        "CYRUS_MOBILE_PORT",
        "CYRUS_COMPANION_PORT",
        "CYRUS_SERVER_PORT",
        "CYRUS_TTS_TIMEOUT",
        "CYRUS_SOCKET_TIMEOUT",
        "CYRUS_SPEECH_THRESHOLD",
        "CYRUS_SILENCE_WINDOW",
        "CYRUS_MIN_SPEECH_DURATION",
        "CYRUS_CHAT_POLL_MS",
        "CYRUS_PERMISSION_POLL_MS",
        "CYRUS_MAX_SPEECH_WORDS",
        # Issue 028-1: authentication token
        "CYRUS_AUTH_TOKEN",
    ]

    def test_env_example_exists(self) -> None:
        """AC: .env.example must exist at cyrus2/.env.example."""
        self.assertTrue(
            self._ENV_EXAMPLE.exists(),
            f".env.example not found at {self._ENV_EXAMPLE}",
        )

    def test_env_example_contains_all_keys(self) -> None:
        """AC: every CYRUS_* key must appear in .env.example."""
        content = self._ENV_EXAMPLE.read_text(encoding="utf-8")
        for key in self._REQUIRED_KEYS:
            self.assertIn(
                key,
                content,
                f"Key {key!r} is missing from .env.example",
            )

    def test_env_example_uses_key_equals_format(self) -> None:
        """Each non-comment, non-blank line must match KEY=value format."""
        content = self._ENV_EXAMPLE.read_text(encoding="utf-8")
        for lineno, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue  # blank lines and comments are fine
            self.assertIn(
                "=",
                stripped,
                f".env.example line {lineno} does not use KEY=value format: {line!r}",
            )


# ── Module interface tests ────────────────────────────────────────────────────


class TestModuleInterface(unittest.TestCase):
    """cyrus_config.py module-level interface requirements.

    The module must be importable without hardware, without external deps,
    and must expose all required constants at the top level.
    """

    _REQUIRED_CONSTANTS = [
        "BRAIN_PORT",
        "HOOK_PORT",
        "MOBILE_PORT",
        "COMPANION_PORT",
        "SERVER_PORT",
        "TTS_TIMEOUT",
        "SOCKET_TIMEOUT",
        "SPEECH_THRESHOLD",
        "SILENCE_WINDOW",
        "MIN_SPEECH_DURATION",
        "CHAT_WATCHER_POLL_INTERVAL",
        "PERMISSION_WATCHER_POLL_INTERVAL",
        "MAX_SPEECH_WORDS",
        # Issue 028-1: authentication token constant and helper
        "AUTH_TOKEN",
        "validate_auth_token",
    ]

    def test_module_exposes_all_required_constants(self) -> None:
        """All required constants must be accessible as module attributes."""
        for name in self._REQUIRED_CONSTANTS:
            self.assertTrue(
                hasattr(cyrus_config, name),
                f"cyrus_config is missing required constant: {name!r}",
            )

    def test_module_imports_without_error(self) -> None:
        """Importing cyrus_config must not raise any exception."""
        try:
            importlib.reload(cyrus_config)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"cyrus_config import raised: {exc}")

    def test_module_has_no_hardware_dependencies(self) -> None:
        """cyrus_config must not import any hardware/audio/ML packages.

        Importing audio or ML deps at module level prevents the config module
        from being used in CI or server environments that don't have GPUs or
        audio hardware.  Verify by confirming the module uses only stdlib.
        """
        # These are the hardware packages we must not find as imports
        forbidden = {
            "sounddevice",
            "torch",
            "faster_whisper",
            "silero_vad",
            "pygame",
            "keyboard",
            "numpy",
            "comtypes",
            "uiautomation",
        }
        # Read the source and check for import statements.
        # No hardware packages are allowed in cyrus_config.py.
        source = (_CYRUS2_DIR / "cyrus_config.py").read_text(encoding="utf-8")
        for pkg in forbidden:
            self.assertNotIn(
                f"import {pkg}",
                source,
                f"cyrus_config.py must not import hardware package: {pkg!r}",
            )


# ── AUTH_TOKEN infrastructure tests (Issue 028-1) ────────────────────────────


class TestAuthToken(unittest.TestCase):
    """Acceptance-driven tests for the AUTH_TOKEN infrastructure (issue 028-1).

    These tests verify:
      - AUTH_TOKEN is a non-empty string when CYRUS_AUTH_TOKEN is set
      - AUTH_TOKEN is auto-generated (non-empty) when env var is absent
      - validate_auth_token() returns True for a matching token
      - validate_auth_token() returns False for a non-matching token
      - validate_auth_token() uses constant-time comparison (hmac.compare_digest)
    """

    def tearDown(self) -> None:
        """Restore clean module state after each test."""
        for key in list(os.environ.keys()):
            if key.startswith("CYRUS_"):
                del os.environ[key]
        importlib.reload(cyrus_config)

    # ── AC: AUTH_TOKEN reads from env var ──────────────────────────────────────

    def test_auth_token_reads_from_env_var(self) -> None:
        """CYRUS_AUTH_TOKEN env var must be reflected in AUTH_TOKEN constant."""
        expected = "deadbeefcafe1234deadbeefcafe1234"
        mod = _reload_with_env(CYRUS_AUTH_TOKEN=expected)
        self.assertEqual(mod.AUTH_TOKEN, expected)

    def test_auth_token_is_string(self) -> None:
        """AUTH_TOKEN must be a str, not bytes or None."""
        mod = _reload_with_env(CYRUS_AUTH_TOKEN="sometoken")
        self.assertIsInstance(mod.AUTH_TOKEN, str)

    # ── AC: auto-generate when env var absent ─────────────────────────────────

    def test_auth_token_auto_generated_when_unset(self) -> None:
        """AUTH_TOKEN must be a non-empty hex string when CYRUS_AUTH_TOKEN is absent."""
        # Remove env var if present so we force auto-generation
        os.environ.pop("CYRUS_AUTH_TOKEN", None)
        mod = importlib.reload(cyrus_config)
        self.assertIsInstance(mod.AUTH_TOKEN, str)
        self.assertTrue(
            len(mod.AUTH_TOKEN) > 0,
            "Auto-generated AUTH_TOKEN must not be empty",
        )
        # secrets.token_hex(16) produces 32 hex characters
        self.assertEqual(len(mod.AUTH_TOKEN), 32)
        self.assertTrue(
            all(c in "0123456789abcdef" for c in mod.AUTH_TOKEN),
            "Auto-generated AUTH_TOKEN must be lowercase hexadecimal",
        )

    def test_auth_token_warn_printed_to_stderr_when_unset(self) -> None:
        """A WARN message must be written to stderr when AUTH_TOKEN auto-generated."""
        import io

        os.environ.pop("CYRUS_AUTH_TOKEN", None)
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            importlib.reload(cyrus_config)
        output = stderr_capture.getvalue()
        self.assertIn(
            "WARN",
            output,
            "WARN prefix must appear in stderr when token auto-generated",
        )
        self.assertIn(
            "CYRUS_AUTH_TOKEN",
            output,
            "Stderr must mention CYRUS_AUTH_TOKEN var name",
        )

    # ── AC: validate_auth_token() helper ──────────────────────────────────────

    def test_validate_auth_token_returns_true_for_correct_token(self) -> None:
        """validate_auth_token(correct_token) must return True."""
        token = "abc123def456abc123def456abc12345"
        mod = _reload_with_env(CYRUS_AUTH_TOKEN=token)
        self.assertTrue(mod.validate_auth_token(token))

    def test_validate_auth_token_returns_false_for_wrong_token(self) -> None:
        """validate_auth_token(wrong_token) must return False."""
        mod = _reload_with_env(CYRUS_AUTH_TOKEN="correct_token_abc123")
        self.assertFalse(mod.validate_auth_token("wrong_token_xyz789"))

    def test_validate_auth_token_returns_false_for_empty_string(self) -> None:
        """validate_auth_token('') must return False when AUTH_TOKEN is non-empty."""
        mod = _reload_with_env(CYRUS_AUTH_TOKEN="sometoken123")
        self.assertFalse(mod.validate_auth_token(""))

    def test_validate_auth_token_returns_false_for_partial_match(self) -> None:
        """validate_auth_token() must reject a prefix of the correct token."""
        full_token = "deadbeefcafe1234deadbeefcafe1234"
        mod = _reload_with_env(CYRUS_AUTH_TOKEN=full_token)
        self.assertFalse(mod.validate_auth_token(full_token[:16]))

    def test_validate_auth_token_uses_hmac_compare_digest(self) -> None:
        """validate_auth_token() must call hmac.compare_digest (constant-time)."""
        mod = _reload_with_env(CYRUS_AUTH_TOKEN="sometoken")
        import inspect

        source = inspect.getsource(mod.validate_auth_token)
        self.assertIn(
            "hmac.compare_digest",
            source,
            "validate_auth_token must use hmac.compare_digest for constant-time cmp",
        )

    def test_validate_auth_token_signature(self) -> None:
        """validate_auth_token must accept exactly one str arg and return bool."""
        import inspect

        mod = _reload_with_env(CYRUS_AUTH_TOKEN="tok")
        sig = inspect.signature(mod.validate_auth_token)
        params = list(sig.parameters.values())
        self.assertEqual(
            len(params), 1, "validate_auth_token must have exactly one parameter"
        )
        self.assertEqual(params[0].name, "received")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
