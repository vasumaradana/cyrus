"""Tier 1 pure function tests for text processing.

Covers clean_for_speech(), _sanitize_for_speech(), and _strip_fillers()
from cyrus_common.py. Zero mocking required — these are pure functions.

References:
  - cyrus_common.py lines 240-286 (where all three functions are defined)
  - cyrus_brain.py lines 76-97 (imports these from cyrus_common)
  - cyrus_voice.py lines 111-122 (_strip_fillers: identical local copy)

Note on imports: All three functions are defined in cyrus_common.py.
cyrus_brain.py re-exports them. cyrus_voice.py has an identical local copy
of _strip_fillers. We import directly from cyrus_common to avoid the
Windows-only (UIA/COM) and heavy audio (torch/pygame/sounddevice) deps
that cyrus_brain.py and cyrus_voice.py pull in at import time.
cyrus_common handles missing platform deps gracefully via try/except.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add cyrus2/ to sys.path so `import cyrus_common` resolves correctly.
# cyrus_common wraps Windows-only packages in try/except, so it imports
# cleanly on any platform without mocking.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

from cyrus_common import (  # noqa: E402
    _sanitize_for_speech,
    _strip_fillers,
    clean_for_speech,
)

# ── test_clean_for_speech ─────────────────────────────────────────────────────


class TestCleanForSpeech:
    """Tier 1 tests for clean_for_speech(): markdown stripping and TTS prep."""

    # ── Markdown: headers ────────────────────────────────────────────────────

    def test_clean_for_speech_strips_h1_header(self) -> None:
        """# Header text → Header text (leading # and space removed)."""
        result = clean_for_speech("# Hello World")
        assert result == "Hello World"

    def test_clean_for_speech_strips_h3_header(self) -> None:
        """### Subheader stripped — any heading level 1-6."""
        result = clean_for_speech("### Section Title")
        assert result == "Section Title"

    # ── Markdown: emphasis ───────────────────────────────────────────────────

    def test_clean_for_speech_strips_bold(self) -> None:
        """**bold text** → bold text (double asterisks removed)."""
        result = clean_for_speech("This is **bold text** here.")
        assert result == "This is bold text here."

    def test_clean_for_speech_strips_italic(self) -> None:
        """*italic text* → italic text (single asterisks removed)."""
        result = clean_for_speech("Use *italic* for emphasis.")
        assert result == "Use italic for emphasis."

    def test_clean_for_speech_strips_bold_italic(self) -> None:
        """***bold italic*** → bold italic (triple asterisks removed)."""
        result = clean_for_speech("***bold italic*** phrase.")
        assert result == "bold italic phrase."

    # ── Markdown: code blocks ────────────────────────────────────────────────

    def test_clean_for_speech_replaces_fenced_code_block(self) -> None:
        """Fenced ``` code block is replaced with spoken placeholder."""
        text = "Here is the code:\n```python\nprint('hello')\n```\nDone."
        result = clean_for_speech(text)
        assert "See the chat for the code." in result
        # Code content must not be read aloud
        assert "print" not in result

    def test_clean_for_speech_replaces_multiline_code_block(self) -> None:
        """Multiline code block replaced entirely with placeholder text."""
        text = "```\nline 1\nline 2\nline 3\n```"
        result = clean_for_speech(text)
        assert result == "See the chat for the code."

    def test_clean_for_speech_strips_inline_code_keeps_text(self) -> None:
        """Inline `code` → code (backticks stripped, inner text preserved)."""
        result = clean_for_speech("Call the `setup()` function.")
        assert result == "Call the setup() function."

    # ── Markdown: links ──────────────────────────────────────────────────────

    def test_clean_for_speech_replaces_markdown_link_with_text(self) -> None:
        """[link text](https://url) → link text (URL dropped)."""
        result = clean_for_speech("See [the docs](https://example.com) for details.")
        assert result == "See the docs for details."

    # ── Markdown: lists ──────────────────────────────────────────────────────

    def test_clean_for_speech_converts_bullet_list_to_prose(self) -> None:
        """Bullet list items converted to '. item' prose for natural speech."""
        text = "Options:\n- first\n- second"
        result = clean_for_speech(text)
        assert ". first" in result
        assert ". second" in result

    def test_clean_for_speech_converts_numbered_list_to_prose(self) -> None:
        """Numbered list items converted to '. item' prose."""
        text = "Steps:\n1. run tests\n2. commit"
        result = clean_for_speech(text)
        assert ". run tests" in result
        assert ". commit" in result

    def test_clean_for_speech_strips_horizontal_rule(self) -> None:
        """Horizontal rule (---) surrounded by newlines is replaced with space."""
        text = "Section one.\n---\nSection two."
        result = clean_for_speech(text)
        assert "---" not in result
        assert "Section one." in result
        assert "Section two." in result

    # ── Truncation ───────────────────────────────────────────────────────────

    def test_clean_for_speech_truncates_at_default_max_words(self) -> None:
        """Text longer than 50 words is truncated with 'See the chat' suffix."""
        long_text = " ".join(["word"] * 55)  # 55 words > 50 default
        result = clean_for_speech(long_text)
        assert result.endswith(". See the chat for the full response.")
        # First 50 words must be preserved
        prefix = " ".join(["word"] * 50)
        assert result.startswith(prefix)

    def test_clean_for_speech_respects_custom_max_words(self) -> None:
        """max_words=5 truncates after exactly 5 words."""
        text = "one two three four five six seven eight"
        result = clean_for_speech(text, max_words=5)
        assert "See the chat for the full response." in result
        assert result.startswith("one two three four five")

    def test_clean_for_speech_does_not_truncate_under_limit(self) -> None:
        """Text at or below max_words is returned without the truncation suffix."""
        text = " ".join(["word"] * 10)
        result = clean_for_speech(text, max_words=20)
        assert "See the chat" not in result

    # ── Edge cases ───────────────────────────────────────────────────────────

    def test_clean_for_speech_empty_string_returns_empty(self) -> None:
        """Empty string input returns empty string."""
        assert clean_for_speech("") == ""

    def test_clean_for_speech_normalizes_multiple_spaces(self) -> None:
        """Multiple consecutive spaces are collapsed to a single space."""
        result = clean_for_speech("Hello   world  here.")
        assert "  " not in result
        assert result == "Hello world here."

    def test_clean_for_speech_plain_text_preserved(self) -> None:
        """Plain text with no markdown passes through unchanged."""
        result = clean_for_speech("This is plain text.")
        assert result == "This is plain text."

    def test_clean_for_speech_sanitizes_unicode_em_dash(self) -> None:
        """Em dash in text is sanitized — delegates to _sanitize_for_speech."""
        result = clean_for_speech("A\u2014B")  # A—B
        # Em dash must be removed
        assert "\u2014" not in result
        # Surrounding text preserved
        assert "A" in result and "B" in result


# ── test_sanitize_for_speech ──────────────────────────────────────────────────


class TestSanitizeForSpeech:
    """Tier 1 tests for _sanitize_for_speech(): Unicode → TTS-safe replacements."""

    @pytest.mark.parametrize(
        "input_char,expected_replacement",
        [
            ("\u2014", ", "),  # em dash → ", "
            ("\u2013", ", "),  # en dash → ", "
            ("\u2026", "..."),  # ellipsis → "..."
            ("\u2018", "'"),  # left single quote → "'"
            ("\u2019", "'"),  # right single quote → "'"
            ("\u201c", '"'),  # left double quote → '"'
            ("\u201d", '"'),  # right double quote → '"'
            ("\u2022", ", "),  # bullet point → ", "
        ],
        ids=[
            "em_dash",
            "en_dash",
            "ellipsis",
            "left_single_quote",
            "right_single_quote",
            "left_double_quote",
            "right_double_quote",
            "bullet",
        ],
    )
    def test_sanitize_for_speech_replaces_unicode_char(
        self, input_char: str, expected_replacement: str
    ) -> None:
        """Each problematic Unicode char is replaced with its TTS-safe equivalent."""
        result = _sanitize_for_speech(f"before{input_char}after")
        # Original Unicode char must be absent
        assert input_char not in result
        # Expected replacement must be present
        assert expected_replacement in result

    def test_sanitize_for_speech_plain_ascii_unchanged(self) -> None:
        """Plain ASCII text with no special chars passes through unchanged."""
        text = "Hello, world! This is a test."
        assert _sanitize_for_speech(text) == text

    def test_sanitize_for_speech_empty_string(self) -> None:
        """Empty string input returns empty string."""
        assert _sanitize_for_speech("") == ""

    def test_sanitize_for_speech_multiple_substitutions_in_one_string(self) -> None:
        """All Unicode chars in a mixed string are replaced in a single call."""
        # String: He said "Hello"—nice to meet you…
        text = "He said\u201cHello\u201d\u2014nice to meet you\u2026"
        result = _sanitize_for_speech(text)
        assert "\u201c" not in result  # left double quote gone
        assert "\u201d" not in result  # right double quote gone
        assert "\u2014" not in result  # em dash gone
        assert "\u2026" not in result  # ellipsis gone
        # Core words preserved
        assert "Hello" in result
        assert "nice to meet you" in result

    def test_sanitize_for_speech_preserves_normal_ascii_quotes(self) -> None:
        """Regular ASCII single and double quotes are left unchanged."""
        text = "She said 'hello' and \"goodbye\"."
        assert _sanitize_for_speech(text) == text


# ── test_strip_fillers ────────────────────────────────────────────────────────


class TestStripFillers:
    """Tier 1 tests for _strip_fillers(): leading voice filler word removal."""

    @pytest.mark.parametrize(
        "filler_prefix",
        [
            "um ",  # "um" + space
            "uh ",  # "uh" + space
            "uhh ",  # extended uh (uh+ regex: one or more h's)
            "umm ",  # extended um (um+ regex: one or more m's)
            "er ",  # "er" + space
            "so ",  # "so" + space
            "okay ",  # "okay" + space
            "ok ",  # "ok" + space
            "right ",  # "right" + space
            "hey ",  # "hey" + space
            "please ",  # "please" + space
            "can you ",  # multi-word filler
            "could you ",  # multi-word filler
            "would you ",  # multi-word filler
        ],
        ids=[
            "um",
            "uh",
            "uhh",
            "umm",
            "er",
            "so",
            "okay",
            "ok",
            "right",
            "hey",
            "please",
            "can_you",
            "could_you",
            "would_you",
        ],
    )
    def test_strip_fillers_removes_leading_filler(self, filler_prefix: str) -> None:
        """Each filler word+space prefix is stripped from the utterance start."""
        text = f"{filler_prefix}fix this bug"
        result = _strip_fillers(text)
        assert result == "fix this bug", (
            f"Expected 'fix this bug', got {result!r} for input {text!r}"
        )

    def test_strip_fillers_no_filler_returns_unchanged(self) -> None:
        """Text with no leading filler words is returned unchanged."""
        text = "run the test suite"
        assert _strip_fillers(text) == text

    def test_strip_fillers_stacked_fillers_all_removed(self) -> None:
        """Multiple consecutive leading fillers are all stripped
        ('um uh okay X' → 'X')."""
        result = _strip_fillers("um uh okay fix it")
        assert result == "fix it"

    def test_strip_fillers_case_insensitive(self) -> None:
        """Filler removal is case-insensitive — UM, Okay, OK all stripped."""
        assert _strip_fillers("UM fix this") == "fix this"
        assert _strip_fillers("Okay run that") == "run that"
        assert _strip_fillers("OK let's go") == "let's go"

    def test_strip_fillers_non_leading_filler_not_stripped(self) -> None:
        """Filler words in the middle of an utterance are NOT removed."""
        # "the" is not a filler, so the "um" and "so" in the middle are kept
        text = "the um so thing"
        assert _strip_fillers(text) == text

    def test_strip_fillers_empty_string(self) -> None:
        """Empty string input returns empty string."""
        assert _strip_fillers("") == ""

    def test_strip_fillers_multi_word_filler_unit(self) -> None:
        """Multi-word filler 'can you' is stripped as a single unit."""
        result = _strip_fillers("can you explain this error")
        assert result == "explain this error"

    def test_strip_fillers_filler_without_trailing_space_not_stripped(self) -> None:
        """Filler word alone (no trailing whitespace) is NOT stripped.

        The regex requires \\s+ after the filler — 'um' alone doesn't match.
        """
        # "um" alone has no trailing space → doesn't satisfy \s+ requirement
        assert _strip_fillers("um") == "um"
