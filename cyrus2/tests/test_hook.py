"""
Acceptance-driven tests for Issue 022: Write test_hook.py (Tier 2).

Tests verify every acceptance criterion from the issue:
  - cyrus2/tests/test_hook.py exists with 12+ test cases
  - Event types covered: Stop, PreToolUse, PostToolUse, Notification, PreCompact
  - _send() called with correct arguments for each event
  - Invalid JSON handling (malformed, missing fields)
  - Unknown event type handling
  - Empty/whitespace-only input handling

Strategy: Patch sys.stdin with StringIO to simulate hook payloads; patch
cyrus_hook._send to intercept IPC messages without opening any real sockets.
The main() function calls sys.exit(0) on completion, so each test catches
SystemExit to avoid test termination.
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add cyrus2/ to sys.path so `import cyrus_hook` resolves correctly.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

from cyrus_hook import main  # noqa: E402

# ── Helpers ────────────────────────────────────────────────────────────────────


def _run_main(payload: dict, send_mock: MagicMock) -> None:
    """Run main() with a JSON-serialised payload via patched stdin.

    Patches cyrus_hook._send to send_mock so no real sockets are opened.
    Asserts that main() exits with code 0 (normal termination).

    Args:
        payload: Hook event dict to serialise as stdin JSON.
        send_mock: MagicMock to capture _send() calls.
    """
    json_str = json.dumps(payload)
    with patch("cyrus_hook._send", send_mock), patch("sys.stdin", StringIO(json_str)):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0


def _run_main_raw(raw_input: str, send_mock: MagicMock) -> int:
    """Run main() with a raw string on stdin (may be invalid JSON).

    Returns:
        The sys.exit() code from main().
    """
    with patch("cyrus_hook._send", send_mock), patch("sys.stdin", StringIO(raw_input)):
        with pytest.raises(SystemExit) as exc_info:
            main()
        return exc_info.value.code  # type: ignore[return-value]


# ─────────────────────────────────────────────────────────────────────────────
# Stop event
# ─────────────────────────────────────────────────────────────────────────────


class TestStopEvent:
    """Tests for Stop hook event dispatch to _send()."""

    def test_stop_event_sends_correct_payload(self, mock_send: MagicMock) -> None:
        """Valid Stop event with last_assistant_message dispatches correct payload."""
        payload = {
            "hook_event_name": "Stop",
            "last_assistant_message": "Task complete.",
            "cwd": "/home/user/project",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {"event": "stop", "text": "Task complete.", "cwd": "/home/user/project"}
        )

    def test_stop_event_with_extra_fields_still_dispatches(
        self, mock_send: MagicMock
    ) -> None:
        """Stop event with extra unrecognised fields is dispatched correctly.

        Extra fields like session_id or metadata should be silently ignored so
        forward-compatible hook payloads keep working.
        """
        payload = {
            "hook_event_name": "Stop",
            "last_assistant_message": "Done",
            "cwd": "/tmp",
            "extra_field": "should be ignored",
            "session_id": "abc123",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {"event": "stop", "text": "Done", "cwd": "/tmp"}
        )

    def test_stop_event_empty_message_does_not_send(self, mock_send: MagicMock) -> None:
        """Stop event with empty string last_assistant_message does not call _send.

        An empty message means there is nothing to announce; sending an empty
        payload wastes the IPC channel.
        """
        payload = {
            "hook_event_name": "Stop",
            "last_assistant_message": "",
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_not_called()

    def test_stop_event_missing_message_does_not_send(
        self, mock_send: MagicMock
    ) -> None:
        """Stop event with no last_assistant_message key does not call _send."""
        payload = {
            "hook_event_name": "Stop",
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# PreToolUse event
# ─────────────────────────────────────────────────────────────────────────────


class TestPreToolUseEvent:
    """Tests for PreToolUse hook event dispatch to _send()."""

    def test_pre_tool_use_bash_sends_command(self, mock_send: MagicMock) -> None:
        """PreToolUse for Bash extracts 'command' from tool_input and sends it."""
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la /tmp"},
            "cwd": "/home/user",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {
                "event": "pre_tool",
                "tool": "Bash",
                "command": "ls -la /tmp",
                "cwd": "/home/user",
            }
        )

    def test_pre_tool_use_edit_sends_file_path(self, mock_send: MagicMock) -> None:
        """PreToolUse for Edit extracts 'file_path' from tool_input as command."""
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/home/user/main.py"},
            "cwd": "/home/user",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {
                "event": "pre_tool",
                "tool": "Edit",
                "command": "/home/user/main.py",
                "cwd": "/home/user",
            }
        )

    def test_pre_tool_use_write_sends_file_path(self, mock_send: MagicMock) -> None:
        """PreToolUse for Write extracts 'file_path' from tool_input as command."""
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/output.txt"},
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {
                "event": "pre_tool",
                "tool": "Write",
                "command": "/tmp/output.txt",
                "cwd": "/tmp",
            }
        )

    def test_pre_tool_use_read_sends_file_path(self, mock_send: MagicMock) -> None:
        """PreToolUse for Read extracts 'file_path' from tool_input as command."""
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/etc/hosts"},
            "cwd": "/etc",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {
                "event": "pre_tool",
                "tool": "Read",
                "command": "/etc/hosts",
                "cwd": "/etc",
            }
        )

    def test_pre_tool_use_unknown_tool_sends_empty_command(
        self, mock_send: MagicMock
    ) -> None:
        """PreToolUse for an unrecognised tool still dispatches event with
        empty command.

        All tool use events are forwarded so Cyrus can announce what Claude is
        doing; the command field is simply empty for unknown tools.
        """
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "UnknownTool",
            "tool_input": {"some_field": "value"},
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {
                "event": "pre_tool",
                "tool": "UnknownTool",
                "command": "",
                "cwd": "/tmp",
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# PostToolUse event
# ─────────────────────────────────────────────────────────────────────────────


class TestPostToolUseEvent:
    """Tests for PostToolUse hook event dispatch to _send()."""

    def test_post_tool_use_bash_failure_sends_payload(
        self, mock_send: MagicMock
    ) -> None:
        """PostToolUse for Bash with non-zero exit_code dispatches post_tool event."""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "failing_cmd"},
            "tool_response": {"exit_code": 1, "stderr": "command not found"},
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {
                "event": "post_tool",
                "tool": "Bash",
                "command": "failing_cmd",
                "exit_code": 1,
                "error": "command not found",
                "cwd": "/tmp",
            }
        )

    def test_post_tool_use_bash_success_does_not_send(
        self, mock_send: MagicMock
    ) -> None:
        """PostToolUse for Bash with exit_code 0 and no error does not call _send.

        Successful Bash commands are not announced — only failures are worth
        interrupting the user about.
        """
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {"exit_code": 0, "stdout": "file.txt"},
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_not_called()

    def test_post_tool_use_bash_with_stderr_sends_even_if_exit_code_zero(
        self, mock_send: MagicMock
    ) -> None:
        """PostToolUse Bash with exit_code 0 but non-empty stderr still notifies.

        Some commands write to stderr even on success (e.g. warnings).  Cyrus
        flags these because the user may still want to know.
        """
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "make"},
            "tool_response": {
                "exit_code": 0,
                "stderr": "warning: implicit declaration",
            },
            "cwd": "/home/user",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once()
        sent = mock_send.call_args[0][0]
        assert sent["event"] == "post_tool"
        assert sent["error"] == "warning: implicit declaration"

    def test_post_tool_use_bash_error_truncated_to_200(
        self, mock_send: MagicMock
    ) -> None:
        """PostToolUse Bash error messages longer than 200 chars are truncated.

        Truncation keeps IPC messages small and avoids flooding Cyrus Brain
        with stack-trace noise.
        """
        long_error = "x" * 300
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "bad_cmd"},
            "tool_response": {"exit_code": 1, "stderr": long_error},
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        sent = mock_send.call_args[0][0]
        assert len(sent["error"]) == 200
        assert sent["error"] == "x" * 200

    def test_post_tool_use_edit_sends_file_path(self, mock_send: MagicMock) -> None:
        """PostToolUse for Edit always dispatches post_tool with file_path.

        File-modification events are always forwarded regardless of success so
        Cyrus can announce what was changed.
        """
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/home/user/app.py"},
            "tool_response": {},
            "cwd": "/home/user",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {
                "event": "post_tool",
                "tool": "Edit",
                "file_path": "/home/user/app.py",
                "cwd": "/home/user",
            }
        )

    def test_post_tool_use_write_sends_file_path(self, mock_send: MagicMock) -> None:
        """PostToolUse for Write always dispatches post_tool with file_path."""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/out.txt"},
            "tool_response": {},
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {
                "event": "post_tool",
                "tool": "Write",
                "file_path": "/tmp/out.txt",
                "cwd": "/tmp",
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# Notification event
# ─────────────────────────────────────────────────────────────────────────────


class TestNotificationEvent:
    """Tests for Notification hook event dispatch to _send()."""

    def test_notification_sends_message(self, mock_send: MagicMock) -> None:
        """Valid Notification event dispatches notification event with message."""
        payload = {
            "hook_event_name": "Notification",
            "message": "Build failed",
            "cwd": "/home/user/project",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {
                "event": "notification",
                "message": "Build failed",
                "cwd": "/home/user/project",
            }
        )

    def test_notification_empty_message_does_not_send(
        self, mock_send: MagicMock
    ) -> None:
        """Notification with empty string message does not call _send."""
        payload = {
            "hook_event_name": "Notification",
            "message": "",
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_not_called()

    def test_notification_whitespace_message_does_not_send(
        self, mock_send: MagicMock
    ) -> None:
        """Notification with whitespace-only message does not call _send.

        strip() is applied before the truthiness check, so a message that is
        only spaces/tabs/newlines is treated as empty.
        """
        payload = {
            "hook_event_name": "Notification",
            "message": "   \t\n  ",
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# PreCompact event
# ─────────────────────────────────────────────────────────────────────────────


class TestPreCompactEvent:
    """Tests for PreCompact hook event dispatch to _send()."""

    def test_pre_compact_sends_auto_trigger(self, mock_send: MagicMock) -> None:
        """PreCompact with 'auto' trigger dispatches pre_compact event correctly."""
        payload = {
            "hook_event_name": "PreCompact",
            "trigger": "auto",
            "cwd": "/home/user",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {"event": "pre_compact", "trigger": "auto", "cwd": "/home/user"}
        )

    def test_pre_compact_manual_trigger(self, mock_send: MagicMock) -> None:
        """PreCompact with 'manual' trigger dispatches pre_compact with correct
        trigger."""
        payload = {
            "hook_event_name": "PreCompact",
            "trigger": "manual",
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_called_once_with(
            {"event": "pre_compact", "trigger": "manual", "cwd": "/tmp"}
        )


# ─────────────────────────────────────────────────────────────────────────────
# Error handling and edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorHandling:
    """Tests for error handling, invalid input, and edge cases."""

    def test_malformed_json_exits_cleanly(self, mock_send: MagicMock) -> None:
        """Malformed JSON input causes sys.exit(0) without calling _send.

        A crashing hook blocks Claude Code, so all exceptions must be swallowed
        and the process must exit with code 0 regardless of input quality.
        """
        exit_code = _run_main_raw("not valid json {{{", mock_send)
        assert exit_code == 0
        mock_send.assert_not_called()

    def test_empty_input_exits_cleanly(self, mock_send: MagicMock) -> None:
        """Empty stdin input causes sys.exit(0) without calling _send."""
        exit_code = _run_main_raw("", mock_send)
        assert exit_code == 0
        mock_send.assert_not_called()

    def test_whitespace_only_input_exits_cleanly(self, mock_send: MagicMock) -> None:
        """Whitespace-only stdin input causes sys.exit(0) without calling _send."""
        exit_code = _run_main_raw("   \n   \t  ", mock_send)
        assert exit_code == 0
        mock_send.assert_not_called()

    def test_unknown_event_type_does_not_send(self, mock_send: MagicMock) -> None:
        """Unknown hook_event_name falls through all branches without calling _send."""
        payload = {
            "hook_event_name": "UnknownEventType",
            "cwd": "/tmp",
        }
        _run_main(payload, mock_send)
        mock_send.assert_not_called()

    def test_missing_hook_event_name_does_not_send(self, mock_send: MagicMock) -> None:
        """JSON payload without hook_event_name key does not call _send.

        Defaults to empty string which matches no known event branch.
        """
        payload = {
            "cwd": "/tmp",
            "some_data": "value",
        }
        _run_main(payload, mock_send)
        mock_send.assert_not_called()

    def test_partial_json_truncated_exits_cleanly(self, mock_send: MagicMock) -> None:
        """Truncated JSON (partial payload) causes sys.exit(0) without calling _send."""
        truncated = '{"hook_event_name": "Stop", "last_assistant_messa'
        exit_code = _run_main_raw(truncated, mock_send)
        assert exit_code == 0
        mock_send.assert_not_called()

    def test_main_always_exits_zero(self, mock_send: MagicMock) -> None:
        """main() always exits with code 0 regardless of event type.

        The hook must never exit non-zero — any non-zero exit code from a hook
        blocks Claude Code from continuing.
        """
        # Use a valid Stop event to reach the normal exit path
        payload = {
            "hook_event_name": "Stop",
            "last_assistant_message": "Done",
            "cwd": "/tmp",
        }
        json_str = json.dumps(payload)
        with (
            patch("cyrus_hook._send", mock_send),
            patch("sys.stdin", StringIO(json_str)),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0
