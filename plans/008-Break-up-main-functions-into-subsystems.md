# Plan 008: Break up main() functions into subsystems

## Summary

Extract subsystem initialization from the monolithic `main()` functions in `cyrus_brain.py` (68 lines) and `main.py` (291 lines) into dedicated `_init_*()` / `_parse_*()` functions. Each subsystem becomes independently callable and testable. Both `main()` functions reduced to < 50-line orchestrators with a documented startup sequence and improved error handling.

## Prerequisites

- **No hard blockers.** The issue says "Blocked By: None."
- **Benefits from Issue 005** (shared code extraction) and **Issue 006** (main.py deprecation):
  - If 006 is complete: `main.py` is already a thin wrapper (< 30 lines). **Skip all main.py steps.**
  - If 005 is complete: shared code lives in `cyrus_common.py`. Import paths may differ but subsystem decomposition is the same.
  - If neither is complete (current state): work on root-level files as-is.

## Key Findings from Gap Analysis

### Path discrepancy

The issue references `cyrus2/` paths but actual source files live at the project root (`/home/daniel/Projects/barf/cyrus/`). The `cyrus2/` directory is empty (Issue 002 hasn't executed). This plan uses root-level paths, consistent with Plans 005–007.

### cyrus_brain.py `main()` — Current state (68 lines, 1696–1764)

| Phase | Lines | Size | Description |
|---|---|---|---|
| Argument parsing | 1699–1702 | 4 | `argparse` for `--host`, `--port` |
| Queue creation | 1704–1706 | 3 | `_speak_queue`, `_utterance_queue`, event loop |
| Session manager | 1709–1716 | 8 | `SessionManager()`, `start()`, initial active project |
| Background threads | 1719–1726 | 8 | Focus tracker thread, submit worker thread |
| Async tasks | 1729–1732 | 4 | Speak worker task, routing loop task |
| Network servers | 1735–1757 | 23 | Voice TCP (8766), Hook TCP (8767), Mobile WS (8769) |
| Serve forever | 1759–1764 | 6 | `async with` + `asyncio.gather()` |

At 68 lines, the function is close to the < 50 target but still mixes argument parsing, session setup, worker lifecycle, and network server creation in one place. Extracting 3 cohesive subsystem functions achieves both the line count target and the testability goal.

### main.py `main()` — Current state (291 lines, 1435–1726)

| Phase | Lines | Size | Description |
|---|---|---|---|
| Argument parsing | 1435–1455 | 21 | `argparse` for `--remote`, WebSocket connect |
| Whisper loading | 1457–1464 | 8 | GPU detection, model loading |
| Kokoro TTS loading | 1466–1487 | 22 | ONNX session, GPU/CPU provider, fallback |
| Audio init | 1489–1505 | 17 | pygame, executor, queues, VAD thread |
| Session management | 1507–1525 | 19 | SessionManager, active project, TTS worker, focus tracker |
| Hotkey setup | 1527–1553 | 27 | 3 hotkey callbacks + registration |
| Startup sequence | 1556–1564 | 9 | Greeting + queue drain |
| **Routing loop** | **1566–1726** | **160** | Transcribe, wake word, route, dispatch — **inline** |

The 160-line inline routing loop is the elephant. Extracting it to `_routing_loop()` takes main() from 291 to ~131 lines. The remaining init extractions bring it under 50.

### No existing `_init_*` functions

Confirmed via grep: no `_init_*` functions exist in any project file. `SPRINT_ISSUES.md` has example patterns (lines 1061–1098) but they're documentation, not code.

### Subsystem extraction from the issue matches brain vs. voice split

The issue lists: VAD init, TTS init, routing loop, permission handling, session management, network setup, hotkey hooks. These map cleanly:

| Issue subsystem | File | Extraction target |
|---|---|---|
| VAD initialization | main.py only | `_init_whisper()` |
| TTS initialization | main.py only | `_init_tts()` |
| Routing loop | Both (different) | `_routing_loop()` in main.py; already separate in brain |
| Permission handling | Both (via SessionManager) | Part of `_init_session()` |
| Session management | Both | `_init_session()` |
| Network setup | cyrus_brain.py only | `_init_servers()` |
| Hotkey hooks | main.py only | `_init_hotkeys()` |

## Design Decisions

### D1. Subsystem grouping by cohesion

Group extractions by functional cohesion rather than by individual object. "Session initialization" includes SessionManager creation + start + initial project detection. "Background workers" includes focus tracker + submit thread + speak worker + routing task. This produces 3–4 well-sized functions per file rather than 8+ trivial ones.

### D2. Return initialized state; globals set by main()

Subsystem functions return their initialized objects so `main()` can wire them together. Globals (`_speak_queue`, `_utterance_queue`, `_active_project`) are set explicitly in `main()`, not hidden inside subsystem functions. Exception: `_init_session()` sets `_active_project` because it's part of the session detection logic and callers shouldn't need to know about it.

### D3. Error handling per subsystem severity

Each subsystem call in `main()` gets specific exception handling:

| Subsystem | Severity | On failure |
|---|---|---|
| Whisper model (main.py) | Fatal | `logger.exception()` + `sys.exit(1)` |
| TTS model (main.py) | Degradable | `logger.warning()` + continue (Edge TTS fallback) |
| Audio/pygame (main.py) | Fatal | `logger.exception()` + `sys.exit(1)` |
| Session manager (both) | Fatal | `logger.exception()` + `sys.exit(1)` |
| Network servers (brain) | Fatal | `logger.exception()` + `sys.exit(1)` |
| Hotkeys (main.py) | Degradable | `logger.warning()` + continue |
| Background workers (brain) | Fatal | `logger.exception()` + `sys.exit(1)` |

The `_init_*` functions themselves raise on failure — they don't catch internally. `main()` decides what's fatal vs. degradable.

### D4. Logging added, prints kept

Add `import logging` + `logger = logging.getLogger(__name__)` to both files (consistent with Plan 007). New `_init_*` functions use `logger.info()` for startup milestones and `logger.exception()` for errors. Existing `print()` calls within extracted code stay as-is — migration to logging is Issue 010's scope.

### D5. Routing loop extraction for main.py

The 160-line inline routing loop is extracted to `async def _routing_loop(whisper_model, utterance_queue, session_mgr, loop)`. Its internal structure is preserved — no logic changes, just moved to a standalone function. Breaking the routing loop *itself* into smaller pieces is beyond this issue's scope.

### D6. main.py work conditional on Issue 006

If Issue 006 has already replaced `main.py` with a thin wrapper (< 50 lines), all main.py steps are skipped. The builder checks this in Step 1.

### D7. No config.py creation

The issue mentions `cyrus2/config.py` as optional. It's not needed for the subsystem decomposition and would add scope. Configuration centralization is a separate concern.

## Implementation Steps — cyrus_brain.py

### Step 1: Check prerequisites and record baseline

```bash
cd /home/daniel/Projects/barf/cyrus

# Check if Issue 006 has already replaced main.py
MAIN_LINES=$(wc -l < main.py)
if [ "$MAIN_LINES" -lt 50 ]; then
    echo "SKIP main.py: already a thin wrapper ($MAIN_LINES lines)"
else
    echo "INCLUDE main.py: $MAIN_LINES lines — needs subsystem extraction"
fi

# Baseline
wc -l main.py cyrus_brain.py
```

**Verification**: Note whether main.py steps are needed.

### Step 2: Add logging import to cyrus_brain.py

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

Check if `import logging` already exists (may have been added by Issue 007). If not, add after existing imports:

```python
import logging

logger = logging.getLogger(__name__)
```

If `logging` is already imported, only add the `logger` line.

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 3: Extract `_parse_args()` from cyrus_brain.py

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

Add before `main()`, after the `# ── Main` section comment:

```python
def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the Brain service."""
    parser = argparse.ArgumentParser(description="Cyrus Brain — logic/watcher service")
    parser.add_argument("--host", default=BRAIN_HOST, help="Listen host")
    parser.add_argument("--port", type=int, default=BRAIN_PORT, help="Listen port")
    return parser.parse_args()
```

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 4: Extract `_init_session()` from cyrus_brain.py

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

```python
def _init_session(loop: asyncio.AbstractEventLoop) -> SessionManager:
    """Create and start the SessionManager, detect initial VS Code sessions.

    Returns the initialized SessionManager. Sets _active_project to the
    first detected VS Code window (if any).
    """
    global _active_project
    session_mgr = SessionManager()
    session_mgr.start(loop)

    first = _vs_code_windows()
    if first:
        with _active_project_lock:
            _active_project = first[0][0]
        logger.info("Initial active project: %s", first[0][0])
    else:
        logger.info("No VS Code sessions detected at startup")

    return session_mgr
```

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 5: Extract `_init_workers()` from cyrus_brain.py

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

```python
def _init_workers(session_mgr: SessionManager,
                  loop: asyncio.AbstractEventLoop) -> None:
    """Start background workers: focus tracker, submit thread, speak worker, routing loop.

    All workers are daemon threads or async tasks — they die when the process exits.
    """
    # Window focus tracker — updates _active_project on VS Code focus change
    threading.Thread(
        target=_start_active_tracker,
        args=(session_mgr, loop),
        daemon=True,
    ).start()

    # Dedicated VS Code submit thread — COM initialized once, stable apartment
    threading.Thread(target=_submit_worker, daemon=True).start()

    # Speak worker — forwards queued speak requests to voice
    asyncio.create_task(_speak_worker())

    # Routing loop — processes utterances from voice service
    asyncio.create_task(routing_loop(session_mgr, loop))

    logger.info("Background workers started")
```

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 6: Extract `_init_servers()` from cyrus_brain.py

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

```python
async def _init_servers(
    session_mgr: SessionManager,
    loop: asyncio.AbstractEventLoop,
    host: str,
    port: int,
) -> tuple:
    """Start all network servers: voice TCP, hook TCP, mobile WebSocket.

    Returns (voice_server, hook_server, mobile_server) for lifetime management.
    """
    # Voice TCP server (default port 8766)
    voice_server = await asyncio.start_server(
        lambda r, w: handle_voice_connection(r, w, session_mgr, loop),
        host, port,
    )
    addr = voice_server.sockets[0].getsockname()
    print(f"[Brain] Listening for voice service on {addr[0]}:{addr[1]}")

    # Hook TCP server (port 8767) — Claude Code Stop hook connects here
    hook_server = await asyncio.start_server(
        lambda r, w: handle_hook_connection(r, w, session_mgr),
        host, HOOK_PORT,
    )
    hook_addr = hook_server.sockets[0].getsockname()
    print(f"[Brain] Listening for Claude hooks on {hook_addr[0]}:{hook_addr[1]}")

    # Mobile WebSocket server (port 8769)
    mobile_server = await websockets.serve(
        handle_mobile_ws,
        host, MOBILE_PORT,
        ping_interval=None,
        ping_timeout=None,
    )
    print(f"[Brain] Listening for mobile clients on {host}:{MOBILE_PORT} (WebSocket)")
    print("[Brain] Waiting for voice to connect...")

    return voice_server, hook_server, mobile_server
```

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 7: Refactor cyrus_brain.py `main()`

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

Replace the entire `main()` body (lines 1696–1764) with:

```python
async def main() -> None:
    """Initialize and run the Cyrus Brain service.

    Startup sequence:
      1. Session manager started (scans VS Code windows)
      2. Background workers started (focus tracker, submit, speak, routing)
      3. Network servers started (voice TCP, hook TCP, mobile WS)
      4. Serve forever (blocking)
    """
    global _speak_queue, _utterance_queue

    args = _parse_args()

    _speak_queue     = asyncio.Queue()
    _utterance_queue = asyncio.Queue()
    loop             = asyncio.get_event_loop()

    try:
        session_mgr = _init_session(loop)
    except Exception:
        logger.exception("Failed to initialize session manager")
        raise SystemExit(1)

    _init_workers(session_mgr, loop)

    try:
        voice_server, hook_server, mobile_server = await _init_servers(
            session_mgr, loop, args.host, args.port,
        )
    except OSError:
        logger.exception("Failed to start network servers (port conflict?)")
        raise SystemExit(1)

    async with voice_server, hook_server:
        await asyncio.gather(
            voice_server.serve_forever(),
            hook_server.serve_forever(),
            mobile_server.wait_closed(),
        )
```

**Line count**: ~32 lines including docstring and error handling. Well under 50.

**What changed**:
- Argument parsing delegated to `_parse_args()`
- Session setup delegated to `_init_session()` with error handling
- Worker startup delegated to `_init_workers()`
- Server creation delegated to `_init_servers()` with port-conflict handling
- `global _active_project` removed from main() — moved to `_init_session()`
- Startup sequence documented in docstring

**What's preserved**:
- Queue globals still set in main() (D2)
- `async with` + `asyncio.gather()` serve pattern unchanged
- All behavior identical — pure extraction refactoring

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

### Step 8: Verify cyrus_brain.py main() line count

```bash
cd /home/daniel/Projects/barf/cyrus
python -c "
import ast, textwrap
source = open('cyrus_brain.py').read()
tree = ast.parse(source)
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'main':
        lines = node.end_lineno - node.lineno + 1
        print(f'main() is {lines} lines')
        assert lines < 50, f'FAIL: main() is {lines} lines (target: < 50)'
        print('PASS: < 50 lines')
        break
"
```

### Step 9: Lint and format cyrus_brain.py

```bash
cd /home/daniel/Projects/barf/cyrus
ruff check cyrus_brain.py 2>/dev/null || python -m py_compile cyrus_brain.py
ruff format cyrus_brain.py 2>/dev/null || true
```

Fix any violations.

## Implementation Steps — main.py (skip if Issue 006 is complete)

These steps only apply if `main.py` is still a monolith (> 50 lines). If Issue 006 has replaced it with a thin wrapper, skip to the test steps.

### Step 10: Add logging import to main.py

**File**: `/home/daniel/Projects/barf/cyrus/main.py`

```python
import logging

logger = logging.getLogger(__name__)
```

### Step 11: Extract `_parse_args()` from main.py

**File**: `/home/daniel/Projects/barf/cyrus/main.py`

```python
async def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments and connect to remote brain if specified."""
    global _remote_url, _remote_ws

    parser = argparse.ArgumentParser(description="Cyrus — voice layer for Claude Code")
    parser.add_argument(
        "--remote", metavar="URL",
        help="WebSocket URL of a remote Cyrus brain, e.g. ws://192.168.1.10:8765",
    )
    args = parser.parse_args()

    if args.remote:
        _remote_url = args.remote
        try:
            import websockets as _ws_lib
            _remote_ws = await _ws_lib.connect(_remote_url)
            print(f"[Cyrus] Connected to remote brain at {_remote_url}")
        except Exception as e:
            logger.warning("Could not connect to remote brain (%s) — using local routing", e)
            _remote_url = ""

    return args
```

### Step 12: Extract `_init_whisper()` from main.py

```python
def _init_whisper() -> "WhisperModel":
    """Load Whisper model for speech transcription.

    Detects GPU availability and selects appropriate device/compute type.
    Returns the loaded WhisperModel. Fatal on failure.
    """
    if _CUDA:
        print(f"[Cyrus] GPU: {_GPU_NAME}")
    else:
        print("[Cyrus] No CUDA/ROCm GPU detected — Whisper on CPU")

    print(f"Loading Whisper {WHISPER_MODEL} on {WHISPER_DEVICE}...")
    model = WhisperModel(WHISPER_MODEL,
                         device=WHISPER_DEVICE,
                         compute_type=WHISPER_COMPUTE_TYPE)
    logger.info("Whisper model loaded: %s on %s", WHISPER_MODEL, WHISPER_DEVICE)
    return model
```

### Step 13: Extract `_init_tts()` from main.py

```python
def _init_tts() -> None:
    """Load Kokoro TTS model if available.

    Sets the module-level _kokoro global. Non-fatal — falls back to Edge TTS
    if Kokoro model files are missing or loading fails.
    """
    global _kokoro

    if not (os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_VOICES)):
        print("[Cyrus] Kokoro model files not found — using Edge TTS fallback")
        print(f"         Expected: {KOKORO_MODEL}")
        return

    try:
        from kokoro_onnx import Kokoro as _KokoroClass
        import onnxruntime as _ort
        _ort.set_default_logger_severity(3)
        _providers = []
        if _CUDA:
            _providers.append(("CUDAExecutionProvider",
                               {"cudnn_conv_algo_search": "DEFAULT"}))
        _providers.append("CPUExecutionProvider")
        _session = _ort.InferenceSession(KOKORO_MODEL, providers=_providers)
        _kokoro = _KokoroClass.from_session(_session, KOKORO_VOICES)
        _active_providers = _session.get_providers()
        _tts_device = "GPU" if "CUDAExecutionProvider" in _active_providers else "CPU"
        print(f"[Cyrus] Kokoro TTS loaded ({_tts_device}) — voice: {TTS_VOICE}")
    except Exception as e:
        logger.warning("Kokoro load failed (%s) — using Edge TTS fallback", e)
```

### Step 14: Extract `_init_audio()` from main.py

```python
def _init_audio(loop: asyncio.AbstractEventLoop) -> tuple:
    """Initialize audio subsystem: pygame mixer, Whisper executor, queues, VAD thread.

    Returns (whisper_executor, tts_queue, utterance_queue).
    """
    global _whisper_executor, _tts_queue

    pygame.mixer.init()

    _whisper_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")
    _tts_queue = asyncio.Queue()
    utterance_queue: asyncio.Queue[np.ndarray] = asyncio.Queue()

    threading.Thread(
        target=vad_loop,
        args=(utterance_queue.put_nowait, loop),
        daemon=True,
    ).start()

    logger.info("Audio subsystem initialized")
    return _whisper_executor, _tts_queue, utterance_queue
```

### Step 15: Extract `_init_sessions()` from main.py

```python
def _init_sessions(loop: asyncio.AbstractEventLoop,
                   tts_queue: asyncio.Queue) -> SessionManager:
    """Create SessionManager, detect VS Code sessions, start watchers.

    Returns the initialized SessionManager.
    """
    global _active_project

    session_mgr = SessionManager()
    session_mgr.start(loop, tts_queue)

    first_windows = _vs_code_windows()
    if first_windows:
        with _active_project_lock:
            _active_project = first_windows[0][0]
        logger.info("Initial active project: %s", first_windows[0][0])

    asyncio.create_task(tts_worker(session_mgr))

    threading.Thread(
        target=_start_active_tracker,
        args=(session_mgr, tts_queue, loop),
        daemon=True,
    ).start()

    return session_mgr
```

### Step 16: Extract `_init_hotkeys()` from main.py

```python
def _init_hotkeys(loop: asyncio.AbstractEventLoop) -> None:
    """Register keyboard hotkeys: F9 pause, F7 stop, F8 clipboard.

    Non-fatal — logs warning if keyboard hooks fail.
    """
    def toggle_pause():
        if _user_paused.is_set():
            _user_paused.clear()
            print("[Cyrus resumed]")
        else:
            _user_paused.set()
            print(f"[Cyrus paused — press {KEY_PAUSE.upper()} to resume]")

    def stop_speech():
        _stop_speech.set()
        asyncio.run_coroutine_threadsafe(drain_tts_queue(), loop)

    def read_clipboard():
        try:
            text = pyperclip.paste().strip()
        except Exception:
            text = ""
        if text:
            asyncio.run_coroutine_threadsafe(_tts_queue.put(("", text)), loop)
        else:
            print("[Clipboard empty]")

    keyboard.add_hotkey(KEY_PAUSE,     toggle_pause)
    keyboard.add_hotkey(KEY_STOP,      stop_speech)
    keyboard.add_hotkey(KEY_READ_CLIP, read_clipboard)
    print(f"[Cyrus] F9 pause  |  F7 stop+clear  |  F8 clipboard  |  Ctrl+C exit")
    logger.info("Hotkeys registered")
```

### Step 17: Extract `_routing_loop()` from main.py

**File**: `/home/daniel/Projects/barf/cyrus/main.py`

Extract lines 1556–1726 (startup drain + main processing loop) into:

```python
async def _routing_loop(whisper_model: "WhisperModel",
                        utterance_queue: asyncio.Queue,
                        session_mgr: SessionManager,
                        loop: asyncio.AbstractEventLoop) -> None:
    """Main processing loop: transcribe audio, check wake words, route utterances.

    Runs forever until interrupted. Handles:
    - Startup queue drain (discard audio captured during TTS)
    - Whisper transcription of VAD chunks
    - TTS echo guard (only wake words interrupt playback)
    - Permission dialog binary responses
    - Wake word detection and follow-up listening
    - Command routing via _fast_command() and _execute_cyrus_command()
    - Forwarding to VS Code via submit_to_vscode()
    """
    global _conversation_active

    # Discard any audio captured during startup TTS
    await startup_sequence(session_mgr)
    while not utterance_queue.empty():
        try:
            utterance_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    # ... (entire while True loop from lines 1566-1726, unchanged)
```

Move the entire `while True:` block (lines 1566–1726) into this function body unchanged. The only changes are:
- Function signature added (whisper_model, utterance_queue, session_mgr, loop as params)
- `global _conversation_active` declaration moved here
- Startup sequence + queue drain moved here from main()
- No logic changes

### Step 18: Refactor main.py `main()`

Replace the entire main() body with:

```python
async def main() -> None:
    """Initialize and run Cyrus voice assistant.

    Startup sequence:
      1. Arguments parsed, remote brain connected (if specified)
      2. Whisper model loaded (enables transcription)
      3. TTS model loaded (enables speech output, fallback to Edge TTS)
      4. Audio subsystem initialized (VAD, pygame, queues)
      5. Session manager started (scans VS Code windows)
      6. Hotkeys registered (F7/F8/F9)
      7. Routing loop entered (transcribe, route, respond)
    """
    args = await _parse_args()

    try:
        whisper_model = _init_whisper()
    except Exception:
        logger.exception("Failed to load Whisper model")
        raise SystemExit(1)

    _init_tts()  # non-fatal — Edge TTS fallback

    loop = asyncio.get_event_loop()

    try:
        _, tts_queue, utterance_queue = _init_audio(loop)
    except Exception:
        logger.exception("Failed to initialize audio subsystem")
        raise SystemExit(1)

    try:
        session_mgr = _init_sessions(loop, tts_queue)
    except Exception:
        logger.exception("Failed to initialize session manager")
        raise SystemExit(1)

    try:
        _init_hotkeys(loop)
    except Exception:
        logger.warning("Hotkey registration failed — continuing without hotkeys")

    await _routing_loop(whisper_model, utterance_queue, session_mgr, loop)
```

**Line count**: ~35 lines including docstring and error handling. Well under 50.

### Step 19: Verify main.py main() line count

```bash
cd /home/daniel/Projects/barf/cyrus
python -c "
import ast
source = open('main.py').read()
tree = ast.parse(source)
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'main':
        lines = node.end_lineno - node.lineno + 1
        print(f'main() is {lines} lines')
        assert lines < 50, f'FAIL: main() is {lines} lines (target: < 50)'
        print('PASS: < 50 lines')
        break
"
```

### Step 20: Lint and format main.py

```bash
cd /home/daniel/Projects/barf/cyrus
ruff check main.py 2>/dev/null || python -m py_compile main.py
ruff format main.py 2>/dev/null || true
```

## Testing

### Step 21: Write tests

**File**: `/home/daniel/Projects/barf/cyrus/tests/test_subsystem_init.py`

Create `tests/` directory if it does not exist.

```python
"""Tests for Issue 008: Break up main() functions into subsystems."""

import ast
from pathlib import Path

CYRUS_ROOT = Path(__file__).resolve().parent.parent


def _get_function_lines(filepath: Path, func_name: str) -> int | None:
    """Return the line count of a function, or None if not found."""
    source = filepath.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                return node.end_lineno - node.lineno + 1
    return None


def _get_function_names(filepath: Path) -> set[str]:
    """Return all function/method names defined at module level."""
    source = filepath.read_text()
    tree = ast.parse(source)
    names = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def _get_function_docstring(filepath: Path, func_name: str) -> str | None:
    """Return the docstring of a function, or None if not found."""
    source = filepath.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                return ast.get_docstring(node)
    return None


# ── cyrus_brain.py tests ─────────────────────────────────────────────────────


class TestBrainMainDecomposition:
    """Verify cyrus_brain.py main() has been decomposed into subsystems."""

    brain = CYRUS_ROOT / "cyrus_brain.py"

    def test_main_under_50_lines(self):
        lines = _get_function_lines(self.brain, "main")
        assert lines is not None, "main() not found in cyrus_brain.py"
        assert lines < 50, f"main() is {lines} lines (target: < 50)"

    def test_parse_args_exists(self):
        names = _get_function_names(self.brain)
        assert "_parse_args" in names, "_parse_args() not found"

    def test_init_session_exists(self):
        names = _get_function_names(self.brain)
        assert "_init_session" in names, "_init_session() not found"

    def test_init_workers_exists(self):
        names = _get_function_names(self.brain)
        assert "_init_workers" in names, "_init_workers() not found"

    def test_init_servers_exists(self):
        names = _get_function_names(self.brain)
        assert "_init_servers" in names, "_init_servers() not found"

    def test_all_init_functions_have_docstrings(self):
        for fn in ("_parse_args", "_init_session", "_init_workers", "_init_servers"):
            doc = _get_function_docstring(self.brain, fn)
            assert doc, f"{fn}() missing docstring"

    def test_main_docstring_documents_startup_sequence(self):
        doc = _get_function_docstring(self.brain, "main")
        assert doc, "main() missing docstring"
        assert "startup" in doc.lower() or "sequence" in doc.lower(), (
            "main() docstring should document the startup sequence"
        )


# ── main.py tests (conditional) ──────────────────────────────────────────────


class TestMainDecomposition:
    """Verify main.py main() has been decomposed into subsystems.

    These tests are skipped if main.py is a thin wrapper (Issue 006 complete).
    """

    main = CYRUS_ROOT / "main.py"

    def _is_thin_wrapper(self) -> bool:
        """Check if main.py is already a thin wrapper (< 50 lines total)."""
        return len(self.main.read_text().splitlines()) < 50

    def test_main_under_50_lines(self):
        if self._is_thin_wrapper():
            return  # Issue 006 already handled this
        lines = _get_function_lines(self.main, "main")
        assert lines is not None, "main() not found in main.py"
        assert lines < 50, f"main() is {lines} lines (target: < 50)"

    def test_init_functions_exist(self):
        if self._is_thin_wrapper():
            return
        names = _get_function_names(self.main)
        expected = {"_init_whisper", "_init_tts", "_init_audio",
                    "_init_sessions", "_init_hotkeys", "_routing_loop"}
        missing = expected - names
        assert not missing, f"Missing functions: {missing}"

    def test_all_init_functions_have_docstrings(self):
        if self._is_thin_wrapper():
            return
        for fn in ("_init_whisper", "_init_tts", "_init_audio",
                    "_init_sessions", "_init_hotkeys", "_routing_loop"):
            doc = _get_function_docstring(self.main, fn)
            assert doc, f"{fn}() missing docstring"

    def test_main_docstring_documents_startup_sequence(self):
        if self._is_thin_wrapper():
            return
        doc = _get_function_docstring(self.main, "main")
        assert doc, "main() missing docstring"
        assert "startup" in doc.lower() or "sequence" in doc.lower(), (
            "main() docstring should document the startup sequence"
        )
```

**Verification**:
```bash
cd /home/daniel/Projects/barf/cyrus
python -m pytest tests/test_subsystem_init.py -v
```

All tests should pass.

## Acceptance Criteria Mapping

| Criterion | Verified by |
|-----------|-------------|
| `main()` in cyrus_brain.py reduced to < 50 lines | Step 8 (AST line count), `test_main_under_50_lines` |
| `main()` in main.py reduced to < 50 lines (if kept) | Step 19 (AST line count), `TestMainDecomposition.test_main_under_50_lines` |
| Each subsystem initialization in a separate function | Steps 3–6, 11–17 (extraction), `test_init_functions_exist` |
| Subsystem functions return initialized objects/state | `_parse_args` → `Namespace`, `_init_session` → `SessionManager`, `_init_servers` → tuple, `_init_whisper` → `WhisperModel`, `_init_audio` → tuple |
| All original initialization behavior preserved | Pure extraction — no logic changes, same call order, same globals set |
| Error handling improved: specific exceptions caught and logged | Steps 7, 18 (try/except per subsystem with `logger.exception()`) |
| Startup sequence clear and documented | Steps 7, 18 (docstring with numbered sequence), `test_main_docstring_documents_startup_sequence` |

## Risk Assessment

**Low risk.** Pure extraction refactoring — no logic changes, no new features.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Closure scoping in `_init_hotkeys()` | Low — callbacks capture loop var | Low | Same closures as before, just in a different function |
| `global` declaration in wrong scope | Medium — silent bugs | Low | Each `_init_*` declares exactly the globals it mutates; AST test validates function exists |
| `_init_servers()` lambda capturing stale `session_mgr` | None — same pattern as current code | None | Lambdas capture by reference, same as before |
| Issue 005/006 changes file structure | Low — plan adapts | Medium | Step 1 checks; main.py tests skip if thin wrapper |
| Missing `logging` import | None — Step 2 adds it | None | py_compile verification |

**Known limitations**:
- Full end-to-end verification requires Windows + GPU hardware
- Tests are structural (AST-based), not runtime — mocked integration tests deferred to test suite sprint (Issue 018+)
- If Issue 005 reorganizes classes into `cyrus_common.py`, the `_init_session()` function body may need adjustment (different import path for `SessionManager`)
