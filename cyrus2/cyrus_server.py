"""
Cyrus Remote Brain — WebSocket server

Receives transcribed text from a local Cyrus client, routes it (fast-command /
answer / forward), and returns decisions as JSON.  The client sends all context
it needs with each utterance, so the server is stateless.

Usage:
    python cyrus_server.py [--host 0.0.0.0] [--port 8765]

Protocol
--------
Client → Server  (utterance):
    {
      "type":          "utterance",
      "text":          "fix the bug in submit",
      "project":       "cyrus",
      "sessions":      ["cyrus", "web app"],
      "last_response": "<last Claude response, may be empty>"
    }

Server → Client  (decision):
    {
      "type":    "decision",
      "action":  "answer" | "forward" | "command",
      "spoken":  "...",
      "message": "...",
      "command": {"type": "...", "project": "..."}
    }
"""

import argparse
import asyncio
import json
import logging
import re

try:
    import websockets
except ImportError:
    raise SystemExit("websockets not installed — run: pip install websockets") from None

from cyrus2.cyrus_config import SERVER_PORT
from cyrus2.cyrus_log import setup_logging

log = logging.getLogger("cyrus.server")


# ── Config (mirrors main.py) ───────────────────────────────────────────────────

SUMMARY_WORD_THRESHOLD = 30

VOICE_HINT = (
    "\n\n[Voice mode: keep explanations to 2-3 sentences. "
    "For code changes show only the modified section, not the full file.]"
)


# ── Routing helpers (mirrors main.py) ─────────────────────────────────────────

_ANSWER_RE = re.compile(
    r"\b(recap|summarize?|summary)\b"
    r"|what\s+(did|was|were)\b.{0,40}\b(say|said|respond|answered?|told?|reply|replied)\b"
    r"|what\s+(you|claude|cyrus|it)\s+said\b"
    r"|\b(last\s+response|last\s+reply)\b"
    r"|\brepeat\s+(that|what\s+(you|claude|cyrus|it)\s+said)\b",
    re.IGNORECASE,
)


def _is_answer_request(text: str) -> bool:
    return bool(_ANSWER_RE.search(text))


def _fast_command(text: str) -> dict | None:
    t = text.lower().strip().rstrip(".,!?")

    if re.fullmatch(r"pause|resume|stop listening|start listening", t):
        return {
            "action": "command",
            "spoken": "",
            "message": "",
            "command": {"type": "pause"},
        }

    if re.fullmatch(r"(un ?lock|auto|follow focus|auto(matic)? routing)", t):
        return {
            "action": "command",
            "spoken": "",
            "message": "",
            "command": {"type": "unlock"},
        }

    if re.search(r"\b(which|what)\b.{0,20}\b(project|session)\b", t):
        return {
            "action": "command",
            "spoken": "",
            "message": "",
            "command": {"type": "which_project"},
        }

    if re.fullmatch(r"(last|repeat|replay|again).{0,30}(message|response|said)?", t):
        return {
            "action": "command",
            "spoken": "",
            "message": "",
            "command": {"type": "last_message"},
        }

    m = (
        re.match(r"(?:switch(?: to)?|use|go to|open|activate)\s+(.+)", t)
        or re.match(r"make\s+(.+?)\s+(?:the\s+)?active", t)
        or re.match(
            r"(?:set|change)\s+(?:active\s+)?(?:project|session)\s+to\s+(.+)", t
        )
    )
    if m:
        return {
            "action": "command",
            "spoken": "",
            "message": "",
            "command": {"type": "switch_project", "project": m.group(1).strip()},
        }

    return None


# ── WebSocket handler ──────────────────────────────────────────────────────────


async def handle_client(websocket):
    addr = websocket.remote_address
    log.info("Client connected: %s", addr)

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") != "utterance":
                continue

            text = msg.get("text", "").strip()
            project = msg.get("project", "")
            last_response = msg.get("last_response", "")

            if not text:
                continue

            decision = _fast_command(text)

            if decision is None:
                if _is_answer_request(text):
                    resp = last_response or "I don't have a recent response to share."
                    words = resp.split()
                    if len(words) > SUMMARY_WORD_THRESHOLD:
                        resp = (
                            " ".join(words[:SUMMARY_WORD_THRESHOLD])
                            + ". See the chat for more."
                        )
                    decision = {
                        "action": "answer",
                        "spoken": resp,
                        "message": "",
                        "command": {},
                    }
                else:
                    decision = {
                        "action": "forward",
                        "message": text + VOICE_HINT,
                        "spoken": "",
                        "command": {},
                    }

            reply = {"type": "decision", **decision}
            await websocket.send(json.dumps(reply))

            log.debug("[%s] '%s' -> %s", project or "?", text[:50], decision["action"])

    except websockets.ConnectionClosed:
        pass
    finally:
        log.info("Client disconnected: %s", addr)


# ── Entry point ────────────────────────────────────────────────────────────────


async def _serve(host: str, port: int) -> None:
    log.info("Listening on ws://%s:%s", host, port)
    async with websockets.serve(handle_client, host, port):
        await asyncio.Future()  # run forever


def main() -> None:
    setup_logging("cyrus")
    parser = argparse.ArgumentParser(
        description="Cyrus Remote Brain (WebSocket server)"
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Interface to bind (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=SERVER_PORT,
        help="Port to listen on (default: 8765)",
    )
    args = parser.parse_args()
    asyncio.run(_serve(args.host, args.port))


if __name__ == "__main__":
    main()
