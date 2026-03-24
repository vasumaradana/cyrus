"""
cyrus_hook.py — Claude Code hooks (Stop, PreToolUse, PostToolUse, Notification)

Configured in ~/.claude/settings.json for all four hook events.
Reads JSON from stdin, forwards appropriate payload to Cyrus Brain on port 8767.

Never raises — a crashing hook blocks Claude Code.
"""

import json
import socket
import sys

BRAIN_HOST = "localhost"
BRAIN_PORT = 8767


def _send(msg: dict) -> None:
    try:
        with socket.create_connection((BRAIN_HOST, BRAIN_PORT), timeout=2) as s:
            s.sendall((json.dumps(msg) + "\n").encode())
    except Exception:
        pass   # Brain not running — silent, never block Claude


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    event = payload.get("hook_event_name", "")
    cwd   = payload.get("cwd", "")

    if event == "Stop":
        text = (payload.get("last_assistant_message") or "").strip()
        if text:
            _send({"event": "stop", "text": text, "cwd": cwd})

    elif event == "PreToolUse":
        tool       = payload.get("tool_name", "")
        tool_input = payload.get("tool_input") or {}
        cmd = ""
        if tool == "Bash":
            cmd = (tool_input.get("command") or "").strip()
        elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            cmd = (tool_input.get("file_path") or
                   tool_input.get("notebook_path") or "").strip()
        elif tool == "Read":
            cmd = (tool_input.get("file_path") or "").strip()
        _send({"event": "pre_tool", "tool": tool, "command": cmd, "cwd": cwd})

    elif event == "PostToolUse":
        tool          = payload.get("tool_name", "")
        tool_input    = payload.get("tool_input")    or {}
        tool_response = payload.get("tool_response") or {}

        if tool == "Bash":
            # Only notify on failure
            exit_code = tool_response.get("exit_code", 0)
            error     = (tool_response.get("stderr") or
                         tool_response.get("error")  or "").strip()
            if exit_code != 0 or error:
                _send({
                    "event":     "post_tool",
                    "tool":      tool,
                    "command":   (tool_input.get("command") or "").strip(),
                    "exit_code": exit_code,
                    "error":     error[:200],
                    "cwd":       cwd,
                })

        elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            file_path = (tool_input.get("file_path") or
                         tool_input.get("notebook_path") or "").strip()
            _send({
                "event":     "post_tool",
                "tool":      tool,
                "file_path": file_path,
                "cwd":       cwd,
            })

    elif event == "Notification":
        message = (payload.get("message") or "").strip()
        if message:
            _send({"event": "notification", "message": message, "cwd": cwd})

    elif event == "PreCompact":
        trigger = payload.get("trigger", "auto")
        _send({"event": "pre_compact", "trigger": trigger, "cwd": cwd})

    sys.exit(0)


if __name__ == "__main__":
    main()
