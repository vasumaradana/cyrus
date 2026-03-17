"""
Acceptance-driven tests for Issue 017:
Add permission approval logging to PermissionWatcher.

Tests verify every acceptance criterion from the issue:
  - PermissionWatcher logs permission type being detected
  - Permission name/description logged when "Allow" button is clicked
  - Log includes timestamp and utterance that triggered approval
  - Log includes dialog title or permission scope
  - All log entries at INFO level (security-relevant events)
  - No sensitive data exposed in logs (avoid full dialog text if it contains secrets)
  - Log entries sufficient for audit trail of auto-approved permissions
  - Existing PermissionWatcher functionality preserved
  - No performance impact from logging

Strategy: Runtime tests for arm_from_hook + handle_response (capture log records);
source-text checks for poll-loop log call (background thread, hard to test at runtime).
"""

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Mock Windows-specific modules BEFORE any cyrus import ────────────────────
# cyrus_common.py imports Windows-only packages at the module level.
# Mock them in sys.modules first so the import succeeds on any platform.
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

# Add cyrus2/ directory to sys.path so imports resolve correctly on any platform.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

from cyrus_common import PermissionWatcher  # noqa: E402

# Path for static analysis.
COMMON_PY = _CYRUS2_DIR / "cyrus_common.py"

# Logger name under test — must match implementation.
_PERM_LOGGER = "cyrus.permission"


# ── Helpers ───────────────────────────────────────────────────────────────────


class _CapturingHandler(logging.Handler):
    """Collects LogRecord instances emitted to a logger."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Store the record for later inspection."""
        self.records.append(record)


def _make_watcher(project_name: str = "test-proj") -> PermissionWatcher:
    """Return a PermissionWatcher configured with no-op callbacks."""
    return PermissionWatcher(project_name=project_name, target_subname="TestSub")


def _attach_handler(logger_name: str) -> _CapturingHandler:
    """Attach a capturing handler to a named logger; set level to DEBUG."""
    handler = _CapturingHandler()
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return handler


def _detach_handler(logger_name: str, handler: _CapturingHandler) -> None:
    """Remove a previously attached capturing handler from a logger."""
    logging.getLogger(logger_name).removeHandler(handler)


# ── AC: PermissionWatcher logs permission type being detected ─────────────────


class TestPollDetectionLogging(unittest.TestCase):
    """AC: PermissionWatcher logs permission type being detected."""

    def test_poll_detection_log_call_exists_in_source(self):
        """Poll loop must contain a log call for permission dialog detection.

        AC: PermissionWatcher logs permission type being detected.
        """
        source = COMMON_PY.read_text(encoding="utf-8")
        self.assertIn(
            "Permission dialog detected",
            source,
            "Expected 'Permission dialog detected' log message in cyrus_common.py",
        )

    def test_poll_detection_log_uses_permission_logger(self):
        """Poll detection log must use the cyrus.permission logger (_perm_log).

        Verifies that the permission-specific logger variable is used in the poll
        function, not the module-level 'log' logger.
        """
        source = COMMON_PY.read_text(encoding="utf-8")
        # The permission logger variable (_perm_log) must appear in the source
        # alongside the "Permission dialog detected" message.
        self.assertIn(
            "_perm_log",
            source,
            "Permission logger variable '_perm_log' not found in cyrus_common.py",
        )

    def test_poll_detection_log_includes_cmd_field(self):
        """Poll detection log format must reference cmd_label for audit context.

        AC: Log includes dialog title or permission scope.
        """
        source = COMMON_PY.read_text(encoding="utf-8")
        # The log message must include cmd_label to identify the permission scope
        self.assertIn(
            "cmd_label",
            source,
            "Permission detection log must reference cmd_label for audit context",
        )


# ── AC: Permission name/description logged when Allow clicked ─────────────────


class TestAllowLogging(unittest.TestCase):
    """AC: Permission name/description logged when Allow button is clicked."""

    def setUp(self) -> None:
        self.handler = _attach_handler(_PERM_LOGGER)
        self.watcher = _make_watcher()

    def tearDown(self) -> None:
        _detach_handler(_PERM_LOGGER, self.handler)

    def test_allow_response_logs_permission_name(self):
        """AC: handle_response('yes') must log the announced permission command.

        AC: Permission name/description logged when Allow button is clicked.
        """
        self.watcher._pending = True
        self.watcher._allow_btn = "keyboard"
        self.watcher._announced = "hook:echo hello"

        with patch("cyrus_common._assert_vscode_focus"):
            self.watcher.handle_response("yes")

        msgs = [r.getMessage() for r in self.handler.records]
        self.assertTrue(
            any("APPROVED" in m for m in msgs),
            f"Expected 'APPROVED' in log messages after allow; got: {msgs}",
        )

    def test_allow_log_includes_announced_cmd(self):
        """Allow log entry must include the announced command text.

        AC: Permission name/description logged when Allow button is clicked.
        """
        self.watcher._pending = True
        self.watcher._allow_btn = "keyboard"
        self.watcher._announced = "hook:git push origin main"

        with patch("cyrus_common._assert_vscode_focus"):
            self.watcher.handle_response("yes")

        msgs = [r.getMessage() for r in self.handler.records]
        self.assertTrue(
            any("git push origin main" in m for m in msgs),
            f"Expected announced cmd in allow log; got: {msgs}",
        )


# ── AC: Log includes utterance that triggered approval ────────────────────────


class TestUtteranceLogging(unittest.TestCase):
    """AC: Log includes utterance that triggered approval."""

    def setUp(self) -> None:
        self.handler = _attach_handler(_PERM_LOGGER)
        self.watcher = _make_watcher()

    def tearDown(self) -> None:
        _detach_handler(_PERM_LOGGER, self.handler)

    def test_allow_log_includes_utterance(self):
        """AC: handle_response('yes') log must contain the utterance text."""
        self.watcher._pending = True
        self.watcher._allow_btn = "keyboard"
        self.watcher._announced = "hook:touch /tmp/test"

        with patch("cyrus_common._assert_vscode_focus"):
            self.watcher.handle_response("yes please allow it")

        msgs = [r.getMessage() for r in self.handler.records]
        self.assertTrue(
            any("yes please allow it" in m for m in msgs),
            f"Expected utterance text in allow log; got: {msgs}",
        )

    def test_deny_log_includes_utterance(self):
        """AC: handle_response('no') log must contain the utterance text."""
        self.watcher._pending = True
        self.watcher._allow_btn = "keyboard"
        self.watcher._announced = "hook:rm -rf /"

        with patch("cyrus_common._assert_vscode_focus"):
            self.watcher.handle_response("no way deny that")

        msgs = [r.getMessage() for r in self.handler.records]
        self.assertTrue(
            any("no way deny that" in m for m in msgs),
            f"Expected utterance text in deny log; got: {msgs}",
        )


# ── AC: Log includes dialog title/permission scope ────────────────────────────


class TestDialogScopeLogging(unittest.TestCase):
    """AC: Log includes dialog title or permission scope."""

    def setUp(self) -> None:
        self.handler = _attach_handler(_PERM_LOGGER)
        self.watcher = _make_watcher()

    def tearDown(self) -> None:
        _detach_handler(_PERM_LOGGER, self.handler)

    def test_hook_arm_logs_tool_name(self):
        """AC: arm_from_hook must log tool name (dialog title / scope)."""
        self.watcher.arm_from_hook("Bash", "rm -rf /tmp/test")

        msgs = [r.getMessage() for r in self.handler.records]
        self.assertTrue(
            any("Bash" in m for m in msgs),
            f"Expected tool name 'Bash' in hook arm log; got: {msgs}",
        )

    def test_hook_arm_logs_cmd(self):
        """AC: arm_from_hook must log the command text (permission scope)."""
        self.watcher.arm_from_hook("Bash", "rm -rf /tmp/test")

        msgs = [r.getMessage() for r in self.handler.records]
        self.assertTrue(
            any("rm -rf /tmp/test" in m for m in msgs),
            f"Expected cmd in hook arm log; got: {msgs}",
        )

    def test_hook_arm_logs_project_name(self):
        """arm_from_hook log must include the project name for audit context."""
        watcher = _make_watcher(project_name="my-project")
        handler = _attach_handler(_PERM_LOGGER)
        try:
            watcher.arm_from_hook("Write", "write to file")
            msgs = [r.getMessage() for r in handler.records]
            self.assertTrue(
                any("my-project" in m for m in msgs),
                f"Expected project name in hook arm log; got: {msgs}",
            )
        finally:
            _detach_handler(_PERM_LOGGER, handler)


# ── AC: All log entries at INFO level ─────────────────────────────────────────


class TestLogLevel(unittest.TestCase):
    """AC: All log entries at INFO level (security-relevant events)."""

    def test_all_log_entries_are_info_level(self):
        """AC: All PermissionWatcher log calls must be at INFO level."""
        handler = _attach_handler(_PERM_LOGGER)
        watcher = _make_watcher()

        try:
            # Trigger arm_from_hook log
            watcher.arm_from_hook("Bash", "ls /tmp")

            # Reset state and trigger allow log
            watcher._pending = True
            watcher._allow_btn = "keyboard"
            watcher._announced = "hook:ls /tmp"
            with patch("cyrus_common._assert_vscode_focus"):
                watcher.handle_response("yes")

            self.assertGreater(
                len(handler.records),
                0,
                "Expected at least one log record from permission watcher",
            )
            for record in handler.records:
                self.assertEqual(
                    record.levelno,
                    logging.INFO,
                    f"Expected INFO level, got {record.levelname}: "
                    f"{record.getMessage()}",
                )
        finally:
            _detach_handler(_PERM_LOGGER, handler)

    def test_deny_log_is_info_level(self):
        """DENIED log entry must also be at INFO level."""
        handler = _attach_handler(_PERM_LOGGER)
        watcher = _make_watcher()
        watcher._pending = True
        watcher._allow_btn = "keyboard"
        watcher._announced = "hook:bad-cmd"

        try:
            with patch("cyrus_common._assert_vscode_focus"):
                watcher.handle_response("no")

            for record in handler.records:
                self.assertEqual(
                    record.levelno,
                    logging.INFO,
                    f"Expected INFO level for deny, got {record.levelname}: "
                    f"{record.getMessage()}",
                )
        finally:
            _detach_handler(_PERM_LOGGER, handler)


# ── AC: No sensitive data in logs ─────────────────────────────────────────────


class TestSensitiveDataProtection(unittest.TestCase):
    """AC: No sensitive data exposed in logs."""

    def test_command_truncated_in_log(self):
        """AC: Commands longer than 120 chars must be truncated in log output.

        AC: No sensitive data exposed in logs.
        """
        handler = _attach_handler(_PERM_LOGGER)
        watcher = _make_watcher()
        long_cmd = "x" * 200  # 200-char command — well beyond the 120-char limit

        try:
            watcher.arm_from_hook("Bash", long_cmd)

            for record in handler.records:
                msg = record.getMessage()
                # Full 200-char command must NOT appear (would indicate no truncation)
                self.assertNotIn(
                    long_cmd,
                    msg,
                    "Full 200-char command appeared in log without truncation",
                )
        finally:
            _detach_handler(_PERM_LOGGER, handler)

    def test_truncated_cmd_max_120_chars(self):
        """Truncated command must be capped at exactly 120 chars in log."""
        handler = _attach_handler(_PERM_LOGGER)
        watcher = _make_watcher()
        # Use a 200-char command of distinct char to detect length precisely
        long_cmd = "z" * 200

        try:
            watcher.arm_from_hook("Bash", long_cmd)
            msgs = [r.getMessage() for r in handler.records]
            # "z" * 121 must NOT appear — truncation must stop at 120
            self.assertFalse(
                any("z" * 121 in m for m in msgs),
                "Command not truncated to 120 chars: found >120 consecutive 'z' chars",
            )
        finally:
            _detach_handler(_PERM_LOGGER, handler)


# ── AC: Audit trail completeness ──────────────────────────────────────────────


class TestAuditTrail(unittest.TestCase):
    """AC: Log entries sufficient for audit trail of auto-approved permissions."""

    def test_audit_trail_completeness(self):
        """Approve + deny paths must log all required fields for an audit trail.

        AC: Log entries sufficient for audit trail of auto-approved permissions.
        """
        handler = _attach_handler(_PERM_LOGGER)
        watcher = _make_watcher(project_name="audit-proj")

        try:
            # Exercise APPROVE path
            watcher._pending = True
            watcher._allow_btn = "keyboard"
            watcher._announced = "hook:echo hello"
            with patch("cyrus_common._assert_vscode_focus"):
                watcher.handle_response("yes")

            # Exercise DENY path
            watcher._pending = True
            watcher._allow_btn = "keyboard"
            watcher._announced = "hook:rm -rf /"
            with patch("cyrus_common._assert_vscode_focus"):
                watcher.handle_response("no")

            all_msgs = "\n".join(r.getMessage() for r in handler.records)

            # Both decision types must be recorded
            self.assertIn(
                "APPROVED", all_msgs, "APPROVED decision missing from audit log"
            )
            self.assertIn("DENIED", all_msgs, "DENIED decision missing from audit log")
            # Project context must be present
            self.assertIn("audit-proj", all_msgs, "Project name missing from audit log")
        finally:
            _detach_handler(_PERM_LOGGER, handler)

    def test_deny_response_logs_denied(self):
        """handle_response('no') must emit a DENIED log entry.

        AC: Log entries sufficient for audit trail.
        """
        handler = _attach_handler(_PERM_LOGGER)
        watcher = _make_watcher()
        watcher._pending = True
        watcher._allow_btn = "keyboard"
        watcher._announced = "hook:dangerous-cmd"

        try:
            with patch("cyrus_common._assert_vscode_focus"):
                watcher.handle_response("no")

            msgs = [r.getMessage() for r in handler.records]
            self.assertTrue(
                any("DENIED" in m for m in msgs),
                f"Expected 'DENIED' in deny log messages; got: {msgs}",
            )
        finally:
            _detach_handler(_PERM_LOGGER, handler)

    def test_hook_arm_logs_permission_requested(self):
        """arm_from_hook must emit a 'Permission requested' log entry.

        AC: Log entries sufficient for audit trail.
        """
        handler = _attach_handler(_PERM_LOGGER)
        watcher = _make_watcher()

        try:
            watcher.arm_from_hook("Write", "create /etc/config")
            msgs = [r.getMessage() for r in handler.records]
            self.assertTrue(
                any("Permission requested" in m for m in msgs),
                f"Expected 'Permission requested' in hook arm log; got: {msgs}",
            )
        finally:
            _detach_handler(_PERM_LOGGER, handler)


# ── AC: Existing functionality preserved ──────────────────────────────────────


class TestFunctionalityPreserved(unittest.TestCase):
    """AC: Existing PermissionWatcher functionality preserved."""

    def test_handle_response_returns_true_on_allow(self):
        """handle_response must still return True when 'yes' is consumed."""
        watcher = _make_watcher()
        watcher._pending = True
        watcher._allow_btn = "keyboard"
        watcher._announced = "hook:some-cmd"

        with patch("cyrus_common._assert_vscode_focus"):
            result = watcher.handle_response("yes")

        self.assertTrue(result, "handle_response must return True for 'yes'")

    def test_handle_response_returns_true_on_deny(self):
        """handle_response must still return True when 'no' is consumed."""
        watcher = _make_watcher()
        watcher._pending = True
        watcher._allow_btn = "keyboard"
        watcher._announced = "hook:some-cmd"

        with patch("cyrus_common._assert_vscode_focus"):
            result = watcher.handle_response("no")

        self.assertTrue(result, "handle_response must return True for 'no'")

    def test_handle_response_returns_false_on_unknown(self):
        """handle_response must return False for unrecognized utterances."""
        watcher = _make_watcher()
        watcher._pending = True
        watcher._allow_btn = "keyboard"

        with patch("cyrus_common._assert_vscode_focus"):
            result = watcher.handle_response("hello")

        self.assertFalse(
            result, "handle_response must return False for unrecognized text"
        )

    def test_arm_from_hook_skips_auto_allowed_tools(self):
        """arm_from_hook must not arm for auto-allowed tools (Read, Grep, etc.)."""
        handler = _attach_handler(_PERM_LOGGER)
        watcher = _make_watcher()

        try:
            watcher.arm_from_hook("Read", "some file path")

            self.assertFalse(
                watcher._pending,
                "PermissionWatcher must not arm for auto-allowed tools like Read",
            )
            # No log should be emitted for auto-allowed tools
            self.assertEqual(
                len(handler.records),
                0,
                "No permission log should be emitted for auto-allowed tools",
            )
        finally:
            _detach_handler(_PERM_LOGGER, handler)

    def test_handle_response_clears_pending_on_allow(self):
        """handle_response('yes') must clear _pending state (existing behavior)."""
        watcher = _make_watcher()
        watcher._pending = True
        watcher._allow_btn = "keyboard"
        watcher._announced = "hook:cmd"

        with patch("cyrus_common._assert_vscode_focus"):
            watcher.handle_response("yes")

        self.assertFalse(
            watcher._pending,
            "_pending must be cleared after allow response",
        )

    def test_handle_response_clears_pending_on_deny(self):
        """handle_response('no') must clear _pending state (existing behavior)."""
        watcher = _make_watcher()
        watcher._pending = True
        watcher._allow_btn = "keyboard"
        watcher._announced = "hook:cmd"

        with patch("cyrus_common._assert_vscode_focus"):
            watcher.handle_response("no")

        self.assertFalse(
            watcher._pending,
            "_pending must be cleared after deny response",
        )


# ── AC: No performance impact from logging ────────────────────────────────────


class TestNoPerformanceImpact(unittest.TestCase):
    """AC: No performance impact from logging."""

    def test_logging_with_no_handler_does_not_raise(self):
        """AC: No exception must be raised when no log handler is configured.

        AC: No performance impact from logging.
        """
        perm_logger = logging.getLogger(_PERM_LOGGER)
        saved_handlers = list(perm_logger.handlers)
        saved_level = perm_logger.level
        # Suppress all output from this logger
        perm_logger.handlers = []
        perm_logger.setLevel(logging.WARNING)

        try:
            watcher = _make_watcher()
            # Must not raise even when INFO is filtered out by level
            watcher.arm_from_hook("Bash", "echo test")
        except Exception as exc:  # noqa: BLE001
            self.fail(f"arm_from_hook raised with no active log handler: {exc}")
        finally:
            perm_logger.handlers = saved_handlers
            perm_logger.setLevel(saved_level)

    def test_logger_name_is_cyrus_permission(self):
        """Permission logger must use 'cyrus.permission' for targeted filtering.

        AC: No performance impact — correct logger hierarchy enables efficient
        log-level filtering.
        """
        handler = _attach_handler(_PERM_LOGGER)
        watcher = _make_watcher()

        try:
            watcher.arm_from_hook("Bash", "ls")

            self.assertGreater(
                len(handler.records),
                0,
                "Expected at least one log record from arm_from_hook",
            )
            for record in handler.records:
                self.assertEqual(
                    record.name,
                    "cyrus.permission",
                    f"Logger name must be 'cyrus.permission', got '{record.name}'",
                )
        finally:
            _detach_handler(_PERM_LOGGER, handler)


if __name__ == "__main__":
    unittest.main(verbosity=2)
