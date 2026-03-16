# Plan 005: Extract Shared Code into cyrus_common.py

## Summary

Extract ~15 shared functions, 3 classes, and 8 constants/regex patterns from `cyrus2/main.py` and `cyrus2/cyrus_brain.py` into a new `cyrus2/cyrus_common.py` module. Eliminates ~1,500 lines of duplication. Both entry points import from `cyrus_common`, making every subsequent refactor a single-file change.

Scope includes targeted refactoring of main.py's class construction to match cyrus_brain.py's callback-based patterns (per interview Q1: "refactor main.py first, then extract shared code"). This is limited to parameter changes at call sites — no new features, no architectural changes.

## Dependencies

**Requires Issue 002** (state: PLANNED). Plan 002 copies all 7 v1 Python files from the project root into `cyrus2/` and applies Ruff formatting. `cyrus2/main.py` and `cyrus2/cyrus_brain.py` must exist before this issue proceeds.

## Key Findings from Gap Analysis

### Three tiers of duplication

| Tier | Items | Difficulty | Lines saved |
|------|-------|-----------|-------------|
| **1. Pure functions** | 9 functions | Trivial — identical implementations | ~400 |
| **2. Constants** | 8 constants/regexes | Trivial — identical (except MAX_SPEECH_WORDS) | ~60 |
| **3. Classes** | ChatWatcher, PermissionWatcher, SessionManager | Medium — different communication patterns | ~1,200 |

### Method-level comparison of classes

**ChatWatcher** (main.py ~lines 456–701, brain ~lines 403–637):

| Method | Status | Difference |
|--------|--------|-----------|
| `__init__` | Identical | — |
| `last_spoken` (property) | Identical | — |
| `flush_pending()` | **Different** | main.py takes `tts_queue, loop`; brain takes `loop`, uses global `_speak_queue` |
| `_find_webview()` | Identical | — |
| `_walk()` | Identical | — |
| `_extract_response()` | Identical | Logic same, only comment differences |
| `start()` | **Major diff** | Brain adds: `comtypes.CoInitializeEx`, coord caching, `_hook_spoken_until` skip, 3-tuple speak, websocket chime |

**PermissionWatcher** (main.py ~lines 706–962, brain ~lines 638–1026):

| Method | Status | Difference |
|--------|--------|-----------|
| `__init__` | **Different** | Brain adds 5 fields: `_vscode_win`, `_pre_armed*` (4). Plus `_AUTO_ALLOWED_TOOLS` class var |
| `is_pending` / `prompt_pending` | Identical | — |
| `_find_webview()` | **Minor diff** | Brain caches `self._vscode_win` |
| `_scan_window_for_permission()` | **Brain only** | ARIA live region scanning for VS Code Quick Pick dialogs |
| `_scan()` | **Major diff** | Brain: 2-stage detection (webview + Quick Pick), coord caching |
| `arm_from_hook()` | **Brain only** | Pre-arms from SDK PreToolUse hook |
| `handle_response()` | **Major diff** | Brain: dual-mode keyboard/button approval with "keyboard" sentinel |
| `handle_prompt_response()` | Identical | Only print prefix differs |
| `start()` | **Major diff** | Brain: complex state machine with 20s timeout, poll ticks, pre-arm upgrade |

**SessionManager** (main.py ~lines 967–1048, brain ~lines 1027–1104):

| Method | Status | Difference |
|--------|--------|-----------|
| `__init__` | Identical | — |
| `aliases` / `multi_session` / `perm_watchers` | Identical | — |
| `on_session_switch()` | **Different** | main.py takes `tts_queue`; print prefix differs |
| `last_response()` | Identical | — |
| `recent_responses()` | **main.py only** | Returns last N responses from a project's watcher |
| `rename_alias()` | Identical | — |
| `_add_session()` | **Major diff** | Brain sends whisper_prompt update via websocket; different params |
| `start()` | **Different** | main.py takes `tts_queue`; print prefix differs |

### Critical difference: communication patterns

The classes are ~90% identical in logic but differ in how they output speech/chimes:

- **main.py**: passes `tts_queue` explicitly, calls `play_chime()` (local audio via numpy/pygame)
- **cyrus_brain.py**: uses module-global `_speak_queue`, calls `_send_threadsafe({"type": "chime"}, loop)` (websocket to voice service)

cyrus_brain.py is the **evolved** version — a strict superset of main.py's functionality. Every difference falls into:
1. **Brain enhancements** — additional features (hook pre-arming, Quick Pick scanning, coord caching, timeout state machine). Including these in the common class is **harmless** to main.py since they're guarded by state that main.py never activates.
2. **Architectural integration** — how the class communicates with the outside world (speak queue, chime notification, print labels, whisper prompt updates). These are **parameterized** via constructor injection.

### Out of scope

- `_execute_cyrus_command()` — Issue 007 (dispatch table refactor)
- `main()` function decomposition — Issue 008
- `submit_to_vscode()` / `_find_chat_input()` — fundamentally different implementations (UIA-only vs extension+pixel-coords+threaded). Not shared code.
- `cyrus_voice.py` deduplication — also has `_FILLER_RE`, `_HALLUCINATIONS`. Should import from common in a follow-up issue.

## Ambiguity Resolution

Eight divergences identified between the two files. Resolutions:

1. **`_resolve_project` differs**: cyrus_brain.py normalizes the query (dashes/underscores → spaces via the same regex as `_make_alias`) and returns the longest-matching alias. main.py does simple `.lower().strip()` and returns the first dict-iteration match. **Resolution: use cyrus_brain.py's version** — it's strictly more robust for multi-word project names.

2. **`clean_for_speech` differs**: cyrus_brain.py calls `_sanitize_for_speech()` to replace Unicode characters (em dash, smart quotes, bullets) that garble TTS output. main.py omits this call. **Resolution: use cyrus_brain.py's version.** Extract both `_sanitize_for_speech` and the updated `clean_for_speech`. main.py gains TTS quality improvement.

3. **`play_chime` / `play_listen_chime` differ fundamentally**: main.py synthesizes audio locally (numpy + pygame); cyrus_brain.py sends IPC messages `{"type": "chime"}` to the voice service. These are different implementations for different architectures. **Resolution: callback registration pattern.** `cyrus_common.py` defines `play_chime(loop=None)` and `play_listen_chime(loop=None)` that dispatch to a registered handler via `register_chime_handlers()`. Each entry point registers its backend at startup.

4. **`MAX_SPEECH_WORDS` has different values** (main.py=30, cyrus_brain.py=50). **Resolution: per interview Q3, extract with default=50 and per-file override.** `clean_for_speech()` accepts an optional `max_words` parameter defaulting to `MAX_SPEECH_WORDS`. main.py passes `max_words=30` at call sites.

5. **`_HALLUCINATIONS` only exists in main.py**: Whisper hallucination filter used by `transcribe()`. **Resolution: extract to common anyway.** It belongs alongside other speech-processing constants. cyrus_brain.py simply doesn't import it.

6. **`ChatWatcher` class diverges** in `flush_pending()` and `start()`. **Resolution: dependency injection.** `ChatWatcher.__init__` accepts `enqueue_speech_fn` and `chime_fn` callables. The extracted version uses cyrus_brain.py as base (superset). Both entry points supply their own dispatch functions when constructing instances.

7. **`PermissionWatcher` class diverges**: cyrus_brain.py adds pre-arm state, `_AUTO_ALLOWED_TOOLS` whitelist, `arm_from_hook()`, `_scan_window_for_permission()`. **Resolution: extract cyrus_brain.py's version (superset).** main.py gains pre-arm capability (inert — won't activate unless `arm_from_hook()` is explicitly called). `PermissionWatcher.__init__` accepts `speak_urgent_fn` and `stop_speech_fn` callables.

8. **`SessionManager` class diverges**: cyrus_brain.py omits `tts_queue` parameter, adds IPC whisper-prompt push, uses `[Brain]` log prefix. **Resolution:** `SessionManager.__init__` accepts factory functions (`make_chat_watcher_fn`, `make_perm_watcher_fn`) and callbacks (`on_whisper_prompt_fn`). Both entry points supply their own factories. Print prefix is configurable but not critical — use `[Session]` in common.

## Design Decisions

### D1. Use cyrus_brain.py versions as canonical base

Since main.py is being deprecated (Issue 006), cyrus_brain.py's implementations are canonical. They are a superset of main.py's features. Where implementations differ, cyrus_brain.py's wins.

### D2. Callback-based communication for classes

Per interview Q1 ("refactor main.py first, then extract"), introduce callback parameters so classes are decoupled from their output mechanism:

```python
class ChatWatcher:
    def __init__(self, project_name, target_subname,
                 enqueue_speech_fn, chime_fn):
        self._enqueue_speech = enqueue_speech_fn  # (project, text, full_text?)
        self._chime = chime_fn                     # () -> None
```

Each entry point wires its own callbacks:
- **main.py**: `enqueue_speech_fn` → puts into tts_queue; `chime_fn` → plays local audio
- **cyrus_brain.py**: `enqueue_speech_fn` → puts into _speak_queue; `chime_fn` → sends websocket message

### D3. MAX_SPEECH_WORDS: parameter override

```python
MAX_SPEECH_WORDS = 50  # default in cyrus_common

def clean_for_speech(text: str, max_words: int = MAX_SPEECH_WORDS) -> str:
    ...
```
- `cyrus_brain.py`: calls `clean_for_speech(text)` → uses default 50
- `main.py`: calls `clean_for_speech(text, max_words=30)` → overrides

### D4. Chime dispatch via registration

```python
# cyrus_common.py
_chime_handler = None
_listen_chime_handler = None

def register_chime_handlers(chime_fn, listen_chime_fn):
    global _chime_handler, _listen_chime_handler
    _chime_handler = chime_fn
    _listen_chime_handler = listen_chime_fn

def play_chime(loop=None):
    if _chime_handler:
        _chime_handler(loop=loop)

def play_listen_chime(loop=None):
    if _listen_chime_handler:
        _listen_chime_handler(loop=loop)
```

Both implementations accept an optional `loop` parameter. main.py's local audio handler ignores it; cyrus_brain.py's IPC handler uses it. This satisfies the AC ("both import from cyrus_common") while preserving architecture-specific behavior.

### D5. Extra constants extracted opportunistically

`WAKE_WORDS` and `VOICE_HINT` are duplicated identically across both files but not explicitly listed in the issue. Extract them anyway — per codebase principle "fix everything you see."

### D6. Interview Q&A compliance

1. **Q1 — service-delegation refactoring**: "Part of 005's scope." Implemented by converting main.py to use the same callback patterns as brain before extraction. The factory functions (`_make_chat_watcher`, `_make_perm_watcher`) are the service-delegation layer.
2. **Q2 — `_sanitize_for_speech()`**: "Only extract to cyrus_common.py and have cyrus_brain.py import it." Extracted in Step 1. brain imports it explicitly. main.py benefits indirectly through `clean_for_speech()` which calls it internally.
3. **Q3 — `MAX_SPEECH_WORDS`**: "Extract to cyrus_common.py with a per-file override mechanism." Default = 50 in common. main.py calls `clean_for_speech(text, max_words=30)` to override. See D3.

### D7. `_fast_command` return type

Both files return `dict | None`. The issue import block shows a return type of `tuple[str, list[str]] | None` — this is incorrect. Use the actual return type from the code: `dict | None`.

## Implementation Steps

### Step 1: Verify Prerequisites

```bash
cd /home/daniel/Projects/barf/cyrus
test -f cyrus2/main.py && echo "OK" || echo "BLOCKED: Issue 002 not complete"
test -f cyrus2/cyrus_brain.py && echo "OK" || echo "BLOCKED: Issue 002 not complete"
```

If either file is missing, fail with "Blocked by Issue 002".

Record baseline line counts:

```bash
wc -l cyrus2/main.py cyrus2/cyrus_brain.py
```

### Step 2: Create cyrus_common.py — Imports, Constants, and Pure Functions

**File**: `cyrus2/cyrus_common.py`

Create the module with: imports → constants/regex → pure functions → chime registration.

**Imports**:

```python
"""Shared utilities for Cyrus voice assistant.

Extracted from main.py and cyrus_brain.py to eliminate duplication.
Both entry points import from this module.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from collections import deque

import pyautogui
import pygetwindow as gw
import pyperclip
import uiautomation as auto

try:
    import comtypes
except ImportError:
    comtypes = None

try:
    import numpy as np
    import pygame
    _HAS_AUDIO = True
except ImportError:
    np = None
    pygame = None
    _HAS_AUDIO = False
```

`numpy`/`pygame` are needed for the local audio chime handler (registered by main.py). `comtypes` is needed for `CoInitializeEx()` in class polling threads. Both gated behind try/except so cyrus_brain.py can import cyrus_common without pulling in audio deps.

**Constants to extract** (with source):

| Constant | Source | Value/Notes |
|----------|--------|-------------|
| `VSCODE_TITLE` | Both (identical) | `"Visual Studio Code"` |
| `_CHAT_INPUT_HINT` | Both (identical) | `"Message input"` |
| `MAX_SPEECH_WORDS` | cyrus_brain.py value | `50` — main.py overrides to 30 via param |
| `WAKE_WORDS` | Both (identical) | Set of 18 phonetic variants |
| `VOICE_HINT` | Both (identical) | Voice mode instruction string |
| `_FILLER_RE` | Both (identical) | Compiled regex for filler words |
| `_ANSWER_RE` | Both (identical) | Compiled regex for answer/recap requests |
| `_HALLUCINATIONS` | main.py only | Compiled regex for Whisper hallucinations |

**Pure functions to extract** (with source preference):

| Function | Source | Rationale |
|----------|--------|-----------|
| `_extract_project(title: str) -> str` | Either (identical) | |
| `_make_alias(proj: str) -> str` | Either (identical) | |
| `_resolve_project(query: str, aliases: dict) -> str \| None` | **cyrus_brain.py** | Normalizes query, sorts candidates by length |
| `_vs_code_windows() -> list[tuple[str, str]]` | Either (identical) | |
| `_sanitize_for_speech(text: str) -> str` | cyrus_brain.py (exclusive) | Unicode → ASCII for TTS |
| `clean_for_speech(text: str, max_words: int = MAX_SPEECH_WORDS) -> str` | **cyrus_brain.py** | Includes `_sanitize_for_speech` call; add `max_words` param |
| `_strip_fillers(text: str) -> str` | Either (identical) | |
| `_is_answer_request(text: str) -> bool` | Either (identical) | |
| `_fast_command(text: str) -> dict \| None` | main.py | Has docstring; body identical |

**Chime registration** (see Design Decision D4):

Add `register_chime_handlers()`, `play_chime(loop=None)`, `play_listen_chime(loop=None)`.

**Verification**:

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
python3 -m py_compile cyrus_common.py
python3 -c "from cyrus_common import _extract_project, _make_alias, clean_for_speech, play_chime; print('OK')"
```

### Step 3: Add ChatWatcher Class

Take cyrus_brain.py's `ChatWatcher` as the base (superset). Refactor to use callbacks:

**Constructor change**:

```python
def __init__(self, project_name="", target_subname="",
             enqueue_speech_fn=None, chime_fn=None):
    # ... existing init from cyrus_brain.py ...
    self._enqueue_speech = enqueue_speech_fn or (lambda *a: None)
    self._chime = chime_fn or (lambda: None)
```

**flush_pending change** — remove both `tts_queue` and `_speak_queue` dependency:

```python
def flush_pending(self) -> int:
    items = self._pending_queue[:]
    self._pending_queue.clear()
    for text in items:
        self._enqueue_speech(self.project_name, text, None)
    return len(items)
```

**start() poll loop change** — replace hardcoded queue/send calls:

```python
# Where active session speaks:
self._enqueue_speech(self.project_name, spoken, response)

# Where inactive session chimes:
self._pending_queue.append(spoken)
self._chime()
```

**Keep cyrus_brain extras**: `comtypes.CoInitializeEx()`, `_chat_input_coords` caching, hook suppression via `_hook_spoken_until`. These are gated by optional attributes (defaults to 0/empty — main.py is unaffected).

**Verification**:

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
python3 -c "from cyrus_common import ChatWatcher; print('OK')"
```

### Step 4: Add PermissionWatcher Class

Take cyrus_brain.py's `PermissionWatcher` as the base (superset). Refactor:

**Constructor change**:

```python
def __init__(self, project_name="", target_subname="",
             speak_urgent_fn=None, stop_speech_fn=None):
    # ... existing init from cyrus_brain.py ...
    self._speak_urgent = speak_urgent_fn or (lambda text: None)
    self._stop_speech = stop_speech_fn or (lambda: None)
```

**start() poll loop change** — replace `_send_threadsafe({"type": "stop_speech"}, loop)` with `self._stop_speech()`, replace `asyncio.run_coroutine_threadsafe(_speak_urgent(prompt), loop)` with `self._speak_urgent(prompt)`.

**Keep all cyrus_brain extras**: `_AUTO_ALLOWED_TOOLS`, pre-arming state machine, `_scan_window_for_permission()`, `_pending_since` timeout, `comtypes.CoInitializeEx()`. main.py won't use pre-arming (gated by `self._pre_armed` which defaults to False).

**Verification**:

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
python3 -c "from cyrus_common import PermissionWatcher; print('OK')"
```

### Step 5: Add SessionManager Class

Take cyrus_brain.py's `SessionManager` as the base. Refactor:

**Constructor change**:

```python
def __init__(self, make_chat_watcher_fn=None, make_perm_watcher_fn=None,
             on_whisper_prompt_fn=None):
    self._chat_watchers = {}
    self._perm_watchers = {}
    self._aliases = {}
    self._make_chat_watcher = make_chat_watcher_fn
    self._make_perm_watcher = make_perm_watcher_fn
    self._on_whisper_prompt = on_whisper_prompt_fn or (lambda text: None)
```

**_add_session change** — use factory functions instead of direct construction:

```python
def _add_session(self, proj, subname, loop):
    global _whisper_prompt
    alias = _make_alias(proj)
    self._aliases[alias] = proj
    names = " ".join(p for p in self._chat_watchers) + f" {proj}"
    _whisper_prompt = f"Cyrus, switch to {names.strip()}."
    self._on_whisper_prompt(_whisper_prompt)

    cw = self._make_chat_watcher(proj, subname, loop)
    self._chat_watchers[proj] = cw

    pw = self._make_perm_watcher(proj, subname, loop)
    self._perm_watchers[proj] = pw
```

**on_session_switch change** — no more tts_queue param:

```python
def on_session_switch(self, proj):
    cw = self._chat_watchers.get(proj)
    if cw:
        n = cw.flush_pending()
        if n:
            print(f"Flushed {n} queued response(s) from {proj}")
```

**Include `recent_responses()`** — exists only in main.py but is a pure accessor. Include in common (harmless for brain, useful for main.py):

```python
def recent_responses(self, proj: str, n: int = 3) -> list[str]:
    cw = self._chat_watchers.get(proj)
    return list(cw._response_history)[-n:] if cw else []
```

The `_whisper_prompt` global is accessed by both files for transcription context. Since SessionManager moves to cyrus_common.py, the `on_whisper_prompt_fn` callback handles propagation: each caller updates its own module-level state as needed.

**Verification**:

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
python3 -c "from cyrus_common import SessionManager; print('OK')"
```

### Step 6: Full Import Smoke Test

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
python3 -c "
from cyrus_common import (
    VSCODE_TITLE, _CHAT_INPUT_HINT, MAX_SPEECH_WORDS,
    WAKE_WORDS, VOICE_HINT,
    _FILLER_RE, _HALLUCINATIONS, _ANSWER_RE,
    _extract_project, _make_alias, _resolve_project, _vs_code_windows,
    _sanitize_for_speech, clean_for_speech, _strip_fillers,
    _is_answer_request, _fast_command,
    play_chime, play_listen_chime, register_chime_handlers,
    ChatWatcher, PermissionWatcher, SessionManager,
)
print('OK: all 22 symbols imported successfully')
"
```

### Step 7: Update cyrus2/cyrus_brain.py — Imports, Factories, Remove Duplicates

**Add import block** near top (after existing third-party imports):

```python
from cyrus_common import (
    # Constants
    VSCODE_TITLE, _CHAT_INPUT_HINT, MAX_SPEECH_WORDS,
    WAKE_WORDS, VOICE_HINT,
    _FILLER_RE, _ANSWER_RE,
    # Pure functions
    _extract_project, _make_alias, _resolve_project, _vs_code_windows,
    _sanitize_for_speech, clean_for_speech, _strip_fillers,
    _is_answer_request, _fast_command,
    play_chime, play_listen_chime, register_chime_handlers,
    # Classes
    ChatWatcher, PermissionWatcher, SessionManager,
)
```

Note: `_HALLUCINATIONS` NOT imported — brain doesn't transcribe.

**Wire callbacks** — create factory functions:

```python
def _make_chat_watcher(proj, subname, loop):
    def enqueue(project, text, full_text=None):
        msg = (project, text) if full_text is None else (project, text, full_text)
        asyncio.run_coroutine_threadsafe(_speak_queue.put(msg), loop)

    def chime():
        _send_threadsafe({"type": "chime"}, loop)

    def is_active():
        with _active_project_lock:
            return _active_project == proj

    cw = ChatWatcher(proj, subname, enqueue_speech_fn=enqueue, chime_fn=chime)
    cw.start(loop, is_active_fn=is_active)
    return cw

def _make_perm_watcher(proj, subname, loop):
    def speak_urgent(text):
        asyncio.run_coroutine_threadsafe(_speak_urgent(text), loop)

    def stop_speech():
        _send_threadsafe({"type": "stop_speech"}, loop)

    pw = PermissionWatcher(proj, subname, speak_urgent_fn=speak_urgent, stop_speech_fn=stop_speech)
    pw.start(loop)
    return pw
```

**Register chime handlers** early in `main()`:

```python
register_chime_handlers(
    chime_fn=lambda loop=None: _send_threadsafe({"type": "chime"}, loop) if loop else None,
    listen_chime_fn=lambda loop=None: _send_threadsafe({"type": "listen_chime"}, loop) if loop else None,
)
```

**Construct SessionManager** with factories:

```python
session_mgr = SessionManager(
    make_chat_watcher_fn=_make_chat_watcher,
    make_perm_watcher_fn=_make_perm_watcher,
    on_whisper_prompt_fn=lambda text: _send_threadsafe(
        {"type": "whisper_prompt", "text": text}, loop
    ),
)
```

**Delete all duplicate definitions** from cyrus_brain.py:

- Constants: `VSCODE_TITLE`, `_CHAT_INPUT_HINT`, `MAX_SPEECH_WORDS`, `WAKE_WORDS`, `VOICE_HINT`
- Regex: `_FILLER_RE`, `_ANSWER_RE`
- Functions: `_extract_project`, `_make_alias`, `_resolve_project`, `_vs_code_windows`, `_sanitize_for_speech`, `clean_for_speech`, `_strip_fillers`, `_is_answer_request`, `_fast_command`
- Classes: `ChatWatcher`, `PermissionWatcher`, `SessionManager`

**Keep cyrus_brain-specific code**:

- `_send_threadsafe()`, `_speak_worker()`, `_speak_urgent()` — websocket communication
- `_execute_cyrus_command()` — refactored in Issue 007
- `_start_active_tracker()`, `_find_chat_input()`, `submit_to_vscode()` — brain-specific implementations
- `main()` — brain entry point
- All module-level state variables (`_active_project`, `_speak_queue`, `_voice_writer`, etc.)

**Verification**:

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
python3 -m py_compile cyrus_brain.py
```

### Step 8: Update cyrus2/main.py — Imports, Factories, Remove Duplicates

**Add import block**:

```python
from cyrus_common import (
    # Constants
    VSCODE_TITLE, _CHAT_INPUT_HINT,
    WAKE_WORDS, VOICE_HINT,
    _FILLER_RE, _ANSWER_RE, _HALLUCINATIONS,
    # Pure functions
    _extract_project, _make_alias, _resolve_project, _vs_code_windows,
    clean_for_speech, _strip_fillers,
    _is_answer_request, _fast_command,
    play_chime, play_listen_chime, register_chime_handlers,
    # Classes
    ChatWatcher, PermissionWatcher, SessionManager,
)
```

**Register local audio chime handlers** early in `main()`:

Rename main.py's original `play_chime` / `play_listen_chime` to `_local_play_chime` / `_local_play_listen_chime` (kept as private functions for audio synthesis). Then register:

```python
register_chime_handlers(
    chime_fn=lambda loop=None: _local_play_chime(),
    listen_chime_fn=lambda loop=None: _local_play_listen_chime(),
)
```

**Wire callbacks** — same factory pattern as brain but using tts_queue:

```python
def _make_chat_watcher(proj, subname, tts_queue, loop):
    def enqueue(project, text, full_text=None):
        asyncio.run_coroutine_threadsafe(tts_queue.put((project, text)), loop)

    def is_active():
        with _active_project_lock:
            return _active_project == proj

    cw = ChatWatcher(proj, subname, enqueue_speech_fn=enqueue, chime_fn=play_chime)
    cw.start(loop, is_active_fn=is_active)
    return cw
```

**Update `clean_for_speech` calls** — pass `max_words=30` at each call site to preserve main.py's current behavior.

**Delete all duplicate definitions** from main.py:

- Constants: `VSCODE_TITLE`, `_CHAT_INPUT_HINT`, `WAKE_WORDS`, `VOICE_HINT`, `MAX_SPEECH_WORDS`
- Regex: `_FILLER_RE`, `_ANSWER_RE`, `_HALLUCINATIONS`
- Functions: `_extract_project`, `_make_alias`, `_resolve_project`, `_vs_code_windows`, `clean_for_speech`, `_strip_fillers`, `_is_answer_request`, `_fast_command`
- Classes: `ChatWatcher`, `PermissionWatcher`, `SessionManager`

Note: Do NOT delete `play_chime` / `play_listen_chime` — rename them to `_local_play_chime` / `_local_play_listen_chime` and keep as the audio backend.

**Keep main.py-specific code**:

- Audio/VAD imports (`numpy`, `sounddevice`, `torch`, `silero_vad`, `faster_whisper`, `pygame`)
- GPU detection, Whisper/VAD config constants
- `vad_loop()`, `transcribe()` — voice-specific
- `_local_play_chime()`, `_local_play_listen_chime()` — local audio synthesis (registered as handlers)
- `_execute_cyrus_command()` — refactored in Issue 007
- `_speak_urgent()`, TTS pipeline functions — main.py TTS
- `main()` — monolith entry point

**Verification**:

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
python3 -m py_compile main.py
```

### Step 9: Verify No Duplicate Definitions Remain

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2

# Functions — each should appear ONLY in cyrus_common.py
for fn in _extract_project _make_alias _resolve_project _vs_code_windows \
          _sanitize_for_speech clean_for_speech _strip_fillers \
          _is_answer_request _fast_command; do
    hits=$(grep -l "^def ${fn}" main.py cyrus_brain.py 2>/dev/null)
    if [ -n "$hits" ]; then
        echo "FAIL: def ${fn} still in: $hits"
    fi
done

# Classes — each should appear ONLY in cyrus_common.py
for cls in ChatWatcher PermissionWatcher SessionManager; do
    hits=$(grep -l "^class ${cls}" main.py cyrus_brain.py 2>/dev/null)
    if [ -n "$hits" ]; then
        echo "FAIL: class ${cls} still in: $hits"
    fi
done

echo "Duplicate check complete"
```

Each function/class should appear exactly once (in `cyrus_common.py`).

### Step 10: Verify No Circular Imports

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
python3 -c "import cyrus_common; print('cyrus_common OK')"
python3 -c "import cyrus_brain; print('cyrus_brain OK')"
python3 -c "import main; print('main OK')"
```

`cyrus_common.py` must NOT import from `main.py` or `cyrus_brain.py`. Full import may fail due to hardware-specific dependencies (CUDA, Windows UIA). The critical check is that `cyrus_common` imports cleanly and neither entry point has `ImportError` for `cyrus_common` symbols.

### Step 11: Ruff Lint and Format Check

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
ruff check cyrus_common.py main.py cyrus_brain.py
ruff format --check cyrus_common.py main.py cyrus_brain.py
```

Fix any violations before completing. All three files must pass both checks.

### Step 12: Line Count Comparison

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
echo "=== Post-extraction line counts ==="
wc -l main.py cyrus_brain.py cyrus_common.py
echo ""
echo "Targets:"
echo "  cyrus_common.py: ~900-1,100 lines"
echo "  main.py: ~900-1,000 lines (down from ~1,755)"
echo "  cyrus_brain.py: ~700-850 lines (down from ~1,773)"
echo "  Duplication eliminated: ~1,500+ lines"
```

## Acceptance Criteria Mapping

| Criterion | Verified by |
|-----------|-------------|
| `cyrus2/cyrus_common.py` created with all shared functions/classes | Steps 2–6 |
| All functions/classes from C3 extraction list present | Step 6 (full import test) |
| Both files import from `cyrus_common.py` | Steps 7–8 (import blocks) |
| No duplicate function/class definitions across files | Step 9 (grep check) |
| ~2,000 lines of duplication eliminated | Step 12 (line count) |
| All tests pass | Steps 10, 11 (import + lint checks) |

## Risk Assessment

**Medium risk.** Largest single refactoring in the sprint — touches the 2 biggest files and creates a new module.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Runtime behavior change from `_resolve_project` upgrade | Low — improves matching | Low | cyrus_brain version proven in production |
| Callback wiring errors in class factories | Medium — runtime failures | Medium | Step 6 smoke test; Step 10 import check |
| `comtypes.CoInitializeEx()` missing in main.py poll threads | Low — Windows-only | Medium | Gate behind try/except in common |
| Module-global state (`_whisper_prompt`, `_active_project`) | Medium — subtle bugs | Low | Globals stay in caller modules; common uses callbacks only |
| `_chat_input_coords` caching after ChatWatcher moves | Low — brain feature | Low | Pass as optional dict param or instance attribute |
| Import weight of numpy/pygame in common | None — gated | None | try/except makes deps optional |

**Known limitations**:

- `_execute_cyrus_command()` remains duplicated — addressed by Issue 007
- `_start_active_tracker()`, `_find_chat_input()`, `submit_to_vscode()` remain in both files — addressed by later issues
- No unit tests added in this issue — Issue 009 covers that
- Full end-to-end verification requires Windows + GPU hardware
- `cyrus_voice.py` also has `_FILLER_RE` and `_HALLUCINATIONS` — should import from common in a follow-up
