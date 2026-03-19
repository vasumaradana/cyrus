"""
Acceptance-driven tests for Issue 037: Add Configurable Whisper Model.

These tests verify every acceptance criterion from the issue:
  - CYRUS_WHISPER_MODEL env var read in cyrus_config.py
  - Defaults to ``medium.en``
  - Valid options: tiny.en, base.en, small.en, medium.en
  - Voice module uses specified model (via WHISPER_MODEL import)
  - Logs model selected at startup (existing log in cyrus_voice.py)
  - Configuration validated (warn on invalid model name, fallback to medium.en)
  - CYRUS_WHISPER_MODEL documented in .env.example

Test categories
---------------
  Defaults          (2 tests) — WHISPER_MODEL defaults to medium.en
  Valid overrides   (4 tests) — each valid model can be selected via env var
  Validation        (3 tests) — invalid model triggers warning + fallback
  VALID_WHISPER_MODELS  (2 tests) — list contains exactly the 4 expected models
  .env.example      (1 test)  — CYRUS_WHISPER_MODEL is documented
  Module interface  (2 tests) — constants importable, voice module uses config

Usage
-----
    pytest tests/test_037_whisper_model_config.py -v
    pytest tests/test_037_whisper_model_config.py -k "defaults" -v
"""

from __future__ import annotations

import importlib
import io
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


class TestWhisperModelDefaults(unittest.TestCase):
    """WHISPER_MODEL defaults to medium.en when no env var is set.

    These tests run without CYRUS_WHISPER_MODEL in the environment to verify
    the production fallback value.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure a clean module state with no CYRUS_WHISPER_MODEL override."""
        os.environ.pop("CYRUS_WHISPER_MODEL", None)
        importlib.reload(cyrus_config)

    @classmethod
    def tearDownClass(cls) -> None:
        """Reload module to a clean state after this class."""
        os.environ.pop("CYRUS_WHISPER_MODEL", None)
        importlib.reload(cyrus_config)

    def test_whisper_model_default_is_medium_en(self) -> None:
        """AC: WHISPER_MODEL must default to 'medium.en' when env var absent."""
        self.assertEqual(cyrus_config.WHISPER_MODEL, "medium.en")

    def test_whisper_model_is_string(self) -> None:
        """WHISPER_MODEL must be a str, not bytes or None."""
        self.assertIsInstance(cyrus_config.WHISPER_MODEL, str)


# ── Valid model override tests ────────────────────────────────────────────────


class TestWhisperModelValidOverrides(unittest.TestCase):
    """Each valid model name can be selected via CYRUS_WHISPER_MODEL env var.

    Voice module loads whichever of the 4 valid models the operator requests.
    """

    def tearDown(self) -> None:
        """Reload with no overrides so the next test sees clean defaults."""
        os.environ.pop("CYRUS_WHISPER_MODEL", None)
        importlib.reload(cyrus_config)

    def test_tiny_en_override(self) -> None:
        """AC: CYRUS_WHISPER_MODEL=tiny.en must set WHISPER_MODEL to 'tiny.en'."""
        mod = _reload_with_env(CYRUS_WHISPER_MODEL="tiny.en")
        self.assertEqual(mod.WHISPER_MODEL, "tiny.en")

    def test_base_en_override(self) -> None:
        """AC: CYRUS_WHISPER_MODEL=base.en must set WHISPER_MODEL to 'base.en'."""
        mod = _reload_with_env(CYRUS_WHISPER_MODEL="base.en")
        self.assertEqual(mod.WHISPER_MODEL, "base.en")

    def test_small_en_override(self) -> None:
        """AC: CYRUS_WHISPER_MODEL=small.en must set WHISPER_MODEL to 'small.en'."""
        mod = _reload_with_env(CYRUS_WHISPER_MODEL="small.en")
        self.assertEqual(mod.WHISPER_MODEL, "small.en")

    def test_medium_en_override(self) -> None:
        """AC: CYRUS_WHISPER_MODEL=medium.en must set WHISPER_MODEL to 'medium.en'."""
        mod = _reload_with_env(CYRUS_WHISPER_MODEL="medium.en")
        self.assertEqual(mod.WHISPER_MODEL, "medium.en")


# ── Validation / invalid model tests ─────────────────────────────────────────


class TestWhisperModelValidation(unittest.TestCase):
    """Invalid model names must trigger a warning and fall back to medium.en.

    Configuration validated: warn on invalid model name, fallback to medium.en.
    """

    def tearDown(self) -> None:
        """Reload with no overrides so the next test sees clean defaults."""
        os.environ.pop("CYRUS_WHISPER_MODEL", None)
        importlib.reload(cyrus_config)

    def test_invalid_model_falls_back_to_medium_en(self) -> None:
        """AC: Invalid CYRUS_WHISPER_MODEL must fall back to 'medium.en'."""
        mod = _reload_with_env(CYRUS_WHISPER_MODEL="large-v3")
        self.assertEqual(
            mod.WHISPER_MODEL,
            "medium.en",
            "Invalid model must fall back to medium.en",
        )

    def test_invalid_model_prints_warning_to_stderr(self) -> None:
        """AC: Invalid model must print a WARN message to stderr."""
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            _reload_with_env(CYRUS_WHISPER_MODEL="bogus_model")
        output = stderr_capture.getvalue()
        self.assertIn(
            "WARN",
            output,
            "WARN prefix must appear in stderr when invalid model is configured",
        )

    def test_invalid_model_stderr_mentions_env_var(self) -> None:
        """AC: Stderr warning must mention CYRUS_WHISPER_MODEL."""
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            _reload_with_env(CYRUS_WHISPER_MODEL="invalid")
        output = stderr_capture.getvalue()
        self.assertIn(
            "CYRUS_WHISPER_MODEL",
            output,
            "Stderr must mention CYRUS_WHISPER_MODEL var name",
        )

    def test_empty_model_string_falls_back_to_medium_en(self) -> None:
        """Edge case: empty CYRUS_WHISPER_MODEL must fall back to medium.en."""
        mod = _reload_with_env(CYRUS_WHISPER_MODEL="")
        self.assertEqual(
            mod.WHISPER_MODEL,
            "medium.en",
            "Empty model string must fall back to medium.en",
        )


# ── VALID_WHISPER_MODELS list tests ───────────────────────────────────────────


class TestValidWhisperModelsList(unittest.TestCase):
    """VALID_WHISPER_MODELS must contain exactly the 4 expected model names."""

    @classmethod
    def setUpClass(cls) -> None:
        """Reload module to get a clean default state."""
        os.environ.pop("CYRUS_WHISPER_MODEL", None)
        importlib.reload(cyrus_config)

    def test_valid_whisper_models_contains_exactly_four_models(self) -> None:
        """AC: VALID_WHISPER_MODELS must list exactly 4 model names."""
        self.assertEqual(
            len(cyrus_config.VALID_WHISPER_MODELS),
            4,
            "VALID_WHISPER_MODELS must contain exactly 4 model names",
        )

    def test_valid_whisper_models_contains_expected_models(self) -> None:
        """AC: Valid options must be tiny.en, base.en, small.en, medium.en."""
        expected = {"tiny.en", "base.en", "small.en", "medium.en"}
        actual = set(cyrus_config.VALID_WHISPER_MODELS)
        self.assertEqual(
            actual,
            expected,
            f"VALID_WHISPER_MODELS mismatch. Expected {expected}, got {actual}",
        )


# ── .env.example tests ────────────────────────────────────────────────────────


class TestEnvExampleWhisperModel(unittest.TestCase):
    """.env.example must document CYRUS_WHISPER_MODEL."""

    _ENV_EXAMPLE = _CYRUS2_DIR / ".env.example"

    def test_env_example_contains_cyrus_whisper_model(self) -> None:
        """AC: CYRUS_WHISPER_MODEL must appear in .env.example."""
        self.assertTrue(
            self._ENV_EXAMPLE.exists(),
            f".env.example not found at {self._ENV_EXAMPLE}",
        )
        content = self._ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn(
            "CYRUS_WHISPER_MODEL",
            content,
            "CYRUS_WHISPER_MODEL must be documented in .env.example",
        )


# ── Module interface tests ────────────────────────────────────────────────────


class TestWhisperModelModuleInterface(unittest.TestCase):
    """WHISPER_MODEL and VALID_WHISPER_MODELS must be importable from cyrus_config."""

    def test_whisper_model_is_importable(self) -> None:
        """AC: WHISPER_MODEL must be importable from cyrus_config."""
        self.assertTrue(
            hasattr(cyrus_config, "WHISPER_MODEL"),
            "cyrus_config is missing WHISPER_MODEL constant",
        )

    def test_valid_whisper_models_is_importable(self) -> None:
        """VALID_WHISPER_MODELS must be importable from cyrus_config."""
        self.assertTrue(
            hasattr(cyrus_config, "VALID_WHISPER_MODELS"),
            "cyrus_config is missing VALID_WHISPER_MODELS constant",
        )

    def test_whisper_model_in_cyrus_voice_source(self) -> None:
        """AC: cyrus_voice.py must import WHISPER_MODEL from cyrus_config.

        The value must not be hardcoded in cyrus_voice.py.
        """
        voice_src = (_CYRUS2_DIR / "cyrus_voice.py").read_text(encoding="utf-8")
        # Must import WHISPER_MODEL from config
        self.assertIn(
            "WHISPER_MODEL",
            voice_src,
            "cyrus_voice.py must reference WHISPER_MODEL from cyrus_config",
        )
        # Must NOT hardcode the value
        self.assertNotIn(
            'WHISPER_MODEL = "medium.en"',
            voice_src,
            "cyrus_voice.py must not hardcode WHISPER_MODEL = 'medium.en'",
        )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
