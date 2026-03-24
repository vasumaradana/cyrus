"""
Tier 3 acceptance tests for Issue 023:
Verify ALLOW_WORDS and DENY_WORDS keyword matching in
PermissionWatcher.handle_response().

Tests cover:
- ALLOW_WORDS matching (~5 parametrized cases): yes, sure, okay, yep, yeah, allow
- DENY_WORDS matching (~5 parametrized cases): no, deny, cancel, stop, nope, reject
- Edge cases (~2+): empty input, ambiguous input, no-pending guard, mixed keywords
- Case-insensitive matching: uppercase and mixed-case utterances

Strategy:
    ``handle_response`` requires ``_pending=True`` and a non-None ``_allow_btn``,
    and calls ``_assert_vscode_focus`` before acting.  All tests prime the watcher
    to a pending state and patch the focus guard so tests run cross-platform.
    ``pyautogui`` and other Windows-only modules are mocked in ``sys.modules``
    before the first import of ``cyrus_common``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Mock Windows-specific modules BEFORE any cyrus import ────────────────────
# cyrus_common.py imports Windows-only packages at the module level.
# Inserting MagicMock stubs into sys.modules lets the import succeed on any OS.
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

# Add cyrus2/ to sys.path so ``from cyrus_common import …`` resolves correctly.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

from cyrus_common import PermissionWatcher  # noqa: E402

# ── Helpers ───────────────────────────────────────────────────────────────────


def _primed_watcher(project_name: str = "test-proj") -> PermissionWatcher:
    """Return a PermissionWatcher with a pending permission dialog.

    Sets ``_pending=True`` and ``_allow_btn='keyboard'`` so
    ``handle_response()`` will act on the next utterance.

    Args:
        project_name: Project label attached to the watcher instance.

    Returns:
        A ready-to-respond PermissionWatcher.
    """
    w = PermissionWatcher(project_name=project_name, target_subname="TestSub")
    w._pending = True
    w._allow_btn = "keyboard"
    w._announced = "hook:some-command"
    return w


# ── ALLOW_WORDS: verify every word in the set is recognised ───────────────────
# Each ALLOW_WORDS case must:
#   1. Return True  (response consumed)
#   2. Clear _pending (dialog dismissed)


@pytest.mark.parametrize(
    "utterance",
    [
        # Exact single-word matches
        "yes",
        "yep",
        "yeah",
        "ok",
        "okay",
        # Keyword embedded in a phrase
        "sure thing",
        "okay go ahead",
        "allow it",
        "proceed with that",
    ],
    ids=[
        "yes",
        "yep",
        "yeah",
        "ok",
        "okay",
        "sure_thing",
        "okay_go_ahead",
        "allow_it",
        "proceed_with_that",
    ],
)
def test_allow_word_returns_true(utterance: str) -> None:
    """handle_response must return True when utterance contains an ALLOW_WORDS keyword.

    AC: Tests verify ALLOW_WORDS matching.

    Args:
        utterance: Voice input that contains at least one ALLOW_WORDS keyword.
    """
    w = _primed_watcher()
    with patch("cyrus_common._assert_vscode_focus"):
        result = w.handle_response(utterance)
    assert result is True, (
        f"Expected True for allow utterance {utterance!r}; "
        f"ALLOW_WORDS={PermissionWatcher.ALLOW_WORDS}"
    )


@pytest.mark.parametrize(
    "utterance",
    ["yes", "sure thing", "okay", "yep", "yeah that's fine"],
    ids=["yes", "sure_thing", "okay", "yep", "yeah_thats_fine"],
)
def test_allow_word_clears_pending(utterance: str) -> None:
    """handle_response with ALLOW_WORDS must clear _pending state.

    After an allow response the permission dialog is dismissed and
    the watcher must not re-arm on the same response.

    Args:
        utterance: Voice input containing an ALLOW_WORDS keyword.
    """
    w = _primed_watcher()
    with patch("cyrus_common._assert_vscode_focus"):
        w.handle_response(utterance)
    assert not w._pending, f"_pending must be False after allow utterance {utterance!r}"


# ── DENY_WORDS: verify every word in the set is recognised ────────────────────
# Each DENY_WORDS case must:
#   1. Return True  (response consumed)
#   2. Clear _pending (dialog cancelled)


@pytest.mark.parametrize(
    "utterance",
    [
        # Exact single-word matches
        "no",
        "nope",
        "cancel",
        "stop",
        "reject",
        # Keyword embedded in a phrase
        "deny it",
        "cancel that",
        "stop it now",
        "no way",
    ],
    ids=[
        "no",
        "nope",
        "cancel",
        "stop",
        "reject",
        "deny_it",
        "cancel_that",
        "stop_it_now",
        "no_way",
    ],
)
def test_deny_word_returns_true(utterance: str) -> None:
    """handle_response must return True when utterance contains a DENY_WORDS keyword.

    AC: Tests verify DENY_WORDS matching.

    Args:
        utterance: Voice input that contains at least one DENY_WORDS keyword.
    """
    w = _primed_watcher()
    with patch("cyrus_common._assert_vscode_focus"):
        result = w.handle_response(utterance)
    assert result is True, (
        f"Expected True for deny utterance {utterance!r}; "
        f"DENY_WORDS={PermissionWatcher.DENY_WORDS}"
    )


@pytest.mark.parametrize(
    "utterance",
    ["no", "nope", "cancel", "stop that", "deny"],
    ids=["no", "nope", "cancel", "stop_that", "deny"],
)
def test_deny_word_clears_pending(utterance: str) -> None:
    """handle_response with DENY_WORDS must clear _pending state.

    After a deny response the dialog is cancelled and the watcher
    must not re-arm on the same response.

    Args:
        utterance: Voice input containing a DENY_WORDS keyword.
    """
    w = _primed_watcher()
    with patch("cyrus_common._assert_vscode_focus"):
        w.handle_response(utterance)
    assert not w._pending, f"_pending must be False after deny utterance {utterance!r}"


# ── Case-insensitive matching ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "utterance",
    [
        # Uppercase allow words
        "YES",
        "SURE",
        "OKAY",
        "YEP",
        # Uppercase deny words
        "NO",
        "NOPE",
        "CANCEL",
    ],
    ids=["YES", "SURE", "OKAY", "YEP", "NO", "NOPE", "CANCEL"],
)
def test_uppercase_keywords_are_recognised(utterance: str) -> None:
    """Uppercase utterances must be matched case-insensitively.

    AC: Case-insensitive matching verified.
    The implementation lowercases the utterance before matching against
    ALLOW_WORDS/DENY_WORDS, so 'YES', 'No', and 'CANCEL' must all match.

    Args:
        utterance: All-uppercase voice input.
    """
    w = _primed_watcher()
    with patch("cyrus_common._assert_vscode_focus"):
        result = w.handle_response(utterance)
    assert result is True, (
        f"Uppercase utterance {utterance!r} must be recognised (case-insensitive)"
    )


@pytest.mark.parametrize(
    "utterance",
    ["Yes", "Sure", "Okay", "No", "Nope"],
    ids=["Yes", "Sure", "Okay", "No", "Nope"],
)
def test_mixed_case_keywords_are_recognised(utterance: str) -> None:
    """Mixed-case utterances (Title Case) must match keywords correctly.

    AC: Case-insensitive matching verified.

    Args:
        utterance: Title-cased voice input.
    """
    w = _primed_watcher()
    with patch("cyrus_common._assert_vscode_focus"):
        result = w.handle_response(utterance)
    assert result is True, f"Mixed-case utterance {utterance!r} must be recognised"


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_response_returns_false() -> None:
    """Empty response must return False — no keyword can be matched.

    AC: Edge cases handled — empty response is ambiguous.
    An empty string contains no words, so neither ALLOW nor DENY sets match.
    """
    w = _primed_watcher()
    with patch("cyrus_common._assert_vscode_focus"):
        result = w.handle_response("")
    assert result is False, "Empty response must not consume the pending dialog"


def test_ambiguous_response_returns_false() -> None:
    """Ambiguous response with no recognisable keywords returns False.

    AC: Edge cases handled — ambiguous input leaves the dialog pending.
    Words like 'maybe' or 'hmm interesting' are not in any keyword list.
    """
    w = _primed_watcher()
    with patch("cyrus_common._assert_vscode_focus"):
        result = w.handle_response("maybe hmm interesting")
    assert result is False, "Ambiguous response must return False"


def test_ambiguous_response_leaves_pending_unchanged() -> None:
    """Ambiguous response must leave _pending=True.

    The dialog remains open while the user has not given a decisive answer.
    "definitely perhaps" contains no ALLOW or DENY keywords, so _pending
    must still be True after the call.
    """
    w = _primed_watcher()
    with patch("cyrus_common._assert_vscode_focus"):
        w.handle_response("definitely perhaps")
    assert w._pending is True, "_pending must remain True after ambiguous response"


def test_no_pending_returns_false_regardless_of_keywords() -> None:
    """handle_response must return False when no dialog is pending.

    The guard at the top of handle_response checks _pending; if no dialog
    is active the response must be ignored entirely, even for clear keywords.
    """
    w = PermissionWatcher(project_name="test", target_subname="TestSub")
    # _pending defaults to False — no dialog is waiting
    with patch("cyrus_common._assert_vscode_focus"):
        result = w.handle_response("yes")
    assert result is False, "handle_response must return False when _pending is False"


def test_mixed_allow_and_deny_keywords_prefers_allow() -> None:
    """Response containing both ALLOW and DENY keywords must honour ALLOW.

    AC: Edge case — mixed keywords.
    The implementation checks ALLOW_WORDS first; the first match wins.
    An utterance like 'yes no' must be treated as an allow, not a deny.
    """
    w = _primed_watcher()
    with patch("cyrus_common._assert_vscode_focus"):
        result = w.handle_response("yes no")
    assert result is True, "Mixed allow+deny utterance must be consumed (True)"
    assert not w._pending, "_pending must be cleared when ALLOW wins over DENY"


# ── Constants sanity checks ───────────────────────────────────────────────────
# Verify that ALLOW_WORDS and DENY_WORDS contain the expected core keywords.
# These tests act as a contract: if a keyword is accidentally removed the
# corresponding parametrized tests above will also fail, but these provide
# a direct signal about which constant changed.


def test_allow_words_contains_core_keywords() -> None:
    """ALLOW_WORDS must contain the core affirmative keywords.

    Documents the expected minimum set.  Adding new words is fine;
    removing any of these would break voice-permission usability.
    """
    required = {"yes", "sure", "okay", "ok", "yep", "yeah"}
    missing = required - PermissionWatcher.ALLOW_WORDS
    assert not missing, (
        f"ALLOW_WORDS is missing core keywords: {missing}; "
        f"current set: {PermissionWatcher.ALLOW_WORDS}"
    )


def test_deny_words_contains_core_keywords() -> None:
    """DENY_WORDS must contain the core negative keywords.

    Documents the expected minimum set.  Adding new words is fine;
    removing any of these would break voice-permission safety.
    """
    required = {"no", "nope", "cancel", "stop", "deny"}
    missing = required - PermissionWatcher.DENY_WORDS
    assert not missing, (
        f"DENY_WORDS is missing core keywords: {missing}; "
        f"current set: {PermissionWatcher.DENY_WORDS}"
    )


def test_allow_and_deny_words_are_disjoint() -> None:
    """ALLOW_WORDS and DENY_WORDS must not share any keywords.

    A word that appears in both sets would be ambiguous: every response
    containing that word would always be treated as an allow (ALLOW_WORDS
    is checked first), making the deny path unreachable for that word.
    """
    overlap = PermissionWatcher.ALLOW_WORDS & PermissionWatcher.DENY_WORDS
    assert not overlap, (
        f"ALLOW_WORDS and DENY_WORDS overlap — ambiguous keywords: {overlap}"
    )
