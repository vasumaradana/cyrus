"""
cyrus_hook.py — Claude Code Stop hook

Configured in .claude/settings.json as a Stop hook command.
Receives JSON on stdin, extracts last_assistant_message, forwards to Cyrus Brain.

Never raises — a crashing hook blocks Claude Code.
"""

import json
import socket
import sys

BRAIN_HOST = "localhost"
BRAIN_PORT = 8767       # dedicated hook port, separate from voice port 8766

def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    text = (payload.get("last_assistant_message") or "").strip()
    if not text:
        sys.exit(0)

    # Include cwd so Brain can resolve which project this belongs to
    msg = json.dumps({
        "type": "hook_response",
        "text": text,
        "cwd":  payload.get("cwd", ""),
    }) + "\n"

    try:
        with socket.create_connection((BRAIN_HOST, BRAIN_PORT), timeout=2) as s:
            s.sendall(msg.encode())
    except Exception:
        pass   # Brain not running — silent, never block Claude

    sys.exit(0)

if __name__ == "__main__":
    main()
