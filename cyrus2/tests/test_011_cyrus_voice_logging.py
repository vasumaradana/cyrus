"""
Acceptance-driven tests for Issue 011: Replace print() calls in cyrus_voice.py.

These tests verify every acceptance criterion from the issue using static
source-code analysis (grep/AST) rather than runtime execution.  Runtime
testing is impractical because cyrus_voice.py depends on hardware (GPU,
sound devices, microphone), but correctness of the logging migration can be
fully verified by inspecting the source.

Acceptance criteria tested:
  - No remaining print() calls
  - import logging added
  - from cyrus2.cyrus_log import setup_logging added
  - log = logging.getLogger("cyrus.voice") defined at module level
  - setup_logging("cyrus") called inside main()
  - log.info() calls present (for [Voice] prefix patterns)
  - log.error() calls present (for [!] / error patterns)
  - log.warning() calls present (for timeout/fallback patterns)
  - log.debug() calls present (for transcription/TTS debug patterns)
  - exc_info=True present in at least 13 exception handlers
  - No f-strings used in log.*() calls
"""

import re
import unittest
from pathlib import Path

# Path to the file under test
VOICE_PATH = Path(__file__).parent.parent / "cyrus_voice.py"


def _source() -> str:
    """Return the full source text of cyrus_voice.py (cached per process)."""
    return VOICE_PATH.read_text(encoding="utf-8")


class TestVoiceFileExists(unittest.TestCase):
    """Prerequisite: the source file must be present."""

    def test_file_exists(self):
        """AC: cyrus2/cyrus_voice.py must exist."""
        self.assertTrue(
            VOICE_PATH.exists(),
            f"cyrus_voice.py not found at {VOICE_PATH}",
        )


class TestNoPrintCalls(unittest.TestCase):
    """AC: All 32 print() calls replaced — none must remain."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_no_print_calls_remain(self):
        """AC: grep for print( in source must return 0 matches."""
        # Find all lines containing print( (excluding comment lines and docstrings)
        lines_with_print = [
            (i + 1, line)
            for i, line in enumerate(self.src.splitlines())
            if re.search(r"\bprint\s*\(", line) and not line.lstrip().startswith("#")
        ]
        self.assertEqual(
            lines_with_print,
            [],
            f"Found remaining print() calls on lines: "
            f"{[ln for ln, _ in lines_with_print]}",
        )


class TestImports(unittest.TestCase):
    """AC: Required imports must be present."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_logging_import(self):
        """AC: 'import logging' must appear in the file."""
        self.assertIn(
            "import logging",
            self.src,
            "Missing 'import logging' in cyrus_voice.py",
        )

    def test_setup_logging_import(self):
        """AC: 'from cyrus2.cyrus_log import setup_logging' must appear."""
        self.assertIn(
            "from cyrus2.cyrus_log import setup_logging",
            self.src,
            "Missing 'from cyrus2.cyrus_log import setup_logging' in cyrus_voice.py",
        )


class TestLoggerDefinition(unittest.TestCase):
    """AC: Module-level logger 'log' must be defined with the correct name."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_logger_name(self):
        """AC: log = logging.getLogger('cyrus.voice') must be defined."""
        self.assertIn(
            'log = logging.getLogger("cyrus.voice")',
            self.src,
            'Missing: log = logging.getLogger("cyrus.voice") in cyrus_voice.py',
        )

    def test_logger_is_module_level(self):
        """Logger must be defined at module level (not inside a function/class)."""
        lines = self.src.splitlines()
        for i, line in enumerate(lines):
            if 'log = logging.getLogger("cyrus.voice")' in line:
                # Must not be indented (module-level = no leading whitespace)
                self.assertFalse(
                    line.startswith(" ") or line.startswith("\t"),
                    f"Logger defined inside a function/class at line {i + 1}: {line!r}",
                )
                return
        self.fail("Logger definition not found in source")


class TestSetupLoggingInMain(unittest.TestCase):
    """AC: setup_logging('cyrus') must be called inside main()."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_setup_logging_in_main(self):
        """AC: setup_logging('cyrus') must appear inside main()."""
        # Extract the body of main() — everything after 'async def main():'
        # up to the next top-level function definition or EOF
        match = re.search(
            r"^async def main\(\)[^\n]*\n(.*?)(?=^(?:async )?def |\Z)",
            self.src,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, "main() function not found in cyrus_voice.py")
        main_body = match.group(1)
        self.assertIn(
            'setup_logging("cyrus")',
            main_body,
            'setup_logging("cyrus") not called inside main()',
        )


class TestLogLevelCalls(unittest.TestCase):
    """AC: All four log levels must be used in the file."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_info_calls_present(self):
        """AC: [Voice] prefix patterns must use log.info()."""
        self.assertIn(
            "log.info(",
            self.src,
            "No log.info() calls found — [Voice] patterns not converted",
        )

    def test_error_calls_present(self):
        """AC: [!] / error patterns must use log.error()."""
        self.assertIn(
            "log.error(",
            self.src,
            "No log.error() calls found — error patterns not converted",
        )

    def test_warning_calls_present(self):
        """AC: Timeout/fallback patterns must use log.warning()."""
        self.assertIn(
            "log.warning(",
            self.src,
            "No log.warning() calls found — timeout/fallback patterns not converted",
        )

    def test_debug_calls_present(self):
        """AC: Transcription/TTS debug patterns must use log.debug()."""
        self.assertIn(
            "log.debug(",
            self.src,
            "No log.debug() calls found — debug patterns not converted",
        )

    def test_minimum_info_count(self):
        """AC: At least 14 log.info() calls must exist (from conversion table)."""
        count = self.src.count("log.info(")
        self.assertGreaterEqual(
            count,
            14,
            f"Expected ≥14 log.info() calls, found {count}",
        )

    def test_minimum_warning_count(self):
        """AC: At least 6 log.warning() calls must exist (from conversion table)."""
        count = self.src.count("log.warning(")
        self.assertGreaterEqual(
            count,
            6,
            f"Expected ≥6 log.warning() calls, found {count}",
        )

    def test_minimum_error_count(self):
        """AC: At least 2 log.error() calls must exist (from conversion table)."""
        count = self.src.count("log.error(")
        self.assertGreaterEqual(
            count,
            2,
            f"Expected ≥2 log.error() calls, found {count}",
        )

    def test_minimum_debug_count(self):
        """AC: At least 10 log.debug() calls must exist (from conversion table)."""
        count = self.src.count("log.debug(")
        self.assertGreaterEqual(
            count,
            10,
            f"Expected ≥10 log.debug() calls, found {count}",
        )


class TestExcInfo(unittest.TestCase):
    """AC: Exception handlers must use exc_info=True — at least 13 occurrences."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_exc_info_in_exception_handlers(self):
        """AC: At least 13 exc_info=True occurrences in log calls."""
        count = self.src.count("exc_info=True")
        self.assertGreaterEqual(
            count,
            13,
            f"Expected ≥13 exc_info=True occurrences, found {count}",
        )


class TestNoFstringsInLogCalls(unittest.TestCase):
    """AC: All log.*() calls must use %s-style formatting, not f-strings."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_no_fstrings_in_log_calls(self):
        """AC: No f-string inside a log.*() call argument."""
        lines = self.src.splitlines()
        violations = []
        for i, line in enumerate(lines):
            # Match any log call that contains an f-string argument
            if re.search(r"\blog\.\w+\s*\(.*f['\"]", line):
                violations.append((i + 1, line.strip()))
        self.assertEqual(
            violations,
            [],
            f"Found f-strings inside log calls on lines: "
            f"{[ln for ln, _ in violations]}",
        )


class TestSpecificConversions(unittest.TestCase):
    """Spot-check a representative sample of specific conversions."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_tts_timeout_uses_warning(self):
        """TTS timed out message must use log.warning."""
        self.assertIn(
            'log.warning("TTS timed out")',
            self.src,
            "TTS timed out must be log.warning",
        )

    def test_connected_to_brain_uses_info(self):
        """Connected to brain message must use log.info."""
        self.assertIn(
            'log.info("Connected to brain.")',
            self.src,
            "Connected to brain must be log.info",
        )

    def test_tts_worker_error_uses_error(self):
        """TTS worker error must use log.error with exc_info=True."""
        self.assertIn(
            'log.error("TTS worker error: %s", e, exc_info=True)',
            self.src,
            "TTS worker error must be log.error with %s format and exc_info=True",
        )

    def test_hallucination_filtered_uses_debug(self):
        """Hallucination filtered must use log.debug."""
        self.assertIn(
            'log.debug("Hallucination filtered: %s", text[:60])',
            self.src,
            "Hallucination filtered must be log.debug",
        )

    def test_brain_disconnected_uses_warning(self):
        """Brain disconnected reconnecting message must use log.warning."""
        self.assertIn(
            'log.warning("Brain disconnected — reconnecting...")',
            self.src,
            "Brain disconnected must be log.warning",
        )

    def test_signing_off_no_newline_prefix(self):
        """Signing off message must not have \\n prefix."""
        self.assertIn(
            'log.info("Cyrus Voice signing off.")',
            self.src,
            "Signing off must be log.info without \\n prefix",
        )

    def test_ready_streaming_uses_info(self):
        """Ready streaming utterances must use log.info."""
        self.assertIn(
            'log.info("Ready — streaming utterances to brain.")',
            self.src,
            "Ready streaming must be log.info",
        )

    def test_kokoro_load_failed_uses_warning(self):
        """Kokoro load failed must use log.warning with %s format and exc_info=True."""
        self.assertIn(
            'log.warning("Kokoro load failed (%s) — using Edge TTS", e, exc_info=True)',
            self.src,
            "Kokoro load failed must be log.warning with %s format and exc_info=True",
        )

    def test_transcribing_uses_debug(self):
        """Transcribing must use log.debug (no end= or flush=)."""
        self.assertIn(
            'log.debug("Transcribing...")',
            self.src,
            "Transcribing must be log.debug",
        )

    def test_transcribed_result_uses_debug(self):
        """Transcribed result must use log.debug with %s format."""
        # The full call with conditional TTS marker — split for line-length
        expected = (
            'log.debug("Transcribed%s: %s",'
            ' " (during TTS)" if during_tts else "", text)'
        )
        self.assertIn(
            expected,
            self.src,
            "Transcribed result must be log.debug with conditional TTS marker",
        )


class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    @classmethod
    def setUpClass(cls):
        cls.src = _source()

    def test_no_end_flush_args_in_log_calls(self):
        """log.*() calls must not contain end= or flush= (not valid for logging)."""
        lines = self.src.splitlines()
        violations = []
        for i, line in enumerate(lines):
            if re.search(r"\blog\.\w+\s*\(", line) and re.search(
                r"\b(?:end|flush)\s*=", line
            ):
                violations.append((i + 1, line.strip()))
        self.assertEqual(
            violations,
            [],
            f"Found end= or flush= in log calls on lines: "
            f"{[ln for ln, _ in violations]}",
        )

    def test_total_log_call_count(self):
        """Total log.*() call count must be ≥32 (the 32 converted + 13 exc_info)."""
        total = sum(
            self.src.count(f"log.{level}(")
            for level in ("debug", "info", "warning", "error", "critical")
        )
        self.assertGreaterEqual(
            total,
            32,
            f"Expected ≥32 total log.*() calls (32 converted + exc_info),"
            f" found {total}",
        )

    def test_setup_logging_import_before_logger_definition(self):
        """setup_logging import must appear before logger definition in file."""
        import_pos = self.src.find("from cyrus2.cyrus_log import setup_logging")
        logger_pos = self.src.find('log = logging.getLogger("cyrus.voice")')
        self.assertGreater(
            import_pos,
            -1,
            "setup_logging import not found",
        )
        self.assertGreater(
            logger_pos,
            -1,
            "logger definition not found",
        )
        self.assertLess(
            import_pos,
            logger_pos,
            "setup_logging import must appear before logger definition",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
