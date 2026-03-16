# Plan 006: Deprecate main.py monolith

## Goal

Reduce `main.py` from a 1,755-line monolith to a ~25-line thin wrapper that prints a deprecation warning and delegates to `cyrus_brain.main()`. The split architecture (brain + voice as separate processes) becomes the only recommended mode.

## Prerequisites

- **Issue 005** (Extract shared code into cyrus_common.py) must be COMPLETE.
  - After 005: `cyrus_common.py` exists with shared code, `main.py` is ~900–1,000 lines, `cyrus_brain.py` is ~700–850 lines.
- This plan assumes 005 is done. All steps reference the post-005 state.

## Key Findings from Gap Analysis

### Path discrepancy
The issue file references `cyrus2/` paths but the actual source files live at the project root (`/home/daniel/Projects/barf/cyrus/`). The `cyrus2/` directory is empty. This plan uses root-level paths matching the actual codebase.

### What main.py contains after Issue 005

After 005 extracts shared code, main.py retains only monolith-specific code:
- Audio/voice imports (~20 lines): numpy, sounddevice, torch, silero_vad, faster_whisper, pygame, keyboard
- GPU detection and Whisper/VAD config constants (~40 lines)
- `vad_loop()` — voice activity detection loop (~100 lines)
- `transcribe()` — Whisper transcription (~20 lines)
- TTS pipeline: `speak()`, `_speak_save()`, `_speak_kokoro()`, `_speak_edge()` (~90 lines)
- `_execute_cyrus_command()` — command dispatch (~80 lines)
- `startup_sequence()` — monolith greeting (~15 lines)
- `main()` — monolith entry point with audio init, hotkeys, event loop (~280 lines)
- Shutdown handling (~25 lines)
- Shared state globals (~20 lines)

**All of this code already exists in `cyrus_voice.py` and `cyrus_brain.py`** (the split services). Nothing unique to main.py is being lost — the monolith simply bundled both services into one process.

### What cyrus_brain.py's main() does

`cyrus_brain.py:main()` (line 1696, `async def main() -> None`) starts:
1. Session manager + window tracking
2. VS Code submit worker thread
3. Speak worker (forwards to voice service)
4. Routing loop (processes utterances)
5. TCP server on port 8766 (voice connections)
6. TCP server on port 8767 (Claude Code hook connections)
7. WebSocket server on port 8769 (mobile clients)

Its own `__main__` block uses `asyncio.run(main())` with KeyboardInterrupt handling.

When `main.py` delegates to `brain_main()`, users get the brain service only. The deprecation message tells them to run `cyrus_voice.py` separately for audio. **This behavioral change is intentional** — the monolith mode is replaced by split mode.

### No imports of main.py from other files

Confirmed via grep: no file imports from `main.py`. It's a standalone entry point only.

### README current state

The README (231 lines) already documents split mode as the primary architecture. The "Project Structure" section does NOT list `main.py` at all — it only shows `cyrus_voice.py`, `cyrus_brain.py`, `cyrus_hook.py`, `cyrus-companion/`, and support files. Step 4a must ADD an entry, not modify one.

## Design Decisions

### D1. Complete replacement, not incremental gutting

Rather than surgically removing functions, replace the entire file content with the thin wrapper. This is cleaner and eliminates any risk of leaving dead code behind. The old content is preserved in git history.

### D2. Deprecation via print(), not logging

The project uses `print()` throughout — logging migration is Issue 009/010. Using `logging.getLogger().warning()` here would be inconsistent with every other file. Use `print()` with a prominent `⚠️` emoji banner, matching the existing output style. When Issue 010 replaces prints with logging, this warning migrates naturally.

### D3. Return value passthrough

`brain_main()` is `async def main() -> None` that runs `serve_forever()` (never returns normally). The wrapper calls it via `asyncio.run()` and propagates `KeyboardInterrupt` for clean shutdown, matching cyrus_brain.py's own `if __name__` block.

### D4. README update scope

The README already documents split mode as the primary architecture. Updates needed:
- Add `main.py` entry to Project Structure (currently absent) and mark as deprecated
- Add a "Deprecated: Monolith Mode" section after Project Structure
- Quick Start already only references split mode — no changes needed there

### D5. cyrus_brain.py comment update

Add a one-line note to cyrus_brain.py's module docstring marking it as the primary entry point.

## Implementation Steps

### Step 1: Verify Issue 005 prerequisite

Confirm `cyrus_common.py` exists and cyrus_brain.py imports from it:

```bash
test -f /home/daniel/Projects/barf/cyrus/cyrus_common.py && echo "OK: cyrus_common.py exists"
grep -n "from cyrus_common import" /home/daniel/Projects/barf/cyrus/cyrus_brain.py && echo "OK: brain imports from common"
```

If either check fails, Issue 005 is not yet complete — stop and report the blocker.

**Verification**: Both commands print "OK".

### Step 2: Replace main.py with thin wrapper

**File**: `/home/daniel/Projects/barf/cyrus/main.py`

Replace the entire file with:
```python
"""
Cyrus - All-in-one monolith mode (DEPRECATED)

This was the original single-process mode that combined voice, brain, and TTS.
It is maintained only as a thin wrapper for backward compatibility.

Recommended: Use split mode instead:
    python cyrus_brain.py &
    python cyrus_voice.py
"""

import asyncio
import sys

from cyrus_brain import main as brain_main


def main() -> None:
    print(
        "\n"
        "⚠️  DEPRECATION WARNING: main.py monolith mode is deprecated.\n"
        "Use split mode instead:\n"
        "  python cyrus_brain.py &\n"
        "  python cyrus_voice.py\n"
        "Split mode allows independent restart and clearer separation of concerns.\n"
    )
    asyncio.run(brain_main())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Cyrus] Shutting down.")
        sys.exit(0)
```

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/main.py
wc -l /home/daniel/Projects/barf/cyrus/main.py  # expected: ~25 lines
```

### Step 3: Update cyrus_brain.py module docstring

**File**: `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`

Change the first line of the docstring from:
```python
"""
cyrus_brain.py — Service 2: Logic / VS Code Watcher
```

To:
```python
"""
cyrus_brain.py — Service 2: Logic / VS Code Watcher (PRIMARY ENTRY POINT)

This is the recommended entry point for Cyrus. main.py is deprecated; use this directly.
```

Leave the rest of the docstring intact.

**Verification**:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
head -5 /home/daniel/Projects/barf/cyrus/cyrus_brain.py | grep -i "primary"
```

### Step 4: Update README.md

**File**: `/home/daniel/Projects/barf/cyrus/README.md`

**4a.** Add `main.py` to the "Project Structure" section and mark as deprecated.

The current Project Structure block is:
```
cyrus_voice.py          — Voice service (mic/VAD/Whisper/TTS)
cyrus_brain.py          — Brain service (routing/UIA/hooks/watchers)
cyrus_hook.py           — Claude Code hook script (all 4 events)
cyrus-companion/        — VS Code extension (submit text to Claude Code)
requirements-voice.txt  — Voice service dependencies
requirements-brain.txt  — Brain service dependencies
install-voice.ps1/.sh   — Voice installer
install-brain.ps1/.sh   — Brain installer
build-release.ps1       — Packages both zips for distribution
```

Add after the `cyrus_hook.py` line:
```
main.py                 — DEPRECATED monolith wrapper (delegates to cyrus_brain.py)
```

**4b.** Add a "Deprecated: Monolith Mode" section after "Project Structure":

```markdown
## Deprecated: Monolith Mode

> **⚠️ `main.py` is deprecated and will be removed in Cyrus 3.0.**

The original `main.py` combined voice I/O and brain logic in a single process.
It now delegates to `cyrus_brain.py` and logs a deprecation warning on startup.

**Use split mode instead** (documented in Quick Start above). If you previously
ran `python main.py`, switch to:

```bash
python cyrus_brain.py &
python cyrus_voice.py
```

No configuration changes needed — split mode uses the same `.env` and hooks.
```

**Verification**:
```bash
grep -c "deprecated" /home/daniel/Projects/barf/cyrus/README.md  # should be >= 1
grep -c "Monolith Mode" /home/daniel/Projects/barf/cyrus/README.md  # should be 1
```

### Step 5: Verify no critical code was lost

After replacing main.py, verify that every function from the old monolith exists elsewhere:

```bash
cd /home/daniel/Projects/barf/cyrus

# Voice functions exist in cyrus_voice.py:
grep -n "^def vad_loop\|^def transcribe\|^async def speak\|^async def _speak" cyrus_voice.py

# Brain functions exist in cyrus_brain.py or cyrus_common.py:
grep -rn "^def _execute_cyrus_command\|^class SessionManager\|^class ChatWatcher\|^class PermissionWatcher" \
  cyrus_brain.py cyrus_common.py
```

Two main.py-only functions are deliberately dropped:
- `_remote_route()` — experimental monolith-only feature for remote brain WebSocket. The split architecture handles remote voice natively (`python cyrus_voice.py --host <brain-ip>`).
- `startup_sequence()` — monolith-specific greeting. Brain + voice each print their own startup messages.

### Step 6: Lint and format

```bash
cd /home/daniel/Projects/barf/cyrus
ruff check main.py cyrus_brain.py
ruff format main.py cyrus_brain.py
```

Fix any violations.

### Step 7: Write tests

Create `/home/daniel/Projects/barf/cyrus/tests/test_deprecation.py` (create `tests/` directory if it does not exist):

```python
"""Tests for Issue 006: main.py deprecation warning."""

import ast
from pathlib import Path

CYRUS_ROOT = Path(__file__).resolve().parent.parent


def test_main_is_thin_wrapper():
    """main.py must be <= 30 lines (thin wrapper, not a monolith)."""
    lines = (CYRUS_ROOT / "main.py").read_text().splitlines()
    assert len(lines) <= 30, (
        f"main.py has {len(lines)} lines — expected <= 30 for a thin wrapper"
    )


def test_main_docstring_says_deprecated():
    """main.py module docstring must contain 'DEPRECATED'."""
    source = (CYRUS_ROOT / "main.py").read_text()
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree) or ""
    assert "DEPRECATED" in docstring.upper(), (
        f"main.py module docstring must mention DEPRECATED, got: {docstring[:200]}"
    )


def test_main_imports_brain_main():
    """main.py must import main from cyrus_brain."""
    source = (CYRUS_ROOT / "main.py").read_text()
    assert "from cyrus_brain import main" in source, (
        "main.py must contain 'from cyrus_brain import main'"
    )


def test_main_prints_deprecation_warning():
    """main.py main() must print a deprecation warning string."""
    source = (CYRUS_ROOT / "main.py").read_text()
    assert "DEPRECATION" in source, (
        "main.py must contain a 'DEPRECATION' warning string"
    )
    assert "cyrus_brain" in source and "cyrus_voice" in source, (
        "Deprecation warning must reference both cyrus_brain and cyrus_voice"
    )


def test_readme_documents_deprecation():
    """README.md must document the main.py deprecation."""
    readme = (CYRUS_ROOT / "README.md").read_text()
    assert "deprecated" in readme.lower(), "README.md must mention deprecation"
    assert "Monolith Mode" in readme, "README.md must have a 'Monolith Mode' section"


def test_brain_docstring_marks_primary():
    """cyrus_brain.py docstring must indicate it's the primary entry point."""
    source = (CYRUS_ROOT / "cyrus_brain.py").read_text()
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree) or ""
    assert "PRIMARY" in docstring.upper(), (
        "cyrus_brain.py module docstring must indicate PRIMARY entry point"
    )
```

**Verification**:
```bash
cd /home/daniel/Projects/barf/cyrus
python -m pytest tests/test_deprecation.py -v
```

All 6 tests should pass.

## Acceptance Criteria Mapping

| Criterion | Verified by |
|-----------|-------------|
| `main.py` refactored to be a thin wrapper | Step 2 (complete replacement), `test_main_is_thin_wrapper` |
| Deprecation warning logged on startup | Step 2 (`print()` call), `test_main_prints_deprecation_warning` |
| All business logic and state management removed from main.py | Step 2 (only import + wrapper remains) |
| main.py imports and delegates to cyrus_brain.py functions | Step 2 (`from cyrus_brain import main as brain_main`), `test_main_imports_brain_main` |
| Documentation updated: recommend split mode | Step 4 (README updated), `test_readme_documents_deprecation` |
| Tests confirm wrapper forwards calls correctly | Step 7 (6 pytest tests), `test_main_imports_brain_main` |

## Risk Notes

1. **Import side effects**: `from cyrus_brain import main as brain_main` will execute cyrus_brain.py's module-level code at import time, including the comtypes/uiautomation try/except block. This is acceptable — the same code runs when cyrus_brain.py is executed directly.

2. **_remote_route() loss**: The monolith had an experimental `--remote` flag for connecting to a remote brain via WebSocket. This feature is dropped. The split architecture is the correct way to run voice remotely (`python cyrus_voice.py --host <brain-ip>`). If remote routing is needed in the future, it should be built into the brain service (separate issue).

3. **asyncio.run() nesting**: The wrapper calls `asyncio.run(brain_main())`. If main.py is ever imported (not run as `__main__`), `main()` would try to start a new event loop. This is fine — main.py is only meant to be run as a script, and `asyncio.run()` is the standard pattern.

4. **Blocked by Issue 005**: This plan assumes cyrus_common.py exists and cyrus_brain.py imports from it. If 005 is not complete, Step 2 will fail at `from cyrus_brain import main` because cyrus_brain.py may have import-time errors (missing cyrus_common.py). The builder must verify the prerequisite in Step 1 before proceeding.

5. **Tests don't test runtime**: The pytest tests verify file structure and content statically (AST parsing, string matching). They do NOT attempt to actually run main.py, which would require audio hardware, Windows UIA, and VS Code. Runtime verification is manual (Step 2 verification commands).
