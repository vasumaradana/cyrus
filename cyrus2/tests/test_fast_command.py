"""
Tier 1 pure-function tests for _fast_command() meta-command routing.

Issue 021 — Write test_fast_command.py (Tier 1)

_fast_command() is a zero-dependency regex router. Given a raw utterance string
it either returns a flat command dict or None. No mocking is needed — every test
is a direct function call followed by an assertion.

Command types and expected dict keys:
  pause         — optional 'duration' (int)
  unlock        — optional 'password' (str)
  which_project — no extra keys
  last_message  — no extra keys
  switch        — required 'project' (str)
  rename        — required 'name' (str); optional 'old' (str, rename-by-hint)

Organisation: one TestCase class per command type + one for non-command paths.
Parametrised cases use subTest() so each variation reports independently.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# ── Mock Windows-specific modules BEFORE any cyrus import ─────────────────────
# cyrus_common.py performs conditional imports of comtypes / uiautomation.
# We pre-populate sys.modules so the import path that would raise ImportError
# on non-Windows is short-circuited cleanly.
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

from cyrus_common import _fast_command  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _cmd(text: str) -> dict | None:
    """Thin wrapper so tests read as 'cmd("pause") → {"command": "pause"}'."""
    return _fast_command(text)


# ─────────────────────────────────────────────────────────────────────────────
# pause
# ─────────────────────────────────────────────────────────────────────────────


class TestPauseCommand(unittest.TestCase):
    """_fast_command recognises pause / resume utterances."""

    def test_pause_bare(self):
        """'pause' → {command: 'pause'} with no duration key."""
        result = _cmd("pause")
        self.assertEqual(result, {"command": "pause"})

    def test_resume_maps_to_pause(self):
        """'resume' is treated as toggling pause state."""
        result = _cmd("resume")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "pause")

    def test_stop_listening(self):
        """'stop listening' triggers pause command."""
        result = _cmd("stop listening")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "pause")

    def test_pause_with_duration_seconds(self):
        """'pause for 10 seconds' → {command: 'pause', duration: 10}."""
        result = _cmd("pause for 10 seconds")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "pause")
        self.assertEqual(result["duration"], 10)

    def test_pause_with_duration_second_singular(self):
        """'pause for 1 second' handles singular form."""
        result = _cmd("pause for 1 second")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "pause")
        self.assertEqual(result["duration"], 1)

    def test_pause_with_duration_is_int(self):
        """Duration value must be an int, not a string."""
        result = _cmd("pause for 30 seconds")
        self.assertIsNotNone(result)
        self.assertIsInstance(result["duration"], int)

    def test_pausable_is_not_a_command(self):
        """'pausable' is a partial match — must NOT trigger pause."""
        result = _cmd("pausable")
        self.assertIsNone(result)

    def test_pause_with_trailing_punctuation(self):
        """Trailing punctuation is stripped before matching."""
        result = _cmd("pause.")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "pause")


# ─────────────────────────────────────────────────────────────────────────────
# unlock
# ─────────────────────────────────────────────────────────────────────────────


class TestUnlockCommand(unittest.TestCase):
    """_fast_command recognises unlock / auto routing utterances."""

    def test_unlock_bare(self):
        """'unlock' alone → {command: 'unlock'} with no password key."""
        result = _cmd("unlock")
        self.assertEqual(result, {"command": "unlock"})

    def test_auto_maps_to_unlock(self):
        """'auto' is an alias for unlock/follow-focus mode."""
        result = _cmd("auto")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "unlock")

    def test_follow_focus_maps_to_unlock(self):
        """'follow focus' enables auto-routing (unlock)."""
        result = _cmd("follow focus")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "unlock")

    def test_unlock_with_password(self):
        """'unlock mypassword' → {command: 'unlock', password: 'mypassword'}."""
        result = _cmd("unlock mypassword")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "unlock")
        self.assertEqual(result["password"], "mypassword")

    def test_unlock_password_is_string(self):
        """Password value must be a str."""
        result = _cmd("unlock hunter2")
        self.assertIsNotNone(result)
        self.assertIsInstance(result["password"], str)

    def test_unlock_case_insensitive(self):
        """Input is normalised to lowercase before matching."""
        result = _cmd("UNLOCK")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "unlock")


# ─────────────────────────────────────────────────────────────────────────────
# which_project
# ─────────────────────────────────────────────────────────────────────────────


class TestWhichProjectCommand(unittest.TestCase):
    """_fast_command recognises 'which/what project/session' queries."""

    def test_which_project(self):
        """'which project' → {command: 'which_project'}."""
        result = _cmd("which project")
        self.assertEqual(result, {"command": "which_project"})

    def test_what_project(self):
        """'what project' is a synonym."""
        result = _cmd("what project")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "which_project")

    def test_which_session(self):
        """'which session' also triggers which_project."""
        result = _cmd("which session")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "which_project")

    def test_which_project_in_full_sentence(self):
        """Full phrase 'which project am I on' still matches."""
        result = _cmd("which project am I on")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "which_project")


# ─────────────────────────────────────────────────────────────────────────────
# last_message
# ─────────────────────────────────────────────────────────────────────────────


class TestLastMessageCommand(unittest.TestCase):
    """_fast_command recognises replay / last-message utterances."""

    def test_last_message(self):
        """'last message' → {command: 'last_message'}."""
        result = _cmd("last message")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "last_message")

    def test_repeat_that(self):
        """'repeat' triggers last_message."""
        result = _cmd("repeat")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "last_message")

    def test_replay_response(self):
        """'replay response' triggers last_message."""
        result = _cmd("replay response")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "last_message")

    def test_again(self):
        """'again' is a shorthand for repeat."""
        result = _cmd("again")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "last_message")


# ─────────────────────────────────────────────────────────────────────────────
# switch
# ─────────────────────────────────────────────────────────────────────────────


class TestSwitchCommand(unittest.TestCase):
    """_fast_command recognises switch-project utterances."""

    def test_switch_to_project(self):
        """'switch to myproject' → {command: 'switch', project: 'myproject'}."""
        result = _cmd("switch to myproject")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "switch")
        self.assertEqual(result["project"], "myproject")

    def test_switch_bare_project(self):
        """'switch myproject' (no 'to') also works."""
        result = _cmd("switch myproject")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "switch")
        self.assertEqual(result["project"], "myproject")

    def test_project_key_is_string(self):
        """The 'project' value must be a str."""
        result = _cmd("switch to backend")
        self.assertIsNotNone(result)
        self.assertIsInstance(result["project"], str)

    def test_go_to_project(self):
        """'go to frontend' is a synonym."""
        result = _cmd("go to frontend")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "switch")
        self.assertEqual(result["project"], "frontend")

    def test_use_project(self):
        """'use api' is a synonym for switch."""
        result = _cmd("use api")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "switch")
        self.assertEqual(result["project"], "api")

    def test_switch_alone_returns_none(self):
        """'switch' with no project name must return None (incomplete command)."""
        result = _cmd("switch")
        # 'switch' alone matches the bare-word fullmatch patterns — it must
        # NOT produce a switch command since there is no project argument.
        # The regex requires at least one non-space character after 'switch'.
        self.assertIsNone(result)

    def test_activate_project(self):
        """'activate dashboard' routes to switch."""
        result = _cmd("activate dashboard")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "switch")
        self.assertEqual(result["project"], "dashboard")


# ─────────────────────────────────────────────────────────────────────────────
# rename
# ─────────────────────────────────────────────────────────────────────────────


class TestRenameCommand(unittest.TestCase):
    """_fast_command recognises rename-session utterances."""

    def test_rename_to_newname(self):
        """'rename to newname' → {command: 'rename', name: 'newname'}."""
        result = _cmd("rename to newname")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "rename")
        self.assertEqual(result["name"], "newname")

    def test_rename_project_newname(self):
        """'rename project newname' is a shorthand synonym."""
        result = _cmd("rename project newname")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "rename")
        self.assertEqual(result["name"], "newname")

    def test_rename_this_session_to(self):
        """'rename this session to api' → name 'api', no 'old' key."""
        result = _cmd("rename this session to api")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "rename")
        self.assertEqual(result["name"], "api")
        self.assertNotIn("old", result)

    def test_rename_old_to_new(self):
        """'rename web to frontend' → name='frontend', old='web'."""
        result = _cmd("rename web to frontend")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "rename")
        self.assertEqual(result["name"], "frontend")
        self.assertEqual(result["old"], "web")

    def test_rename_old_key_is_string(self):
        """'old' key must be a str when present."""
        result = _cmd("rename alpha to beta")
        self.assertIsNotNone(result)
        self.assertIsInstance(result["old"], str)

    def test_rename_name_key_is_string(self):
        """'name' key must be a str."""
        result = _cmd("rename to gamma")
        self.assertIsNotNone(result)
        self.assertIsInstance(result["name"], str)

    def test_rename_alone_returns_none(self):
        """'rename' with no arguments must return None."""
        result = _cmd("rename")
        self.assertIsNone(result)

    def test_call_this_synonym(self):
        """'call this backend' triggers rename of current session."""
        result = _cmd("call this backend")
        self.assertIsNotNone(result)
        self.assertEqual(result["command"], "rename")
        self.assertEqual(result["name"], "backend")
        self.assertNotIn("old", result)


# ─────────────────────────────────────────────────────────────────────────────
# Non-commands and edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestNonCommandStrings(unittest.TestCase):
    """Utterances that are not Cyrus meta-commands must return None."""

    def test_empty_string(self):
        """Empty string → None."""
        self.assertIsNone(_cmd(""))

    def test_regular_conversation(self):
        """Ordinary question to LLM must not match any command."""
        self.assertIsNone(_cmd("What is the capital of France?"))

    def test_partial_match_pausable(self):
        """'pausable' is not 'pause' — partial prefix must not match."""
        self.assertIsNone(_cmd("pausable"))

    def test_partial_match_unlocking(self):
        """'unlocking' is not 'unlock' — present-participle must not match."""
        self.assertIsNone(_cmd("unlocking the door"))

    def test_whitespace_only(self):
        """Whitespace-only input → None."""
        self.assertIsNone(_cmd("   "))

    def test_return_type_is_dict_or_none(self):
        """Every call must return dict or None — never another type."""
        cases = [
            "pause",
            "unlock",
            "switch to api",
            "rename to backend",
            "hello",
            "",
        ]
        for text in cases:
            with self.subTest(text=text):
                result = _cmd(text)
                self.assertIn(
                    type(result),
                    (dict, type(None)),
                    f"Expected dict or None for {text!r}, got {type(result)}",
                )

    def test_command_key_always_present_when_not_none(self):
        """When a command dict is returned, the 'command' key must be present."""
        command_cases = [
            "pause",
            "resume",
            "unlock",
            "follow focus",
            "which project",
            "last message",
            "switch to myproject",
            "rename to newname",
        ]
        for text in command_cases:
            with self.subTest(text=text):
                result = _cmd(text)
                self.assertIsNotNone(result, f"Expected command dict for {text!r}")
                self.assertIn("command", result, f"'command' key missing for {text!r}")

    def test_case_insensitive_matching(self):
        """Input is lowercased before matching — uppercase input still works."""
        cases_expected = [
            ("PAUSE", "pause"),
            ("UNLOCK", "unlock"),
            ("WHICH PROJECT", "which_project"),
            ("SWITCH TO MYAPP", "switch"),
        ]
        for text, expected_cmd in cases_expected:
            with self.subTest(text=text):
                result = _cmd(text)
                self.assertIsNotNone(result)
                self.assertEqual(result["command"], expected_cmd)

    def test_trailing_punctuation_stripped(self):
        """Trailing .,!? are ignored during matching."""
        for suffix in (".", ",", "!", "?"):
            with self.subTest(suffix=suffix):
                result = _cmd(f"pause{suffix}")
                self.assertIsNotNone(result)
                self.assertEqual(result["command"], "pause")


if __name__ == "__main__":
    unittest.main(verbosity=2)
