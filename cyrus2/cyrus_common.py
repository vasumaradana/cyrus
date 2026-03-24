"""
cyrus_common.py — Shared utilities for Cyrus 2.0

Constants, helper functions, and core classes shared between
cyrus_brain.py and main.py.

Chime handlers must be registered at startup via register_chime_handlers().
Classes use constructor-injected callbacks to decouple communication
patterns (TTS queue + local audio vs. websocket IPC).
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from collections import deque
from collections.abc import Callable

# HEADLESS is read from cyrus_config so that a single env var (CYRUS_HEADLESS=1)
# disables all Windows GUI code across both this module and cyrus_brain.py.
from cyrus_config import HEADLESS

try:
    import comtypes
    import pyautogui
    import pygetwindow as gw
    import pyperclip

    _HAS_UIA = True
except ImportError:
    _HAS_UIA = False

try:
    import uiautomation as auto
except Exception:
    try:
        import importlib
        import os as _os
        import shutil

        import comtypes.gen  # type: ignore[import]

        _gen_dir = _os.path.dirname(comtypes.gen.__file__)
        shutil.rmtree(_gen_dir, ignore_errors=True)
        _os.makedirs(_gen_dir, exist_ok=True)
        with open(_os.path.join(_gen_dir, "__init__.py"), "w") as _f:
            _f.write("# auto-generated\n")
        importlib.invalidate_caches()
        import uiautomation as auto  # type: ignore[import]

        _HAS_UIA = True
    except Exception:
        auto = None  # type: ignore[assignment]
        _HAS_UIA = False

# ── Module logger ──────────────────────────────────────────────────────────────
log = logging.getLogger("cyrus.common")

# Dedicated security audit logger for permission events — use this logger (not
# 'log') so callers can filter permission events with `grep "cyrus.permission"`.
_perm_log = logging.getLogger("cyrus.permission")

# ── Configuration ──────────────────────────────────────────────────────────────

VSCODE_TITLE = "Visual Studio Code"
_CHAT_INPUT_HINT = "Message input"

# Default word cap for spoken responses.  main.py overrides to 30 via
# the max_words parameter on clean_for_speech().
MAX_SPEECH_WORDS = 50

# Phonetic Whisper variants for the "Cyrus" wake word
WAKE_WORDS = {
    "cyrus",
    "sire",
    "sirius",
    "serious",
    "cyprus",
    "virus",
    "sirus",
    "cirus",
    "sy",
    "sir",
    "sarush",
    "surus",
    "saras",
    "serus",
    "situs",
    "cirrus",
    "serous",
    "ceres",
}

# Appended to every forwarded message so Claude keeps responses voice-friendly
VOICE_HINT = (
    "\n\n[Voice mode: keep explanations to 2-3 sentences. "
    "For code changes show only the modified section, not the full file.]"
)

# ── Regex patterns ─────────────────────────────────────────────────────────────

_FILLER_RE = re.compile(
    r"^(?:uh+|um+|er+|so|okay|ok|right|hey|please|can you|could you|would you)\s+",
    re.IGNORECASE,
)

# Phrases Whisper hallucinates on silence/noise (YouTube training data artefacts)
_HALLUCINATIONS = re.compile(
    r"thank(s| you) for watching"
    r"|see you (in the next|next time|again)"
    r"|don'?t forget to (like|subscribe)"
    r"|like and subscribe"
    r"|please subscribe"
    r"|subtitles by"
    r"|transcribed by",
    re.IGNORECASE,
)

_ANSWER_RE = re.compile(
    r"\b(recap|summarize?|summary)\b"
    r"|what\s+(did|was|were)\b.{0,40}\b(say|said|respond|answered?|told?|reply|replied)\b"
    r"|what\s+(you|claude|cyrus|it)\s+said\b"
    r"|\b(last\s+response|last\s+reply)\b"
    r"|\brepeat\s+(that|what\s+(you|claude|cyrus|it)\s+said)\b",
    re.IGNORECASE,
)

# ── Shared UIA caches (module-level, per-process) ──────────────────────────────

# project_name → UIA EditControl (for same-thread reuse)
_chat_input_cache: dict = {}
# Protects all reads/writes to _chat_input_cache across ChatWatcher and
# PermissionWatcher background threads.
_chat_input_cache_lock: threading.Lock = threading.Lock()

# proj → (cx, cy) pixel coords (cross-thread safe — plain ints, no COM objects)
_chat_input_coords: dict = {}
# Protects all reads/writes to _chat_input_coords across ChatWatcher,
# PermissionWatcher, and the submit thread in cyrus_brain.py.
_chat_input_coords_lock: threading.Lock = threading.Lock()

# ── Companion extension session registry (HEADLESS mode) ───────────────────────
# In HEADLESS mode, pygetwindow is unavailable so the companion extension
# registers sessions here via TCP messages on port 8770.
# Maps project_name → window subname
# (e.g. "myproject" → "myproject - Visual Studio Code").
# _vs_code_windows() reads this dict instead of calling gw.getAllWindows().
_registered_sessions: dict[str, str] = {}

# ── Chime registration ─────────────────────────────────────────────────────────

_chime_fn: Callable | None = None
_listen_chime_fn: Callable | None = None


def register_chime_handlers(
    chime_fn: Callable,
    listen_chime_fn: Callable,
) -> None:
    """Register chime handlers for local audio or websocket IPC dispatch.

    Must be called once at startup before any ChatWatcher or PermissionWatcher
    uses play_chime() / play_listen_chime().

    Args:
        chime_fn: Zero-argument callable that plays/sends a notification chime.
        listen_chime_fn: Zero-argument callable for the listen-start chime.
    """
    global _chime_fn, _listen_chime_fn
    _chime_fn = chime_fn
    _listen_chime_fn = listen_chime_fn


def play_chime() -> None:
    """Dispatch to the registered chime handler (no-op if unregistered)."""
    if _chime_fn is not None:
        _chime_fn()


def play_listen_chime() -> None:
    """Dispatch to the registered listen-chime handler (no-op if unregistered)."""
    if _listen_chime_fn is not None:
        _listen_chime_fn()


# ── Helper functions ────────────────────────────────────────────────────────────


def _extract_project(title: str) -> str:
    """Extract the project name from a VS Code window title.

    Examples:
        'main.py - cyrus - Visual Studio Code'  →  'cyrus'
        '● my-app - Visual Studio Code'  →  'my-app'
    """
    t = title.replace(" - Visual Studio Code", "").lstrip("● ").strip()
    parts = [p.strip() for p in t.split(" - ") if p.strip()]
    return parts[-1] if parts else "VS Code"


def _make_alias(proj: str) -> str:
    """Normalise a project name into a voice-friendly alias.

    Examples:
        'my-web-app'        →  'my web app'
        'backend_service'   →  'backend service'
    """
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", proj.lower())).strip()


def _resolve_project(query: str, aliases: dict) -> str | None:
    """Return the project_name whose alias best matches query, or None.

    Normalises query (dashes/underscores → spaces) before matching.
    Partial matches are supported; the longest matching alias wins.
    """
    # Normalise the same way aliases are built
    q = re.sub(r"\s+", " ", re.sub(r"[-_]", " ", query.lower())).strip()
    # Exact match first
    if q in aliases:
        return aliases[q]
    # Partial matches — prefer longest (most specific) alias match
    candidates = []
    for alias, proj in aliases.items():
        if q in alias or alias in q:
            candidates.append((len(alias), alias, proj))
    if candidates:
        candidates.sort(reverse=True)  # longest alias wins
        return candidates[0][2]
    return None


def _vs_code_windows() -> list[tuple[str, str]]:
    """Return [(project_name, subname), ...] for every open VS Code window.

    In HEADLESS mode, returns sessions registered by the companion extension
    (via _registered_sessions) instead of calling pygetwindow — which is
    unavailable on Linux / Docker deployments.
    """
    if HEADLESS:
        # Companion extension populates _registered_sessions via TCP messages.
        # Return a stable list snapshot; the caller must not hold the GIL across
        # slow operations while iterating this dict.
        return list(_registered_sessions.items())
    if not _HAS_UIA:
        return []
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for w in gw.getAllWindows():
        if VSCODE_TITLE not in (w.title or ""):
            continue
        proj = _extract_project(w.title)
        if proj not in seen:
            seen.add(proj)
            result.append((proj, f"{proj} - Visual Studio Code"))
    return result


def _sanitize_for_speech(text: str) -> str:
    """Replace Unicode chars that TTS engines read as garbled UTF-8 bytes."""
    return (
        text.replace("\u2014", ", ")  # em dash
        .replace("\u2013", ", ")  # en dash
        .replace("\u2026", "...")  # ellipsis
        .replace("\u2018", "'")  # left single quote
        .replace("\u2019", "'")  # right single quote
        .replace("\u201c", '"')  # left double quote
        .replace("\u201d", '"')  # right double quote
        .replace("\u2022", ", ")  # bullet
    )


def clean_for_speech(text: str, max_words: int = MAX_SPEECH_WORDS) -> str:
    """Strip markdown and truncate text to max_words for TTS output.

    Args:
        text: Raw markdown text from Claude.
        max_words: Maximum spoken word count before truncation (default 50).
                   Callers that prefer shorter output can pass max_words=30.
    """
    text = re.sub(r"```[\s\S]*?```", "See the chat for the code.", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\n[-*_]{3,}\n", " ", text)
    text = re.sub(r"\n\s*[-*•]\s+", ". ", text)
    text = re.sub(r"\n\s*\d+\.\s+", ". ", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    # Replace Unicode chars that TTS engines read as garbled UTF-8 bytes
    text = _sanitize_for_speech(text)
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]) + ". See the chat for the full response."
    return text.strip()


def _strip_fillers(text: str) -> str:
    """Strip leading filler words — handles stacked fillers like 'uh um fix it'."""
    prev = None
    while prev != text:
        prev = text
        text = _FILLER_RE.sub("", text).strip()
    return text


def _is_answer_request(text: str) -> bool:
    """Return True if the utterance asks Cyrus to replay/summarise the last response."""
    return bool(_ANSWER_RE.search(text))


def _fast_command(text: str) -> dict | None:
    """Regex fast-path for obvious Cyrus meta-commands.

    Returns a flat command dict or None if the utterance should be forwarded to
    the LLM. Each command dict contains at minimum a ``'command'`` key with the
    command type string. Optional keys carry parsed parameters.

    Command types and their optional parameters:

    - ``pause``        — optional ``duration`` (int, seconds)
    - ``unlock``       — optional ``password`` (str)
    - ``which_project``— no parameters
    - ``last_message`` — no parameters
    - ``switch``       — required ``project`` (str)
    - ``rename``       — required ``name`` (str, new name); optional ``old`` (str, hint)

    Examples::

        >>> _fast_command("pause")
        {'command': 'pause'}
        >>> _fast_command("pause for 10 seconds")
        {'command': 'pause', 'duration': 10}
        >>> _fast_command("unlock mypassword")
        {'command': 'unlock', 'password': 'mypassword'}
        >>> _fast_command("switch to myproject")
        {'command': 'switch', 'project': 'myproject'}
        >>> _fast_command("hello cyrus")

    """
    t = text.lower().strip().rstrip(".,!?")

    # ── pause / resume ────────────────────────────────────────────────────────
    # Check duration variant before bare pause so "pause for 5 seconds" is
    # captured with its parameter rather than matching the fullmatch below.
    m = re.match(r"pause\s+for\s+(\d+)\s+seconds?", t)
    if m:
        return {"command": "pause", "duration": int(m.group(1))}

    if re.fullmatch(r"pause|resume|stop listening|start listening", t):
        return {"command": "pause"}

    # ── unlock / auto ─────────────────────────────────────────────────────────
    # Password variant checked first so "unlock secret" captures the password.
    m = re.match(r"un ?lock\s+(.+)", t)
    if m:
        return {"command": "unlock", "password": m.group(1).strip()}

    if re.fullmatch(r"(un ?lock|auto|follow focus|auto(matic)? routing)", t):
        return {"command": "unlock"}

    # ── which project / what project ──────────────────────────────────────────
    if re.search(r"\b(which|what)\b.{0,20}\b(project|session)\b", t):
        return {"command": "which_project"}

    # ── last message / replay ─────────────────────────────────────────────────
    if re.fullmatch(r"(last|repeat|replay|again).{0,30}(message|response|said)?", t):
        return {"command": "last_message"}

    # ── switch to <name> — many natural phrasings ─────────────────────────────
    m = (
        re.match(r"(?:switch(?:ed)?(?: to)?|use|go to|open|activate)\s+(.+)", t)
        or re.match(r"make\s+(.+?)\s+(?:the\s+)?active", t)
        or re.match(
            r"(?:set|change)\s+(?:active\s+)?(?:project|session)\s+to\s+(.+)", t
        )
    )
    if m:
        return {"command": "switch", "project": m.group(1).strip()}

    # ── rename / relabel ──────────────────────────────────────────────────────
    # "rename [this] [session|window] to <new>" / "call this [session|window] <new>"
    # — checked before the two-arg form to avoid "this" being treated as old name.
    m = re.match(
        r"(?:rename|relabel)\s+(?:this\s+)?(?:session\s+|window\s+)?to\s+(.+)", t
    ) or re.match(r"call\s+this\s+(?:session\s+|window\s+)?(.+)", t)
    if m:
        return {"command": "rename", "name": m.group(1).strip()}

    # "rename project/session <new>" — shorthand for rename current session
    m = re.match(r"(?:rename|relabel)\s+(?:project|session)\s+(.+)", t)
    if m:
        return {"command": "rename", "name": m.group(1).strip()}

    # "rename <old> to <new>" — rename specific session by hint
    m = re.match(r"(?:rename|relabel)\s+(.+?)\s+to\s+(.+)", t)
    if m:
        return {
            "command": "rename",
            "name": m.group(2).strip(),
            "old": m.group(1).strip(),
        }

    return None


# ── Focus verification guard ───────────────────────────────────────────────────


def _assert_vscode_focus() -> None:
    """Verify VS Code has window focus; raise RuntimeError if it does not.

    Uses UIAutomation to walk up from the currently focused control to the
    top-level window and checks that its Name contains "Visual Studio Code".
    Called immediately before every pyautogui keystroke sequence to prevent
    misdirected input if focus changes mid-operation.

    Raises:
        RuntimeError: If the focused window is not VS Code, or if UIAutomation
            raises an exception while querying the focused control.
    """
    try:
        ctrl = auto.GetFocusedControl()
        # Walk up the UIA tree to find the top-level window name
        window_name: str = ctrl.Name if ctrl is not None else ""
        parent = ctrl.GetParentControl() if ctrl is not None else None
        while parent is not None:
            window_name = parent.Name
            parent = parent.GetParentControl()
    except Exception as exc:
        log.warning("Could not verify VS Code focus via UIAutomation: %s", exc)
        raise RuntimeError(f"Focus verification failed: {exc}") from exc

    if "Visual Studio Code" not in window_name:
        log.error("Focus mismatch: %s (not VS Code)", window_name)
        raise RuntimeError(f"VS Code not focused, got {window_name!r}")


# ── Chat Watcher ───────────────────────────────────────────────────────────────


class ChatWatcher:
    """Polls a Claude Code chat webview via UIA.

    When a new response stabilises, either forwards it to the speech
    backend (active session) or holds it in _pending_queue and calls
    the chime handler (non-active session).

    Args:
        project_name: Display name for the VS Code project.
        target_subname: VS Code window SubName for UIA search.
        enqueue_speech_fn: Callable(project_name, text, full_text=None) —
            enqueues text for TTS (captures loop/queue internally).
        chime_fn: Zero-argument callable — signals a queued response.
    """

    POLL_SECS = 0.5
    STABLE_SECS = 1.2

    _STOP = {
        "Edit automatically",
        "Show command menu (/)",
        "ctrl esc to focus or unfocus Claude",
        "Message input",
    }
    _SKIP = {
        "Thinking",
        "Message actions",
        "Copy code to clipboard",
        "Stop",
        "Regenerate",
        "tasks",
        "New session",
        "Ask before edits",
    }

    def __init__(
        self,
        project_name: str = "",
        target_subname: str = "",
        *,
        enqueue_speech_fn: Callable | None = None,
        chime_fn: Callable | None = None,
        max_speech_words: int = MAX_SPEECH_WORDS,
    ) -> None:
        self._chat_doc = None
        self._last_text = ""
        self._last_change = 0.0
        self._last_spoken = ""
        self._new_submission_pending = False
        self._pending_queue: list[str] = []
        self._response_history: deque = deque(maxlen=10)
        self.project_name = project_name
        self._target_sub = target_subname or VSCODE_TITLE
        self._max_speech_words = max_speech_words
        # Callbacks — no-ops if not provided
        self._enqueue_speech_fn: Callable = enqueue_speech_fn or (lambda *a, **kw: None)
        self._chime_fn: Callable = chime_fn or (lambda: None)

    @property
    def last_spoken(self) -> str:
        """Most recently spoken response text."""
        return self._last_spoken

    def flush_pending(self) -> int:
        """Enqueue all pending (non-active session) responses for TTS.

        Returns:
            Number of responses flushed.
        """
        items = self._pending_queue[:]
        self._pending_queue.clear()
        for text in items:
            self._enqueue_speech_fn(self.project_name, text)
        return len(items)

    def _find_webview(self):
        """Locate the Claude Code chat DocumentControl via UIA."""
        vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
        if not vscode.Exists(3):
            return None
        chrome = vscode.PaneControl(
            searchDepth=12, ClassName="Chrome_RenderWidgetHostHWND"
        )
        if not chrome.Exists(2):
            return None
        docs: list[tuple[int, auto.Control]] = []

        def collect(ctrl, d=0):
            if d > 15:
                return
            try:
                if ctrl.ControlTypeName == "DocumentControl":
                    docs.append((d, ctrl))
            except Exception:
                pass
            try:
                child = ctrl.GetFirstChildControl()
                while child:
                    collect(child, d + 1)
                    child = child.GetNextSiblingControl()
            except Exception:
                pass

        collect(chrome)
        unnamed = [(d, c) for d, c in docs if not (c.Name or "").strip()]
        if unnamed:
            return unnamed[-1][1]
        return docs[-1][1] if docs else None

    def _walk(self, ctrl, depth=0, max_depth=12, out=None):
        """Walk UIA accessibility tree; collect (depth, type, name) tuples."""
        if out is None:
            out = []
        if depth > max_depth:
            return out
        try:
            name = (ctrl.Name or "").strip()
            ctype = ctrl.ControlTypeName or ""
            if len(name) >= 4:
                out.append((depth, ctype, name))
        except Exception:
            pass
        try:
            child = ctrl.GetFirstChildControl()
            while child:
                self._walk(child, depth + 1, max_depth, out)
                child = child.GetNextSiblingControl()
        except Exception:
            pass
        return out

    def _extract_response(self, results):
        """Extract the latest Claude response from a UIA walk result.

        Anchor strategy:
          - "Message input" EditControl is a reliable end-of-chat marker.
          - Last "Thinking" ButtonControl before it marks the start of
            Claude's final response block.
          - Fallback: last "Message actions" before "Message input".
        """
        msg_input_pos = next(
            (
                i
                for i, (_, ct, tx) in enumerate(results)
                if ct == "EditControl" and tx == _CHAT_INPUT_HINT
            ),
            -1,
        )
        if msg_input_pos == -1:
            return ""

        # Primary: last "Thinking" button before Message input
        start = -1
        for i, (_, ctype, text) in enumerate(results[:msg_input_pos]):
            if ctype == "ButtonControl" and "Thinking" in text:
                start = i

        # Secondary: last "Message actions" before Message input
        if start == -1:
            for i, (_, ctype, text) in enumerate(results[:msg_input_pos]):
                if ctype == "ButtonControl" and text == "Message actions":
                    start = i

        if start == -1:
            return ""

        parts: list[str] = []
        seen: set[str] = set()

        for _, ctype, text in results[start + 1 : msg_input_pos]:
            if text in self._STOP:
                break
            if ctype == "ButtonControl" and text == "Message actions":
                break  # end of Claude's response block; user's next message follows
            if text in self._SKIP or len(text) < 4:
                continue
            if ctype not in ("TextControl", "ListItemControl"):
                continue
            if text not in seen and not any(
                text in s for s in seen if len(s) > len(text)
            ):
                seen.add(text)
                parts.append(text)

        return " ".join(parts)

    def start(
        self,
        loop: asyncio.AbstractEventLoop | None = None,  # accepted but not used
        is_active_fn: Callable | None = None,
    ) -> None:
        """Spawn the background polling thread.

        Args:
            loop: Accepted for API compatibility but unused (callbacks capture loop).
            is_active_fn: Zero-argument callable returning True when this
                session is the active one.
        """
        if is_active_fn is None:

            def is_active_fn() -> bool:
                return True

        def poll():
            if HEADLESS:
                # In HEADLESS mode, the hook's Stop event (port 8767) is the
                # sole chat notification path. UIA polling is unavailable on
                # Linux/Docker where Windows GUI libraries are absent.
                return
            if _HAS_UIA:
                try:
                    comtypes.CoInitializeEx()
                except Exception:
                    pass
            while self._chat_doc is None:
                self._chat_doc = self._find_webview()
                if self._chat_doc is None:
                    time.sleep(2)
            label = f"[{self.project_name}] " if self.project_name else ""
            print(f"[Cyrus] {label}Connected to Claude Code chat panel.")

            # Populate chat input coords early — direct EditControl search.
            # Check under lock; do UIA work outside lock (no blocking inside lock).
            with _chat_input_coords_lock:
                needs_coords = self.project_name not in _chat_input_coords
            if needs_coords and _HAS_UIA:
                try:
                    vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
                    if vscode.Exists(1):
                        ctrl = vscode.EditControl(searchDepth=20, Name=_CHAT_INPUT_HINT)
                        if ctrl.Exists(2):
                            r = ctrl.BoundingRectangle
                            if r.width() > 0:
                                coords_val = (
                                    (r.left + r.right) // 2,
                                    (r.top + r.bottom) // 2,
                                )
                                with _chat_input_coords_lock:
                                    _chat_input_coords[self.project_name] = coords_val
                                print(
                                    f"[Cyrus] {label}Chat input coords cached: "
                                    f"{coords_val}"
                                )
                except Exception as e:
                    print(f"[Cyrus] {label}Coords cache error: {e}")

            seed = ""
            for _ in range(6):
                try:
                    seed = self._extract_response(self._walk(self._chat_doc))
                    if seed:
                        break
                except Exception:
                    seed = ""
                time.sleep(1.0)
            self._last_spoken = seed
            self._last_text = seed
            self._last_change = time.time()

            while True:
                time.sleep(self.POLL_SECS)
                try:
                    results = self._walk(self._chat_doc)
                    response = self._extract_response(results)
                    now = time.time()

                    # Detect new user submission via Message actions count
                    msg_actions_count = sum(
                        1
                        for _, ct, tx in results
                        if ct == "ButtonControl" and tx == "Message actions"
                    )
                    if msg_actions_count != getattr(
                        self, "_last_msg_actions_count", -1
                    ):
                        prev = getattr(self, "_last_msg_actions_count", -1)
                        self._last_msg_actions_count = msg_actions_count
                        if prev != -1 and msg_actions_count > prev:
                            self._new_submission_pending = True

                    if response != self._last_text:
                        self._last_text = response
                        self._last_change = now
                        if self._new_submission_pending:
                            self._new_submission_pending = False
                            self._last_spoken = ""
                    elif response and response != self._last_spoken:
                        if now - self._last_change >= self.STABLE_SECS:
                            self._last_spoken = response
                            # Hook already spoke this response — suppress ChatWatcher
                            if now < getattr(self, "_hook_spoken_until", 0):
                                continue
                            if not seed:
                                seed = response
                                continue
                            spoken = clean_for_speech(
                                response, max_words=self._max_speech_words
                            )
                            self._response_history.append(spoken)
                            preview = spoken[:80] + ("..." if len(spoken) > 80 else "")
                            print(
                                f"\nCyrus [{self.project_name or 'Claude'}]: {preview}"
                            )

                            if is_active_fn():
                                self._enqueue_speech_fn(
                                    self.project_name, spoken, response
                                )
                            else:
                                self._pending_queue.append(spoken)
                                self._chime_fn()
                                print(
                                    f"[queued: {self.project_name}] "
                                    f"{len(self._pending_queue)} message(s) waiting"
                                )

                except Exception:
                    self._chat_doc = None
                    while self._chat_doc is None:
                        self._chat_doc = self._find_webview()
                        if self._chat_doc is None:
                            time.sleep(2)

        threading.Thread(target=poll, daemon=True).start()


# ── Permission Watcher ─────────────────────────────────────────────────────────


class PermissionWatcher:
    """Polls Claude Code's chat webview for permission dialogs and input prompts.

    Uses the VS Code ARIA live region and Quick Pick scanning in addition
    to chat webview scanning for reliable permission detection.

    Args:
        project_name: Display name for the VS Code project.
        target_subname: VS Code window SubName for UIA search.
        speak_urgent_fn: Callable(prompt: str) — interrupts TTS and speaks
            the permission prompt immediately.
        stop_speech_fn: Zero-argument callable — stops current TTS playback.
    """

    POLL_SECS = 0.3
    ALLOW_WORDS = {"yes", "allow", "sure", "ok", "okay", "proceed", "yep", "yeah", "go"}
    DENY_WORDS = {"no", "deny", "cancel", "stop", "nope", "reject"}

    _SKIP_PROMPT_NAMES = {_CHAT_INPUT_HINT, ""}
    _SKIP_PROMPT_LABELS = {"search", "find", "replace", "filter", "go to line"}

    # Tools that never trigger permission dialogs — always auto-allowed
    _AUTO_ALLOWED_TOOLS = {
        "Read",
        "Grep",
        "Glob",
        "Agent",
        "TodoWrite",
        "TodoRead",
        "AskFollowupQuestion",
        "AskUserQuestion",
        "Skill",
        "ToolSearch",
        "TaskOutput",
        "TaskStop",
    }

    def __init__(
        self,
        project_name: str = "",
        target_subname: str = "",
        *,
        speak_urgent_fn: Callable | None = None,
        stop_speech_fn: Callable | None = None,
    ) -> None:
        self._chat_doc = None
        self._vscode_win = None  # cached VS Code WindowControl
        self._pending = False
        self._allow_btn = None
        self._announced = ""
        self._pre_armed = False  # hook pre-armed, waiting for UIA confirmation
        self._pre_armed_tool = ""
        self._pre_armed_cmd = ""
        self._pre_armed_since = 0.0
        self._prompt_pending = False
        self._prompt_input_ctrl = None
        self._prompt_announced = ""
        self.project_name = project_name
        self._target_sub = target_subname or VSCODE_TITLE
        # Callbacks — no-ops if not provided
        self._speak_urgent_fn: Callable = speak_urgent_fn or (lambda prompt: None)
        self._stop_speech_fn: Callable = stop_speech_fn or (lambda: None)

    @property
    def is_pending(self) -> bool:
        """True while a permission dialog is awaiting a voice response."""
        return self._pending

    @property
    def prompt_pending(self) -> bool:
        """True while an input prompt is awaiting a voice response."""
        return self._prompt_pending

    def _find_webview(self):
        """Locate the Claude Code chat DocumentControl via UIA."""
        vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
        if not vscode.Exists(3):
            return None
        self._vscode_win = vscode
        chrome = vscode.PaneControl(
            searchDepth=12, ClassName="Chrome_RenderWidgetHostHWND"
        )
        if not chrome.Exists(2):
            return None
        docs: list[tuple[int, auto.Control]] = []

        def collect(ctrl, d=0):
            if d > 15:
                return
            try:
                if ctrl.ControlTypeName == "DocumentControl":
                    docs.append((d, ctrl))
            except Exception:
                pass
            try:
                child = ctrl.GetFirstChildControl()
                while child:
                    collect(child, d + 1)
                    child = child.GetNextSiblingControl()
            except Exception:
                pass

        collect(chrome)
        unnamed = [(d, c) for d, c in docs if not (c.Name or "").strip()]
        if unnamed:
            return unnamed[-1][1]
        return docs[-1][1] if docs else None

    def _scan_window_for_permission(self):
        """Scan the VS Code workbench Chrome pane for the permission dialog.

        Uses the monaco-aria-container live region as a reliable signal.
        Returns (aria_text, found: bool).
        """
        try:
            vscode = self._vscode_win
            if vscode is None or not vscode.Exists(0):
                vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
                if not vscode.Exists(1):
                    return "", False
                self._vscode_win = vscode

            chrome = vscode.PaneControl(
                searchDepth=20, ClassName="Chrome_RenderWidgetHostHWND"
            )
            if not chrome.Exists(1):
                return "", False

            aria_text = ""
            found_perm = False

            def walk(ctrl, d=0):
                nonlocal aria_text, found_perm
                if d > 8:
                    return
                try:
                    name = (ctrl.Name or "").strip()
                    cls = ctrl.ClassName or ""
                    # ARIA live region — VS Code announces permission dialogs here
                    if (
                        cls == "monaco-alert"
                        and "requesting permission" in name.lower()
                    ):
                        aria_text = name
                        found_perm = True
                    # Also catch if "Allow this" appears directly at shallow depth
                    if "Allow this" in name:
                        found_perm = True
                        if not aria_text:
                            aria_text = name
                except Exception:
                    pass
                try:
                    child = ctrl.GetFirstChildControl()
                    while child:
                        walk(child, d + 1)
                        child = child.GetNextSiblingControl()
                except Exception:
                    pass

            walk(chrome)
            return aria_text, found_perm
        except Exception:
            return "", False

    def _scan(self):
        """Walk the chat doc once; return (perm_btn, cmd, prompt_ctrl, prompt_label)."""
        if not self._chat_doc:
            return None, "", None, ""
        items: list[tuple[int, str, str, object]] = []

        def walk(ctrl, d=0):
            if d > 12:
                return
            try:
                name = (ctrl.Name or "").strip()
                ctype = ctrl.ControlTypeName or ""
                if name:
                    items.append((d, ctype, name, ctrl))
            except Exception:
                pass
            try:
                child = ctrl.GetFirstChildControl()
                while child:
                    walk(child, d + 1)
                    child = child.GetNextSiblingControl()
            except Exception:
                pass

        walk(self._chat_doc)

        # Cache chat input pixel coords (plain ints — no COM cross-thread issues).
        # Check under lock; UIA work is done outside lock (no blocking inside lock).
        with _chat_input_coords_lock:
            needs_coords = self.project_name not in _chat_input_coords
        if needs_coords:
            for _, ctype, name, ctrl in items:
                if ctype == "EditControl" and name == _CHAT_INPUT_HINT:
                    with _chat_input_cache_lock:
                        _chat_input_cache[self.project_name] = ctrl
                    try:
                        r = ctrl.BoundingRectangle
                        if r.width() > 0 and r.height() > 0:
                            with _chat_input_coords_lock:
                                _chat_input_coords[self.project_name] = (
                                    (r.left + r.right) // 2,
                                    (r.top + r.bottom) // 2,
                                )
                    except Exception:
                        pass
                    break

        # ── Permission detection: chat webview first, then VS Code window scan ─
        perm_btn, perm_cmd = None, ""

        # 1. Webview scan — "Yes, allow" button in chat panel
        allow_idx = next(
            (
                i
                for i, (_, ct, n, _) in enumerate(items)
                if ct in ("TextControl", "StaticTextControl") and "Allow this" in n
            ),
            -1,
        )
        if allow_idx != -1:
            cmd = ""
            for _, ct2, n2, _ in items[allow_idx + 1 : allow_idx + 10]:
                if ct2 == "TextControl" and len(n2) > 2:
                    cmd = n2
                    break
            for _, ctype, name, ctrl in items[allow_idx : allow_idx + 20]:
                if ctype == "ButtonControl" and re.search(
                    r"\byes\b|\ballow\b", name, re.IGNORECASE
                ):
                    perm_btn, perm_cmd = ctrl, cmd
                    break

        # 2. VS Code native Quick Pick scan (no button ctrl — keyboard approval)
        if not perm_btn:
            cmd, found = self._scan_window_for_permission()
            if found:
                # Sentinel: perm_btn="keyboard" signals keyboard-based approval
                perm_btn = "keyboard"
                perm_cmd = cmd

        prompt_ctrl, prompt_label = None, ""
        for i, (_, ctype, name, ctrl) in enumerate(items):
            if ctype != "EditControl":
                continue
            if name in self._SKIP_PROMPT_NAMES:
                continue
            label = ""
            for j in range(max(0, i - 10), i):
                _, ct2, n2, _ = items[j]
                if ct2 not in ("TextControl", "StaticTextControl"):
                    continue
                n2s = n2.strip().lower()
                if not n2s or n2s in self._SKIP_PROMPT_LABELS or len(n2) < 4:
                    continue
                label = n2.strip()
                break
            if label:
                prompt_ctrl, prompt_label = ctrl, label
                break

        return perm_btn, perm_cmd, prompt_ctrl, prompt_label

    def arm_from_hook(
        self,
        tool: str,
        cmd: str,
        loop: asyncio.AbstractEventLoop | None = None,  # accepted but unused
    ) -> None:
        """Arm from PreToolUse hook.

        Skip auto-allowed tools; announce others immediately via speak_urgent_fn.
        """
        if tool in self._AUTO_ALLOWED_TOOLS:
            return  # never needs permission
        if self._pending:
            return  # already waiting for a response
        self._allow_btn = "keyboard"
        self._pending = True
        self._pending_since = time.time()
        self._announced = f"hook:{cmd}"
        prefix = f"In {self.project_name}: " if self.project_name else ""
        cmd_short = cmd[:120] if cmd else tool
        prompt = f"{prefix}Allow {tool}: {cmd_short}. Say yes or no."
        print(f"\n[Permission/hook] {prefix}{tool}: {cmd}")
        # Security audit: record every permission request for the audit trail.
        _perm_log.info(
            "Permission requested: tool=%s cmd=%s project=%s",
            tool,
            cmd[:120],
            self.project_name,
        )
        self._stop_speech_fn()
        self._speak_urgent_fn(prompt)

    def handle_response(self, text: str) -> bool:
        """Handle a yes/no voice response to a pending permission dialog.

        Returns True if the response was consumed (yes or no).
        """
        if not self._pending or not self._allow_btn:
            return False
        # Guard: verify VS Code has focus before sending any keystrokes.
        # Abort and clear pending state if focus has drifted to another window.
        try:
            _assert_vscode_focus()
        except RuntimeError as _focus_err:
            print(f"[Cyrus] Focus check failed, aborting response: {_focus_err}")
            self._pending = False
            self._allow_btn = None
            return True
        words = set(text.lower().strip().split())
        if words & self.ALLOW_WORDS:
            print(f"[Cyrus] → Allowing command ({self.project_name or 'session'})")
            # Security audit: record the approved permission with its utterance.
            _perm_log.info(
                "Permission APPROVED: cmd=%s utterance=%r project=%s",
                self._announced,
                text.strip(),
                self.project_name,
            )
            if self._allow_btn == "keyboard":
                # Native VS Code Quick Pick: press "1" to select "1 Yes"
                vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
                if vscode.Exists(1):
                    try:
                        vscode.SetFocus()
                    except Exception:
                        pass
                pyautogui.press("1")
            else:
                clicked = False
                try:
                    self._allow_btn.Click()
                    clicked = True
                except Exception:
                    pass
                if not clicked:
                    pyautogui.press("enter")
            self._pending = False
            self._allow_btn = None
            return True
        if words & self.DENY_WORDS:
            print(f"[Cyrus] → Cancelling command ({self.project_name or 'session'})")
            # Security audit: record the denied permission with its utterance.
            _perm_log.info(
                "Permission DENIED: cmd=%s utterance=%r project=%s",
                self._announced,
                text.strip(),
                self.project_name,
            )
            vscode = auto.WindowControl(searchDepth=1, SubName=self._target_sub)
            if vscode.Exists(1):
                try:
                    vscode.SetFocus()
                except Exception:
                    pass
            pyautogui.press("escape")
            self._pending = False
            self._allow_btn = None
            return True
        return False

    def handle_prompt_response(self, text: str) -> bool:
        """Handle a voice response to a pending input prompt.

        Returns True if the response was consumed.
        """
        if not self._prompt_pending or not self._prompt_input_ctrl:
            return False
        # Guard: verify VS Code has focus before sending any keystrokes.
        # Abort and clear prompt state if focus has drifted to another window.
        try:
            _assert_vscode_focus()
        except RuntimeError as _focus_err:
            print(f"[Cyrus] Focus check failed, aborting prompt response: {_focus_err}")
            self._prompt_pending = False
            self._prompt_input_ctrl = None
            return True
        cancel = {
            "cancel",
            "escape",
            "never mind",
            "nevermind",
            "stop",
            "dismiss",
            "close",
        }
        if text.lower().strip() in cancel:
            pyautogui.press("escape")
            print(f"[Cyrus] → Dismissed prompt ({self.project_name or 'session'})")
        else:
            try:
                self._prompt_input_ctrl.SetFocus()
                time.sleep(0.05)
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.02)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.05)
                pyautogui.press("enter")
                print(f"[Cyrus] → Prompt answered: {text!r}")
            except Exception as e:
                print(f"[Cyrus] Prompt input error: {e}")
        self._prompt_pending = False
        self._prompt_input_ctrl = None
        return True

    def start(
        self,
        loop: asyncio.AbstractEventLoop | None = None,  # accepted but unused
    ) -> None:
        """Spawn the background permission-polling thread.

        Args:
            loop: Accepted for API compatibility but unused (callbacks capture loop).
        """

        def poll():
            if HEADLESS:
                # In HEADLESS mode, arm_from_hook() is the sole permission
                # trigger. UIA polling is unavailable on Linux/Docker where
                # Windows GUI libraries are absent. The companion extension
                # sends permission_respond messages instead of auto-clicking.
                return
            if _HAS_UIA:
                try:
                    comtypes.CoInitializeEx()
                except Exception:
                    pass
            while self._chat_doc is None:
                self._chat_doc = self._find_webview()
                if self._chat_doc is None:
                    time.sleep(2)

            _poll_tick = 0
            while True:
                time.sleep(self.POLL_SECS)
                _poll_tick += 1
                try:
                    btn, cmd, p_ctrl, p_label = self._scan()

                    # Every 5 polls (~1.5 s): also scan all Chrome panes for
                    # the VS Code native Quick Pick permission dialog
                    if not btn and _poll_tick % 5 == 0:
                        qp_cmd, qp_found = self._scan_window_for_permission()
                        if qp_found:
                            btn, cmd = "keyboard", qp_cmd

                    if btn:
                        if not self._pending:
                            # Dialog confirmed by UIA — announce it
                            self._allow_btn = btn
                            self._pending = True
                            self._pending_since = time.time()
                            # Use richer hook info if pre-armed, else UIA-scanned cmd
                            if self._pre_armed:
                                tool_label = self._pre_armed_tool
                                cmd_label = self._pre_armed_cmd[:120] or tool_label
                                self._announced = f"hook:{self._pre_armed_cmd}"
                            else:
                                tool_label = ""
                                cmd_label = cmd[:120] if cmd else ""
                                self._announced = cmd
                            self._pre_armed = False
                            prefix = (
                                f"In {self.project_name}: " if self.project_name else ""
                            )
                            if tool_label:
                                prompt = (
                                    f"{prefix}Allow {tool_label}: "
                                    f"{cmd_label}. Say yes or no."
                                )
                            else:
                                prompt = f"{prefix}Allow: {cmd_label}. Say yes or no."
                            print(
                                "\n[Permission] "
                                f"{prefix}Claude wants to run: {cmd_label}"
                            )
                            # Security audit: record every UIA-detected dialog.
                            _perm_log.info(
                                "Permission dialog detected: cmd=%s project=%s",
                                cmd_label,
                                self.project_name,
                            )
                            self._stop_speech_fn()
                            self._speak_urgent_fn(prompt)
                        elif btn != "keyboard" and self._allow_btn == "keyboard":
                            # Hook armed with keyboard fallback — upgrade to real
                            # UIA button
                            self._allow_btn = btn
                    elif not btn:
                        self._announced = ""
                        # Clear pre-arm if no dialog appeared within 2 s
                        if (
                            self._pre_armed
                            and time.time() > self._pre_armed_since + 2.0
                        ):
                            self._pre_armed = False
                        # Keep pending for 20 s after announcement so transient
                        # UIA misses don't clear it before the user responds.
                        if (
                            self._pending
                            and time.time() > getattr(self, "_pending_since", 0) + 20
                        ):
                            self._pending = False
                            self._allow_btn = None

                    if p_ctrl and p_label != self._prompt_announced:
                        self._prompt_input_ctrl = p_ctrl
                        self._prompt_pending = True
                        self._prompt_announced = p_label
                        prefix = (
                            f"In {self.project_name}: " if self.project_name else ""
                        )
                        prompt = f"{prefix}{p_label}"
                        print(f"\n[Input Prompt] {prompt}")
                        self._speak_urgent_fn(prompt)
                    elif not p_ctrl:
                        self._prompt_announced = ""
                        if self._prompt_pending:
                            self._prompt_pending = False
                            self._prompt_input_ctrl = None

                except Exception:
                    self._chat_doc = None
                    while self._chat_doc is None:
                        self._chat_doc = self._find_webview()
                        if self._chat_doc is None:
                            time.sleep(2)

        threading.Thread(target=poll, daemon=True).start()


# ── Session Manager ────────────────────────────────────────────────────────────


class SessionManager:
    """Manages per-project ChatWatcher and PermissionWatcher instances.

    Uses factory functions for creating watchers and a callback for
    whisper prompt updates, keeping this class decoupled from the
    specific communication backend.

    Args:
        make_chat_watcher_fn: Callable(project_name, subname) → ChatWatcher.
        make_perm_watcher_fn: Callable(project_name, subname) → PermissionWatcher.
        on_whisper_prompt_fn: Callable(prompt: str) — called when the Whisper
            prompt should be updated (e.g. to announce new sessions).
        is_active_project_fn: Zero-argument callable returning the current
            active project name (for is_active checks in ChatWatcher).
    """

    def __init__(
        self,
        *,
        make_chat_watcher_fn: Callable | None = None,
        make_perm_watcher_fn: Callable | None = None,
        on_whisper_prompt_fn: Callable | None = None,
        is_active_project_fn: Callable | None = None,
    ) -> None:
        self._chat_watchers: dict[str, ChatWatcher] = {}
        self._perm_watchers: dict[str, PermissionWatcher] = {}
        self._aliases: dict[str, str] = {}
        self._make_chat_watcher_fn = make_chat_watcher_fn
        self._make_perm_watcher_fn = make_perm_watcher_fn
        self._on_whisper_prompt_fn = on_whisper_prompt_fn
        self._is_active_project_fn = is_active_project_fn

    @property
    def aliases(self) -> dict[str, str]:
        """Copy of the current alias → project mapping."""
        return dict(self._aliases)

    @property
    def multi_session(self) -> bool:
        """True when more than one VS Code session is being watched."""
        return len(self._chat_watchers) > 1

    @property
    def perm_watchers(self) -> list[PermissionWatcher]:
        """List of all active PermissionWatcher instances."""
        return list(self._perm_watchers.values())

    def on_session_switch(self, proj: str) -> None:
        """Flush queued responses when the user switches to proj."""
        cw = self._chat_watchers.get(proj)
        if cw:
            n = cw.flush_pending()
            if n:
                print(f"[Cyrus] Flushed {n} queued response(s) from {proj}")

    def last_response(self, proj: str) -> str:
        """Return the last spoken response for proj, or empty string."""
        cw = self._chat_watchers.get(proj)
        return cw.last_spoken if cw else ""

    def recent_responses(self, proj: str, n: int = 3) -> list[str]:
        """Return the last n spoken responses for proj."""
        cw = self._chat_watchers.get(proj)
        return list(cw._response_history)[-n:] if cw else []

    def rename_alias(self, old_alias: str, new_alias: str, proj: str) -> None:
        """Replace an auto-generated alias with a user-chosen name."""
        self._aliases.pop(old_alias, None)
        self._aliases[new_alias.lower().strip()] = proj

    def _add_session(self, proj: str, subname: str) -> None:
        """Register a new VS Code session and start its watchers."""
        alias = _make_alias(proj)
        self._aliases[alias] = proj
        print(f'[Cyrus] Session detected: {proj}  (say "switch to {alias}")')

        # Build updated whisper prompt and notify via callback
        names = " ".join(p for p in self._chat_watchers) + f" {proj}"
        prompt = f"Cyrus, switch to {names.strip()}."
        if self._on_whisper_prompt_fn is not None:
            self._on_whisper_prompt_fn(prompt)

        # is_active closure: captures proj + is_active_project_fn
        if self._is_active_project_fn is not None:

            def is_active(p=proj) -> bool:
                return self._is_active_project_fn() == p

        else:

            def is_active() -> bool:
                return True

        # Create watchers via injected factories (fall back to bare constructors)
        if self._make_chat_watcher_fn is not None:
            cw = self._make_chat_watcher_fn(proj, subname)
        else:
            cw = ChatWatcher(project_name=proj, target_subname=subname)
        cw.start(is_active_fn=is_active)
        self._chat_watchers[proj] = cw

        if self._make_perm_watcher_fn is not None:
            pw = self._make_perm_watcher_fn(proj, subname)
        else:
            pw = PermissionWatcher(project_name=proj, target_subname=subname)
        pw.start()
        self._perm_watchers[proj] = pw

    def start(self) -> None:
        """Scan for VS Code windows and start a background scanner thread."""

        def scan():
            while True:
                try:
                    for proj, subname in _vs_code_windows():
                        if proj not in self._chat_watchers:
                            self._add_session(proj, subname)
                except Exception:
                    pass
                time.sleep(5)

        try:
            for proj, subname in _vs_code_windows():
                self._add_session(proj, subname)
        except Exception:
            pass

        if self.multi_session:
            names = " | ".join(f'"{a}"' for a in self._aliases)
            print(f"[Cyrus] {len(self._chat_watchers)} sessions: {names}")

        threading.Thread(target=scan, daemon=True).start()
