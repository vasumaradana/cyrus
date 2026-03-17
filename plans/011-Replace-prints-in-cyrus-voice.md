# Implementation Plan: Replace print() calls in cyrus_voice.py

**Issue**: [011-Replace-prints-in-cyrus-voice](/home/daniel/Projects/barf/cyrus/issues/011-Replace-prints-in-cyrus-voice.md)
**Created**: 2026-03-16
**Updated**: 2026-03-17
**PROMPT**: `.claude/prompts/plan.md`

## Gap Analysis

**Already exists**:
- Complete logging design spec at `docs/16-logging-system.md` with exact conversion rules, format strings, and per-file logger names
- `cyrus2/cyrus_voice.py` with 32 `print()` calls to convert (624 lines, all line numbers verified 2026-03-16)
- Test patterns established in `cyrus2/tests/test_001_pyproject_config.py` (unittest, class-based, "AC:" docstrings, setUpClass, assertion messages)
- Plan for Issue 009 (`cyrus_log.py`) fully specified — module will provide `setup_logging(name)`
- Issue 010 plan (`plans/010-Replace-prints-in-cyrus-brain.md`) as a reference for identical conversion pattern

**Needs building**:
- Replace all 32 `print()` calls with `log.*()` equivalents in `cyrus2/cyrus_voice.py`
- Add imports (`import logging`, `from cyrus2.cyrus_log import setup_logging`)
- Add logger definition `log = logging.getLogger("cyrus.voice")`
- Call `setup_logging("cyrus")` in `main()` before any logging
- Add `log.debug(..., exc_info=True)` to 13 silent exception handlers (12 listed + keyboard.unhook_all at line 622)
- Convert all f-strings to `%s`-style logging
- Create `cyrus2/tests/test_011_cyrus_voice_logging.py` — acceptance tests

**Blocker**: Issue 009 (Create cyrus_log module) must be completed first — `cyrus2/cyrus_log.py` does not yet exist. Issue 009 is in `PLANNED` state as of 2026-03-16. This plan assumes it will be built per the spec in `docs/16-logging-system.md`.

## Approach

Mechanical print-to-log conversion following the exact rules from `docs/16-logging-system.md`. Each `print()` is categorized by its prefix/context into INFO, WARNING, ERROR, or DEBUG. Silent exception handlers get `log.debug(..., exc_info=True)`. All f-strings converted to `%s`-style lazy formatting.

**Why this approach**: The spec fully defines the conversion rules. No architectural decisions needed — just apply the mapping table consistently. The file is 624 lines with a single module-level logger, making the conversion straightforward and low-risk.

**Special cases**:
- `print("Transcribing...", end=" ", flush=True)` — logging doesn't support `end=" "`. Convert to standalone `log.debug("Transcribing...")`. The "continuation" pattern (Transcribing... result) becomes two separate log lines.
- `print(" [max duration]", flush=True)` — leading space was for inline continuation. Convert to `log.debug("Max duration reached")`.
- `print(msg.get("msg", ""))` — status relay from brain. Use `log.info("%s", msg.get("msg", ""))`.
- `print("\nCyrus Voice signing off.")` — drop `\n` prefix. Use `log.info("Cyrus Voice signing off.")`.

## Rules to Follow

- `.claude/rules/` — Empty (no project rules defined)
- **Ruff compliance**: Code must pass `ruff check` and `ruff format` with pyproject.toml settings (E, F, W, I, UP, B; line-length 88; py310)
- **Test pattern**: Follow test_001 conventions — unittest, class-based, "AC:" docstrings, assertion messages, setUpClass for shared setup
- **Logging convention**: `%s`-style formatting (never f-strings in log calls), `exc_info=True` for exception handlers
- **`.claude/skills/python-patterns/SKILL.md`** — Explicit prohibition on f-strings in logging; use `%s` lazy formatting
- **`.claude/skills/python-linting/SKILL.md`** — Ruff check/format commands reference

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Print-to-log conversion | Direct implementation | Mechanical conversion per conversion table |
| Logging style validation | `.claude/skills/python-patterns/` | Enforces `%s`-style logging, no f-strings |
| Lint check | `.claude/skills/python-linting/` | `ruff check cyrus2/cyrus_voice.py` |
| Format check | `.claude/skills/python-linting/` | `ruff format --check cyrus2/cyrus_voice.py` |
| Write tests | `.claude/skills/python-testing/` | unittest class-based pattern from test_001 |
| Code quality review | `.claude/skills/python-expert/` | Type hints, error handling, PEP 8 compliance |
| Run tests | `python -m unittest cyrus2/tests/test_011_cyrus_voice_logging.py -v` | Verify acceptance |
| Grep verification | `grep -n "print(" cyrus2/cyrus_voice.py` | Confirm zero remaining print() calls |

## Prioritized Tasks

- [x] Add imports at top of `cyrus2/cyrus_voice.py`:
  ```python
  import logging
  from cyrus2.cyrus_log import setup_logging
  ```
  (`import logging` goes with stdlib imports after `import json`; `from cyrus2.cyrus_log import setup_logging` after third-party imports, before module code)
- [x] Add logger definition after all imports:
  ```python
  log = logging.getLogger("cyrus.voice")
  ```
- [x] Add `setup_logging("cyrus")` as first statement in `main()` (line 503, before `parser = argparse...`)
- [x] Replace all 32 `print()` calls per the conversion table below
- [x] Add `log.debug(..., exc_info=True)` to 13 silent exception handlers
- [x] Run `ruff check` and `ruff format` — fix any issues
- [x] Verify zero `print(` calls remain: `grep -n "print(" cyrus2/cyrus_voice.py`
- [x] Create acceptance test file `cyrus2/tests/test_011_cyrus_voice_logging.py`
- [x] Run all tests and verify they pass

## Print-to-Log Conversion Table (all 32 calls)

### INFO — 14 calls (lifecycle events, state changes)

| Line | Current | Replacement |
|------|---------|-------------|
| 423 | `print("[Voice] Resumed")` | `log.info("Resumed")` |
| 426 | `print("[Voice] Paused")` | `log.info("Paused")` |
| 432 | `print(msg.get("msg", ""))` | `log.info("%s", msg.get("msg", ""))` |
| 470 | `print("[Voice] Ready — streaming utterances to brain.")` | `log.info("Ready — streaming utterances to brain.")` |
| 511 | `print(f"[Voice] GPU: {_GPU_NAME}")` | `log.info("GPU: %s", _GPU_NAME)` |
| 513 | `print("[Voice] No CUDA GPU — Whisper on CPU")` | `log.info("No CUDA GPU — Whisper on CPU")` |
| 514 | `print(f"Loading Whisper {WHISPER_MODEL} on {WHISPER_DEVICE}...")` | `log.info("Loading Whisper %s on %s...", WHISPER_MODEL, WHISPER_DEVICE)` |
| 536 | `print(f"[Voice] Kokoro TTS loaded ({_tts_dev}) — voice: {TTS_VOICE}")` | `log.info("Kokoro TTS loaded (%s) — voice: %s", _tts_dev, TTS_VOICE)` |
| 551 | `print("[Voice] Resumed (F9)")` | `log.info("Resumed (F9)")` |
| 554 | `print("[Voice] Paused (F9)")` | `log.info("Paused (F9)")` |
| 574 | `print("[Voice] F9 pause \| F7 stop+clear \| F8 clipboard \| Ctrl+C exit")` | `log.info("F9 pause \| F7 stop+clear \| F8 clipboard \| Ctrl+C exit")` |
| 577 | `print(f"[Voice] Connecting to brain at {args.host}:{args.port}...")` | `log.info("Connecting to brain at %s:%s...", args.host, args.port)` |
| 581 | `print("[Voice] Connected to brain.")` | `log.info("Connected to brain.")` |
| 605 | `print("\nCyrus Voice signing off.")` | `log.info("Cyrus Voice signing off.")` |

### WARNING — 6 calls (timeouts, fallbacks, reconnection)

| Line | Current | Replacement |
|------|---------|-------------|
| 181 | `print("[Voice] TTS timed out")` | `log.warning("TTS timed out")` |
| 496 | `print("[Voice] Brain disconnected — reconnecting...")` | `log.warning("Brain disconnected — reconnecting...")` |
| 538 | `print(f"[Voice] Kokoro load failed ({e}) — using Edge TTS")` | `log.warning("Kokoro load failed (%s) — using Edge TTS", e)` |
| 540 | `print("[Voice] Kokoro model not found — using Edge TTS")` | `log.warning("Kokoro model not found — using Edge TTS")` |
| 585 | `print(f"[Voice] Disconnected: {e}")` | `log.warning("Disconnected: %s", e)` |
| 595 | `print(f"[Voice] Cannot connect to brain ({e}) — retrying in 3s...")` | `log.warning("Cannot connect to brain (%s) — retrying in 3s...", e)` |

### ERROR — 2 calls (exception handlers with explicit messages)

| Line | Current | Replacement |
|------|---------|-------------|
| 283 | `print(f"[TTS worker error] {e}")` | `log.error("TTS worker error: %s", e)` |
| 437 | `print(f"[Voice] Brain reader error: {e}")` | `log.error("Brain reader error: %s", e)` |

### DEBUG — 10 calls (transcription flow, TTS dispatch)

| Line | Current | Replacement |
|------|---------|-------------|
| 198 | `print(f"[TTS] generating {len(text)} chars...")` | `log.debug("TTS generating %s chars...", len(text))` |
| 203 | `print(f"[TTS] {len(samples)} samples at {sr}Hz — playing")` | `log.debug("TTS %s samples at %sHz — playing", len(samples), sr)` |
| 279 | `print(f"[TTS worker] speak: {text[:50]!r}")` | `log.debug("TTS worker speak: %r", text[:50])` |
| 281 | `print("[TTS worker] done")` | `log.debug("TTS worker done")` |
| 302 | `print(f"(hallucination filtered: '{text[:60]}')")` | `log.debug("Hallucination filtered: %s", text[:60])` |
| 357 | `print("Listening...", flush=True)` | `log.debug("Listening...")` |
| 374 | `print(" [max duration]", flush=True)` | `log.debug("Max duration reached")` |
| 484 | `print("Transcribing...", end=" ", flush=True)` | `log.debug("Transcribing...")` |
| 489 | `print("(nothing heard)")` | `log.debug("Nothing heard")` |
| 493 | `print(f"'{text}'" if not during_tts else f"[during TTS] '{text}'")`| `log.debug("Transcribed%s: %s", " (during TTS)" if during_tts else "", text)` |

**Total: 14 INFO + 6 WARNING + 2 ERROR + 10 DEBUG = 32 print() calls**

## Silent Exception Handlers — Add exc_info Logging (13 blocks)

These `except` blocks currently swallow errors silently. Per acceptance criteria, add `log.debug()` with `exc_info=True`:

| Line | Location | Current action | New logging |
|------|----------|----------------|-------------|
| 130 | `play_chime()` | `pass` | `log.debug("Chime playback failed", exc_info=True)` |
| 145 | `play_listen_chime()` | `pass` | `log.debug("Listen chime playback failed", exc_info=True)` |
| 158 | `_send()` | `pass` | `log.debug("Failed to send to brain", exc_info=True)` |
| 169 | `drain_tts_queue()` | `break` | `log.debug("Error draining TTS queue", exc_info=True)` + `break` |
| 269 | `_speak_edge()` cleanup | `pass` | `log.debug("Failed to delete temp file", exc_info=True)` |
| 342 | `vad_loop()` | `continue` | `log.debug("VAD frame error", exc_info=True)` + `continue` |
| 434 | `brain_reader()` JSONDecodeError | `pass` | `log.debug("Invalid JSON from brain", exc_info=True)` |
| 464 | `voice_loop()` queue drain | `pass` | `log.debug("Queue drain error", exc_info=True)` |
| 568 | `_read_clipboard()` | `pass` | `log.debug("Clipboard read failed", exc_info=True)` |
| 592 | `main()` writer close | `pass` | `log.debug("Writer close error", exc_info=True)` |
| 612 | `main()` pygame cleanup | `pass` | `log.debug("Pygame cleanup error", exc_info=True)` |
| 616 | `main()` sd.stop() | `pass` | `log.debug("Sound device cleanup error", exc_info=True)` |
| 622 | `main()` keyboard.unhook_all | `pass` | `log.debug("Keyboard cleanup error", exc_info=True)` |

**Note**: `except KeyboardInterrupt: pass` (line 602), `except asyncio.TimeoutError: continue` (line 475), and `except asyncio.QueueEmpty: break` (line 481) are intentional control flow — leave unchanged.

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| All 32 print() replaced | `test_no_print_calls_remain` — grep source for `print(`, count == 0 | static |
| `from cyrus2.cyrus_log import setup_logging` added | `test_setup_logging_import` — check import in source | static |
| `import logging` added | `test_logging_import` — check import in source | static |
| `log = logging.getLogger("cyrus.voice")` defined | `test_logger_name` — verify module-level `log` exists with correct name | unit |
| `setup_logging("cyrus")` called in main() | `test_setup_logging_in_main` — check source of main() contains call | static |
| `[Voice]` prefix → `log.info()` | `test_info_calls_present` — verify log.info calls exist in source | static |
| `[!]` prefix → `log.error()` | `test_error_calls_present` — verify log.error calls exist | static |
| Timeout/fallback → `log.warning()` | `test_warning_calls_present` — verify log.warning calls exist | static |
| Debug patterns → `log.debug()` | `test_debug_calls_present` — verify log.debug calls exist | static |
| Exception handlers with exc_info=True | `test_exc_info_in_exception_handlers` — count `exc_info=True` ≥ 13 | static |
| F-strings → %s style | `test_no_fstrings_in_log_calls` — grep log calls for f-string patterns | static |
| No new print() introduced | `test_no_print_calls_remain` — (same as first test) | static |

**No cheating** — cannot claim done without all required tests passing.

## Validation (Backpressure)

- **Tests**: `python -m unittest cyrus2/tests/test_011_cyrus_voice_logging.py -v` — all tests pass
- **Lint**: `ruff check cyrus2/cyrus_voice.py` — no violations
- **Format**: `ruff format --check cyrus2/cyrus_voice.py` — already formatted
- **Grep**: `grep -n "print(" cyrus2/cyrus_voice.py` — returns 0 matches
- **Existing tests**: `python -m unittest discover cyrus2/tests/ -v` — no regressions

## Files to Create/Modify

- `cyrus2/cyrus_voice.py` — **modify** (replace 32 prints, add imports, add logger, add exc_info logging to 13 handlers)
- `cyrus2/tests/test_011_cyrus_voice_logging.py` — **create new** (~120-150 lines, acceptance tests)

## Key Decisions

1. **Static analysis tests over runtime tests**: Since cyrus_voice.py depends on hardware (GPU, sound devices, microphone), runtime tests are impractical. Tests verify the source code statically — grep for print(), count log calls, verify import structure. This matches the issue's own verification approach (`grep -n "print(" cyrus2/cyrus_voice.py`).
2. **Line 432 (`msg.get("msg", "")`) is INFO**: This relays status messages from brain — lifecycle/state info, not debug.
3. **Line 585 (`Disconnected: {e}`) is WARNING not ERROR**: Disconnections trigger automatic reconnect — they're recoverable, not fatal.
4. **`end=" "` and `flush=True` dropped**: Logging doesn't support inline continuation. Each log call is a standalone line. The "Transcribing... result" pattern becomes two separate log.debug() calls.
5. **`\n` prefix in "signing off" dropped**: Logging handles line separation; the newline was only for print() visual spacing.
6. **unittest over pytest**: Matching established test patterns (test_001). Project pyproject.toml has pytest config but existing tests use unittest classes.
7. **13 silent handlers (not 12)**: The plan in the issue body says "12 silent except blocks" but keyboard.unhook_all at line 622 is a 13th that should also get exc_info logging.
