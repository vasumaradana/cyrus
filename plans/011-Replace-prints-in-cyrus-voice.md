# Plan 011: Replace print() calls in cyrus_voice.py

## Summary

Replace all 32 `print()` calls in `cyrus_voice.py` with structured `logging` calls. Add `import logging`, `from cyrus2.cyrus_log import setup_logging`, define `log = logging.getLogger("cyrus.voice")` after imports, and call `setup_logging("cyrus")` in `main()`. Convert f-strings to `%s`-style logging. Map each print to the correct log level per docs/16-logging-system.md.

## Dependencies

- **Issue 009** — `cyrus2/cyrus_log.py` must exist with `setup_logging()` function. Plan 009 is complete; module may or may not be built yet. If absent, this issue cannot be verified at runtime but can still be built and syntax-checked.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `import logging` | Not present | Add after `import json` in stdlib imports |
| `from cyrus2.cyrus_log import setup_logging` | Not present | Add after third-party imports (after `from faster_whisper import WhisperModel`) |
| `log = logging.getLogger("cyrus.voice")` | Not present | Add after all imports, before `# ── GPU detection ──` |
| `setup_logging("cyrus")` in `main()` | Not present | Add as first line of `main()` body after arg parsing |
| 32 `print()` calls | All use bare `print()` with `[Voice]`/`[TTS]` prefixes | Convert per mapping table below |
| f-string arguments | All use f-strings | Convert to `%s`-style lazy formatting |
| Exception handlers | Print `e` or bare except | Add `exc_info=True` where appropriate |

## Design Decisions

### D1. Import location

`import logging` goes with stdlib imports (after `import json`, line 25). `from cyrus2.cyrus_log import setup_logging` goes after the last third-party import (`from faster_whisper import WhisperModel`, line 39). The logger definition `log = logging.getLogger("cyrus.voice")` goes immediately after the import block, before the `# ── GPU detection ──` section.

### D2. No module-level prints

Unlike `cyrus_brain.py` (plan 010), `cyrus_voice.py` has no prints that fire at import time — all 32 are inside functions. This simplifies the migration: no `lastResort` handler concerns.

### D3. `end=" "` and `flush=True` patterns

Lines 322, 337, 444 use `flush=True`. Line 444 uses `end=" "` to keep the cursor on the same line for a follow-up print on line 449 (`"(nothing heard)"`) or line 453. Logging doesn't support inline continuations — each log call is a complete line. Convert both to independent log calls. The visual "same-line" behavior is cosmetic; structured logging is cleaner.

### D4. `[Voice]` and `[TTS]` prefix removal

The `[Voice]` prefix was an ad-hoc convention. The logger name `cyrus.voice` now provides this context in the structured format `[cyrus.voice] I ...`. Strip `[Voice] ` from all message strings. Similarly strip `[TTS] ` and `[TTS worker] ` — the logger name replaces them.

### D5. Leading `\n` in print strings

Line 559 starts with `\n`. Drop the `\n` prefix — logging adds its own line termination, and timestamps (in DEBUG mode) provide visual structure.

### D6. `exc_info=True` policy

Per the issue's acceptance criterion: "Exception handlers using broad `except` → `log.error()` or `log.debug()` with `exc_info=True`". Apply `exc_info=True` to all broad `except Exception` handlers that log. For handlers where the exception represents a fallback (not a crash), use `exc_info=True` at warning level so tracebacks appear only when needed.

### D7. `setup_logging()` placement in `main()`

Place after `argparse` completes but before any model loading or logging. This ensures all subsequent log calls use the configured format.

### D8. Conditional print on line 453

```python
print(f"'{text}'" if not during_tts else f"[during TTS] '{text}'")
```

Convert to two conditional `log.debug()` calls for clarity, rather than an inline ternary in the format string:

```python
if during_tts:
    log.debug("[during TTS] %r", text)
else:
    log.debug("%r", text)
```

### D9. Status pass-through on line 392

`print(msg.get("msg", ""))` relays status messages from brain. Convert to `log.info("%s", msg.get("msg", ""))`. Empty-string case logs an empty info line — same as current behavior.

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC1 | All 32 `print()` calls replaced | `grep -c "print(" cyrus_voice.py` → 0 |
| AC2 | `from cyrus2.cyrus_log import setup_logging` added | `grep "from cyrus2.cyrus_log" cyrus_voice.py` → match |
| AC3 | `import logging` added | `grep "^import logging" cyrus_voice.py` → match |
| AC4 | `log = logging.getLogger("cyrus.voice")` defined | `grep 'getLogger("cyrus.voice")' cyrus_voice.py` → match |
| AC5 | `setup_logging("cyrus")` in `main()` | `grep 'setup_logging("cyrus")' cyrus_voice.py` → match |
| AC6 | `[Voice]` → `log.info()` | Lines 383, 386, 430, 470, 472, 491, 506, 509, 528, 531, 535 use `log.info()` |
| AC7 | `[!]` → `log.error()` | No `[!]` patterns in voice file — N/A |
| AC8 | Timeout/fallback → `log.warning()` | Lines 176, 337, 456, 493, 495, 539, 549 use `log.warning()` |
| AC9 | Debug patterns (transcription, TTS dispatch) → `log.debug()` | Lines 193, 198, 255, 257, 274, 444, 449, 453 use `log.debug()` |
| AC10 | Exception handlers → `exc_info=True` | Lines 259, 397, 493, 539, 549 include `exc_info=True` |
| AC11 | f-strings → `%s` style | All log calls use `log.level("msg: %s", var)` |
| AC12 | No new `print()` introduced | Same grep verification as AC1 |
| AC13 | Functionality unchanged | File structure, function signatures, logic flow all preserved |

## Complete Print-to-Log Mapping (all 32 calls)

### `speak()` (1 call)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 176 | `print("[Voice] TTS timed out")` | `log.warning("TTS timed out")` | WARNING |

### `_speak_kokoro()` (2 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 193 | `print(f"[TTS] generating {len(text)} chars...")` | `log.debug("Generating %s chars...", len(text))` | DEBUG |
| 198 | `print(f"[TTS] {len(samples)} samples at {sr}Hz — playing")` | `log.debug("%s samples at %sHz — playing", len(samples), sr)` | DEBUG |

### `tts_worker()` (3 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 255 | `print(f"[TTS worker] speak: {text[:50]!r}")` | `log.debug("TTS speak: %r", text[:50])` | DEBUG |
| 257 | `print("[TTS worker] done")` | `log.debug("TTS done")` | DEBUG |
| 259 | `print(f"[TTS worker error] {e}")` | `log.error("TTS worker error: %s", e, exc_info=True)` | ERROR |

### `transcribe()` (1 call)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 274 | `print(f"(hallucination filtered: '{text[:60]}')")` | `log.debug("Hallucination filtered: %s", text[:60])` | DEBUG |

### `vad_loop()` (2 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 322 | `print("Listening...", flush=True)` | `log.info("Listening...")` | INFO |
| 337 | `print(" [max duration]", flush=True)` | `log.warning("Max recording duration reached")` | WARNING |

### `brain_reader()` (4 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 383 | `print("[Voice] Resumed")` | `log.info("Resumed")` | INFO |
| 386 | `print("[Voice] Paused")` | `log.info("Paused")` | INFO |
| 392 | `print(msg.get("msg", ""))` | `log.info("%s", msg.get("msg", ""))` | INFO |
| 397 | `print(f"[Voice] Brain reader error: {e}")` | `log.error("Brain reader error: %s", e, exc_info=True)` | ERROR |

### `voice_loop()` (5 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 430 | `print("[Voice] Ready — streaming utterances to brain.")` | `log.info("Ready — streaming utterances to brain.")` | INFO |
| 444 | `print("Transcribing...", end=" ", flush=True)` | `log.debug("Transcribing...")` | DEBUG |
| 449 | `print("(nothing heard)")` | `log.debug("Nothing heard")` | DEBUG |
| 453 | `print(f"'{text}'" if not during_tts else f"[during TTS] '{text}'")` | See D8: conditional `log.debug("[during TTS] %r", text)` or `log.debug("%r", text)` | DEBUG |
| 456 | `print("[Voice] Brain disconnected — reconnecting...")` | `log.warning("Brain disconnected — reconnecting...")` | WARNING |

### `main()` (13 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 470 | `print(f"[Voice] GPU: {_GPU_NAME}")` | `log.info("GPU: %s", _GPU_NAME)` | INFO |
| 472 | `print("[Voice] No CUDA GPU — Whisper on CPU")` | `log.info("No CUDA GPU — Whisper on CPU")` | INFO |
| 473 | `print(f"Loading Whisper {WHISPER_MODEL} on {WHISPER_DEVICE}...")` | `log.info("Loading Whisper %s on %s...", WHISPER_MODEL, WHISPER_DEVICE)` | INFO |
| 491 | `print(f"[Voice] Kokoro TTS loaded ({_tts_dev}) — voice: {TTS_VOICE}")` | `log.info("Kokoro TTS loaded (%s) — voice: %s", _tts_dev, TTS_VOICE)` | INFO |
| 493 | `print(f"[Voice] Kokoro load failed ({e}) — using Edge TTS")` | `log.warning("Kokoro load failed (%s) — using Edge TTS", e, exc_info=True)` | WARNING |
| 495 | `print("[Voice] Kokoro model not found — using Edge TTS")` | `log.warning("Kokoro model not found — using Edge TTS")` | WARNING |
| 506 | `print("[Voice] Resumed (F9)")` | `log.info("Resumed (F9)")` | INFO |
| 509 | `print("[Voice] Paused (F9)")` | `log.info("Paused (F9)")` | INFO |
| 528 | `print("[Voice] F9 pause  \|  F7 stop+clear  \|  F8 clipboard  \|  Ctrl+C exit")` | `log.info("F9 pause  \|  F7 stop+clear  \|  F8 clipboard  \|  Ctrl+C exit")` | INFO |
| 531 | `print(f"[Voice] Connecting to brain at {args.host}:{args.port}...")` | `log.info("Connecting to brain at %s:%s...", args.host, args.port)` | INFO |
| 535 | `print("[Voice] Connected to brain.")` | `log.info("Connected to brain.")` | INFO |
| 539 | `print(f"[Voice] Disconnected: {e}")` | `log.warning("Disconnected: %s", e, exc_info=True)` | WARNING |
| 549 | `print(f"[Voice] Cannot connect to brain ({e}) — retrying in 3s...")` | `log.warning("Cannot connect to brain (%s) — retrying in 3s...", e, exc_info=True)` | WARNING |

### `__main__` block (1 call)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 559 | `print("\nCyrus Voice signing off.")` | `log.info("Cyrus Voice signing off.")` | INFO |

**Total: 32 calls** (1 + 2 + 3 + 1 + 2 + 4 + 5 + 13 + 1 = 32 ✓)

## Silent Exception Handlers

Per docs/16-logging-system.md: `except Exception: pass` (silent) → `except Exception: log.debug("...", exc_info=True)`. The following silent handlers should get debug logging where they could indicate real problems. Cleanup/shutdown handlers are left as-is.

| Line | Location | Current | Action |
|---|---|---|---|
| 129–130 | `play_chime()` | `except Exception: pass` | Add `log.debug("Chime playback failed", exc_info=True)` |
| 142–143 | `play_listen_chime()` | `except Exception: pass` | Add `log.debug("Listen chime playback failed", exc_info=True)` |
| 154–155 | `_send()` | `except Exception: pass` | Add `log.debug("Send to brain failed", exc_info=True)` |
| 163–165 | `drain_tts_queue()` | `except Exception: break` | Leave — expected (queue empty) |
| 244–246 | `_speak_edge()` finally | `except Exception: pass` | Leave — best-effort cleanup |
| 423–425 | `voice_loop()` queue drain | `except Exception: pass` | Leave — expected (queue empty) |
| 521–523 | `_read_clipboard()` | `except Exception: pass` | Add `log.debug("Clipboard read failed", exc_info=True)` |
| 546–547 | `main()` writer.close() | `except Exception: pass` | Leave — cleanup |
| 566–567 | `__main__` pygame | `except Exception: pass` | Leave — shutdown cleanup |
| 569–570 | `__main__` sounddevice | `except Exception: pass` | Leave — shutdown cleanup |
| 575–576 | `__main__` keyboard | `except Exception: pass` | Leave — shutdown cleanup |

## Implementation Steps

### Step 1: Add imports and logger definition

**File**: `cyrus_voice.py`

1. Add `import logging` after `import json` (line 25):

```python
import json
import logging
import asyncio
```

2. Add `from cyrus2.cyrus_log import setup_logging` after the last third-party import line (`from faster_whisper import WhisperModel`, line 39):

```python
from faster_whisper import WhisperModel
from cyrus2.cyrus_log import setup_logging
```

3. Add logger definition after the import block, before `# ── GPU detection ──` (line 41):

```python
from cyrus2.cyrus_log import setup_logging

log = logging.getLogger("cyrus.voice")

# ── GPU detection ──────────────────────────────────────────────────────────────
```

### Step 2: Add `setup_logging()` call in `main()`

In `main()`, add `setup_logging("cyrus")` after argparse but before any model loading:

```python
    args = parser.parse_args()

    setup_logging("cyrus")

    if _CUDA:
```

### Step 3: Convert `speak()` print (1 call)

Line 176: timeout warning.

### Step 4: Convert `_speak_kokoro()` prints (2 calls)

Lines 193, 198: TTS debug output.

### Step 5: Convert `tts_worker()` prints (3 calls)

Lines 255, 257, 259. Note `exc_info=True` on error handler (line 259).

### Step 6: Convert `transcribe()` print (1 call)

Line 274: hallucination filter debug.

### Step 7: Convert `vad_loop()` prints (2 calls)

Lines 322, 337. Drop `flush=True` (logging handles flushing).

### Step 8: Convert `brain_reader()` prints (4 calls)

Lines 383, 386, 392, 397. Note `exc_info=True` on error handler (line 397).

### Step 9: Convert `voice_loop()` prints (5 calls)

Lines 430, 444, 449, 453, 456. Note `end=" "` removal on line 444 (see D3). Conditional print on line 453 becomes two `log.debug()` calls (see D8).

### Step 10: Convert `main()` prints (13 calls)

Lines 470, 472, 473, 491, 493, 495, 506, 509, 528, 531, 535, 539, 549. Note `exc_info=True` on Kokoro load failure (line 493), disconnection (line 539), and connection failure (line 549).

### Step 11: Convert `__main__` print (1 call)

Line 559: drop `\n` prefix (see D5).

### Step 12: Add debug logging to silent exception handlers (4 handlers)

Lines 129–130, 142–143, 154–155, 521–523 per the silent exception handler table above.

### Step 13: Verify — zero print() calls remaining

```bash
cd /home/daniel/Projects/barf/cyrus
grep -cn "print(" cyrus_voice.py
```

Expected: `0` matches.

### Step 14: Verify — all required patterns present

```bash
cd /home/daniel/Projects/barf/cyrus
grep -n "from cyrus2.cyrus_log import setup_logging" cyrus_voice.py
grep -n "^import logging" cyrus_voice.py
grep -n 'getLogger("cyrus.voice")' cyrus_voice.py
grep -n 'setup_logging("cyrus")' cyrus_voice.py
```

All four must match exactly one line each.

### Step 15: Verify — syntax check

```bash
cd /home/daniel/Projects/barf/cyrus
python3 -m py_compile cyrus_voice.py 2>&1 || true
```

Expected: no `SyntaxError`. Import errors for hardware-specific modules (sounddevice, torch, etc.) are expected on non-target machines.

## Risk Assessment

**Low risk.** Mechanical conversion of print→log. No logic changes, no new behavior, no API changes.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| `cyrus_log.py` not built yet (Issue 009) | `ImportError` at runtime | Medium | Issue is blocked by 009; builder should verify 009 is complete before runtime test |
| Typo in `%s` format string | Runtime `TypeError` on first log call | Low | Mapping table above is exhaustive; grep verification catches mismatches |
| `exc_info=True` adds unexpected traceback verbosity | Longer log output on errors | Very low | Only on ERROR-level exceptions and one WARNING; this is the desired behavior per spec |
| `end=" "` / `flush=True` removal changes terminal appearance | Visual difference during debugging | Very low | Structured logging is the replacement; cosmetic same-line behavior was a debugging convenience |
