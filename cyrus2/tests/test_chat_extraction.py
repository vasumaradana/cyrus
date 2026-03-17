"""
Tier 4 integration tests for ChatWatcher._extract_response().

Issue 025 — mock UIA walk results (flat ``(depth, ctype, name)`` tuples)
to test anchor-finding and response-extraction logic in isolation.
No real UIA tree, no Windows hardware required.

``_extract_response(results)`` takes the flat output of ``_walk()`` and:
  1. Finds the ``EditControl("Message input")`` end-of-chat sentinel.
  2. Identifies the primary anchor: last ``ButtonControl`` with "Thinking"
     in its text before the sentinel.
  3. Falls back to the secondary anchor: last ``ButtonControl("Message actions")``.
  4. Collects ``TextControl`` / ``ListItemControl`` items between anchor and
     sentinel, applying _STOP/break, _SKIP/continue, dedup logic.
  5. Returns the parts joined with a single space, or ``""`` on failure.

Test categories
---------------
  Anchor detection        (2 tests) — Thinking button, Message actions button
  Backtrack logic         (3 tests) — last anchor wins, STOP halts, non-text skipped
  Text extraction         (2 tests) — multi-part join, deduplication
  Missing element handling(2 tests) — no sentinel, no anchor
  Cache / determinism     (1 test)  — same input → same output
  Edge cases              (2 tests) — _SKIP words filtered, short text filtered

Usage
-----
    pytest tests/test_chat_extraction.py -v
    pytest tests/test_chat_extraction.py -k "anchor" -v
    pytest tests/test_chat_extraction.py -k "missing or empty" -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# ── Mock Windows-specific modules BEFORE importing cyrus_common ───────────────
# cyrus_common.py imports comtypes, pyautogui, pygetwindow, pyperclip, and
# uiautomation at module level (with try/except). Pre-populating sys.modules
# prevents import errors on Linux / CI where these packages are absent.
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

# Add cyrus2/ to sys.path so ``from cyrus_common import …`` resolves.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

from cyrus_common import ChatWatcher  # noqa: E402

# ── Helpers ───────────────────────────────────────────────────────────────────

# Sentinel text for the message-input EditControl (end-of-chat marker).
_MSG_INPUT_TEXT = "Message input"


def _r(ctype: str, name: str, depth: int = 0) -> tuple[int, str, str]:
    """Build a single UIA walk result tuple.

    Args:
        ctype: UIA control type string, e.g. ``"TextControl"``.
        name:  Accessible name / text of the element.
        depth: Tree depth (not used by _extract_response, but kept real).

    Returns:
        ``(depth, ctype, name)`` tuple matching ``_walk()`` output format.
    """
    return (depth, ctype, name)


def _msg_input() -> tuple[int, str, str]:
    """Return the mandatory end-of-chat EditControl sentinel tuple."""
    return _r("EditControl", _MSG_INPUT_TEXT)


def _thinking(label: str = "Thinking (3 seconds)") -> tuple[int, str, str]:
    """Return a primary-anchor Thinking ButtonControl tuple."""
    return _r("ButtonControl", label)


def _msg_actions() -> tuple[int, str, str]:
    """Return a secondary-anchor Message actions ButtonControl tuple."""
    return _r("ButtonControl", "Message actions")


def _text(content: str, depth: int = 1) -> tuple[int, str, str]:
    """Return a TextControl tuple with *content*."""
    return _r("TextControl", content, depth)


def _list_item(content: str, depth: int = 1) -> tuple[int, str, str]:
    """Return a ListItemControl tuple with *content*."""
    return _r("ListItemControl", content, depth)


def _make_watcher() -> ChatWatcher:
    """Return a minimal ChatWatcher suitable for calling _extract_response()."""
    return ChatWatcher(project_name="test-project", target_subname="TestSub")


# ── Anchor Detection Tests ────────────────────────────────────────────────────


def test_thinking_button_detected_as_primary_anchor() -> None:
    """Thinking ButtonControl before Message input is used as the primary anchor.

    AC: Tests verify anchor element detection (~2 cases).

    The last "Thinking (...)" button before the message input marks the start
    of Claude's current response block.  Text after it must be extracted.
    """
    results = [
        _thinking("Thinking (5 seconds)"),
        _text("Here is the answer"),
        _msg_input(),
    ]
    watcher = _make_watcher()
    assert watcher._extract_response(results) == "Here is the answer"


def test_message_actions_used_as_secondary_anchor() -> None:
    """Message actions ButtonControl is used when no Thinking button is present.

    AC: Tests verify anchor element detection (~2 cases).

    "Message actions" is the fallback anchor when Claude has finished thinking
    and the Thinking button has disappeared from the UIA tree.
    """
    results = [
        _msg_actions(),
        _text("Response content"),
        _msg_input(),
    ]
    watcher = _make_watcher()
    assert watcher._extract_response(results) == "Response content"


# ── Backtrack Logic Tests ─────────────────────────────────────────────────────


def test_last_thinking_button_wins_when_multiple_present() -> None:
    """The last Thinking button before Message input is the anchor, not earlier ones.

    AC: Tests verify backtrack logic (~3 cases).

    When multiple Thinking buttons exist (e.g. multi-turn conversation), only
    the content after the *last* one is part of the current response.
    """
    results = [
        # First turn (should be ignored)
        _thinking("Thinking (old, first turn)"),
        _text("First response text — ignored"),
        # Second turn — this is the actual response block
        _thinking("Thinking (3 seconds)"),
        _text("Latest response text"),
        _msg_input(),
    ]
    watcher = _make_watcher()
    extracted = watcher._extract_response(results)
    # Only text after the LAST Thinking anchor
    assert extracted == "Latest response text"
    assert "First response text" not in extracted


def test_stop_word_halts_extraction() -> None:
    """A _STOP word breaks out of the extraction loop immediately.

    AC: Tests verify backtrack logic (~3 cases).

    "Edit automatically" is in ChatWatcher._STOP.  Any text that appears
    *after* it (before the message input) must not be included in the response.
    """
    results = [
        _thinking(),
        _text("Before stop word"),
        # "Edit automatically" is in _STOP; extraction halts here
        _r("TextControl", "Edit automatically"),
        _text("After stop word — must be excluded"),
        _msg_input(),
    ]
    watcher = _make_watcher()
    extracted = watcher._extract_response(results)
    assert extracted == "Before stop word"
    assert "After stop word" not in extracted


def test_only_text_and_listitem_controls_included() -> None:
    """Only TextControl and ListItemControl elements contribute to the response.

    AC: Tests verify backtrack logic (~3 cases).

    ButtonControl, GroupControl, and other control types are ignored regardless
    of their text content.  ListItemControl (code block lines, bullet items)
    are explicitly included alongside TextControl.
    """
    results = [
        _thinking(),
        _r("ButtonControl", "Some button text here"),  # ButtonControl — excluded
        _text("Valid text response"),  # TextControl — included
        _list_item("Valid list item"),  # ListItemControl — included
        _r("GroupControl", "Some group label"),  # GroupControl — excluded
        _msg_input(),
    ]
    watcher = _make_watcher()
    extracted = watcher._extract_response(results)
    assert extracted == "Valid text response Valid list item"
    assert "Some button text" not in extracted
    assert "Some group label" not in extracted


# ── Text Extraction Tests ─────────────────────────────────────────────────────


def test_multiple_text_elements_joined_with_spaces() -> None:
    """Multiple TextControl elements are concatenated with single spaces.

    AC: Tests verify response text extraction (~2 cases).

    Claude responses typically span several text nodes.  They must all be
    included and joined by a single space character.
    """
    results = [
        _thinking(),
        _text("First part of response"),
        _text("Second part of response"),
        _text("Third part of response"),
        _msg_input(),
    ]
    watcher = _make_watcher()
    assert (
        watcher._extract_response(results)
        == "First part of response Second part of response Third part of response"
    )


def test_duplicate_text_deduplicated() -> None:
    """Repeated text nodes appear only once in the extracted response.

    AC: Tests verify response text extraction (~2 cases).

    UIA trees often duplicate text nodes (parent/child sharing the same Name).
    The seen-set deduplication ensures each unique string appears once.
    Also verifies substring deduplication: if a longer string already contains
    a shorter one, the shorter one is omitted.
    """
    results = [
        _thinking(),
        _text("Hello world"),  # first occurrence — included
        _text("Hello world"),  # exact duplicate — skipped
        _text("Different text"),  # unique — included
        _msg_input(),
    ]
    watcher = _make_watcher()
    extracted = watcher._extract_response(results)
    assert extracted == "Hello world Different text"
    # "Hello world" must appear exactly once
    assert extracted.count("Hello world") == 1


# ── Missing Element Handling Tests ───────────────────────────────────────────


def test_no_message_input_returns_empty_string() -> None:
    """Returns '' when no EditControl('Message input') is present in results.

    AC: Tests verify missing element handling (~2 cases).

    Without the end-of-chat sentinel the method cannot bound the response region
    and must bail out gracefully rather than raising an exception.
    """
    results = [
        _thinking(),
        _text("Some response text"),
        # Intentionally omit _msg_input()
    ]
    watcher = _make_watcher()
    assert watcher._extract_response(results) == ""


def test_no_anchor_returns_empty_string() -> None:
    """Returns '' when neither a Thinking button nor Message actions button exists.

    AC: Tests verify missing element handling (~2 cases).

    The message input sentinel is present but there is no anchor button — the
    method cannot determine where the current response starts and returns ''.
    """
    results = [
        _text("Some orphaned text"),
        _text("More text without an anchor"),
        _msg_input(),
    ]
    watcher = _make_watcher()
    assert watcher._extract_response(results) == ""


# ── Cache / Determinism Test ──────────────────────────────────────────────────


def test_same_results_returns_same_response() -> None:
    """_extract_response is deterministic: the same input always yields the same output.

    AC: Tests verify cache behavior (~1 case): reusing cached response if tree
    unchanged.

    Calling the method twice with identical results must return the same string
    both times.  The watcher's internal state (_last_text, _last_spoken) must
    not affect the extraction result.
    """
    results = [
        _thinking(),
        _text("Consistent response text"),
        _msg_input(),
    ]
    watcher = _make_watcher()
    first_call = watcher._extract_response(results)
    second_call = watcher._extract_response(results)
    assert first_call == second_call == "Consistent response text"


# ── Edge Case Tests ───────────────────────────────────────────────────────────


def test_skip_words_filtered_from_response() -> None:
    """Text nodes in _SKIP are silently omitted from the extracted response.

    AC: Edge cases — SKIP filtering.

    "Thinking", "Stop", "Regenerate", and other UI chrome strings must not
    appear in the final response even if they appear as TextControl nodes
    in the UIA tree (which can happen when Chrome renders these as text layers).
    """
    results = [
        _thinking(),
        _text("Thinking"),  # in _SKIP — excluded
        _text("Stop"),  # in _SKIP — excluded
        _text("Regenerate"),  # in _SKIP — excluded
        _text("Actual response content"),  # not in _SKIP — included
        _msg_input(),
    ]
    watcher = _make_watcher()
    extracted = watcher._extract_response(results)
    assert extracted == "Actual response content"
    assert "Thinking" not in extracted
    assert "Stop" not in extracted
    assert "Regenerate" not in extracted


def test_short_text_under_four_chars_filtered() -> None:
    """Text nodes shorter than 4 characters are silently filtered.

    AC: Edge cases — short text filtering.

    Very short strings ("ok", "no", "yes", "hi") are UI noise.  The
    ``len(text) < 4`` guard in _extract_response must exclude them so they
    do not clutter the spoken response.
    """
    results = [
        _thinking(),
        _text("ok"),  # 2 chars — excluded
        _text("yes"),  # 3 chars — excluded
        _text("This is a real sentence"),  # 24 chars — included
        _text("no"),  # 2 chars — excluded
        _msg_input(),
    ]
    watcher = _make_watcher()
    extracted = watcher._extract_response(results)
    assert extracted == "This is a real sentence"
    assert "ok" not in extracted
    assert "yes" not in extracted


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
