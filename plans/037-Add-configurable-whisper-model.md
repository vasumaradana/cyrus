# Plan 037: Add Configurable Whisper Model

## Summary

Make the Whisper speech-to-text model configurable via `CYRUS_WHISPER_MODEL` environment variable in `cyrus_voice.py`. Default to `medium.en`. Validate against the allowed model list (`tiny.en`, `base.en`, `small.en`, `medium.en`), warn and fall back to default on invalid input. Log the selected model at startup. Update `.env.example` to document the new variable.

## Dependencies

Blocked by Issue 027 (centralized config), which is PLANNED but NOT BUILT — `cyrus2/` is empty. Following the pattern established by plan 029 (hook host configurable): read the env var directly in `cyrus_voice.py` using `os.environ.get()`, aligned with plan 027's `CYRUS_*` naming convention. When 027 consolidates config, this becomes a clean import replacement.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `CYRUS_WHISPER_MODEL` env var | `WHISPER_MODEL = "medium.en"` hardcoded (line 48) | Replace with `os.environ.get` |
| Defaults to `medium.en` | Already `medium.en` | Default value in `os.environ.get` |
| Valid options: `tiny.en`, `base.en`, `small.en`, `medium.en` | No validation | Add `VALID_WHISPER_MODELS` list + validation |
| Voice module loads specified model | `WhisperModel(WHISPER_MODEL, ...)` (line 474) | Already uses the variable — just changing its source |
| Logs model selected at startup | `print(f"Loading Whisper {WHISPER_MODEL} on {WHISPER_DEVICE}...")` (line 473) | Add `[Config]` log line |
| Configuration validated (warn on invalid) | No validation exists | Add validation with warning + fallback |
| Works on CPU and GPU | Lines 43-44, 49-50 handle GPU/CPU detection | No change needed |
| `.env.example` updated | Only has `ANTHROPIC_API_KEY=` | Add `CYRUS_WHISPER_MODEL` |

## Key Findings from Codebase Exploration

### Current config block in `cyrus_voice.py` (lines 46–51)

```python
# ── Configuration ──────────────────────────────────────────────────────────────

WHISPER_MODEL        = "medium.en"
WHISPER_DEVICE       = "cuda" if _CUDA else "cpu"
WHISPER_COMPUTE_TYPE = "float16" if _CUDA else "int8"
SAMPLE_RATE          = 16000
CHANNELS             = 1
```

### Current model loading in `main()` (lines 473–475)

```python
print(f"Loading Whisper {WHISPER_MODEL} on {WHISPER_DEVICE}...")
whisper_model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE,
                             compute_type=WHISPER_COMPUTE_TYPE)
```

The `WHISPER_MODEL` variable is used in exactly two places: the log message and the `WhisperModel()` constructor call. Changing the variable's source from hardcoded to env var requires zero logic changes downstream.

### Test infrastructure

Plan 029 creates `cyrus2/__init__.py`, `cyrus2/tests/`, `cyrus2/tests/conftest.py`, and `cyrus2/pytest.ini`. If 029 hasn't been built yet, we create the same minimal structure (both plans handle "create if missing").

### `faster-whisper` model names

The `faster_whisper.WhisperModel` constructor accepts any CTranslate2 model size string. The four `.en` models listed in the acceptance criteria are the standard English-only variants. The constructor will raise an error itself for completely invalid names, but we validate upfront to provide a friendlier warning.

### Naming alignment with plan 027

Plan 027 defines `CYRUS_*` prefixed env vars. This plan uses `CYRUS_WHISPER_MODEL` — same convention. When 027 consolidates config into `ConfigManager`, the `WHISPER_MODEL` and `VALID_WHISPER_MODELS` constants move from `cyrus_voice.py` to `cyrus2/cyrus_config.py` as a clean cut-and-paste.

## Design Decisions

### D1. Standalone approach — read env var directly in `cyrus_voice.py`

Issue 027 is PLANNED but `cyrus2/cyrus_config.py` does not exist. Plan 029 faced the same situation and chose to work standalone. We follow the same pattern: read `os.environ.get()` directly in the voice module, using the same `CYRUS_*` env var name that 027 will adopt. When 027 lands, it replaces the local reading with an import — one-line diff.

### D2. Validation warns but does not crash

The issue says "warn on invalid model name" — not "reject." The validation warns and falls back to `medium.en`, matching the issue spec exactly. The voice service always starts.

### D3. `WHISPER_DEVICE` and `WHISPER_COMPUTE_TYPE` stay hardcoded

These are derived from CUDA availability (hardware detection at import time) and are not user-configurable settings. The issue spec only asks for model selection.

### D4. Logging follows existing `print("[Tag] ...")` pattern

No logging framework exists yet (Issue 009 plans it). Current codebase uses bare `print()` with prefix tags. Validation warning uses `print("WARN: ...")` matching the issue spec exactly. Startup log uses `print(f"[Config] Whisper model: ...")`.

### D5. `large` models deliberately excluded from valid list

The acceptance criteria list exactly four models: `tiny.en`, `base.en`, `small.en`, `medium.en`. The `large-v3` (3GB) exists but isn't listed — likely intentional given Cyrus's real-time voice latency requirements. The valid list matches the spec exactly.

### D6. Empty string env var treated as unset

`os.environ.get("CYRUS_WHISPER_MODEL", "medium.en")` returns `""` if the var is set to empty. The validation catches this (empty string is not in `VALID_WHISPER_MODELS`) and falls back to default.

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Test |
|---|---|---|
| AC1 | `CYRUS_WHISPER_MODEL` env var read | `test_reads_env_var` |
| AC2 | Defaults to `medium.en` | `test_defaults_to_medium_en` |
| AC3 | Valid options: `tiny.en`, `base.en`, `small.en`, `medium.en` | `test_valid_models_accepted` (parametrized) |
| AC4 | Voice module loads specified model | Variable flows through to `WhisperModel()` — no code change at call site |
| AC5 | Logs model selected at startup | `test_startup_config_log` (captured print output) |
| AC6 | Validated — warn on invalid model name | `test_invalid_model_warns_and_falls_back` |
| AC7 | Works on CPU and GPU | No change needed — device selection is independent of model name |

## Implementation Steps

### Step 1: Create test infrastructure (if missing)

If plan 029 hasn't been built yet, create the minimal structure. Both plans handle "create if missing" explicitly.

**Create** (if missing):
- `cyrus2/__init__.py` — empty
- `cyrus2/tests/__init__.py` — empty
- `cyrus2/pytest.ini` — with `pythonpath = ..`

```bash
cd /home/daniel/Projects/barf/cyrus
mkdir -p cyrus2/tests
touch cyrus2/__init__.py
touch cyrus2/tests/__init__.py
```

**File**: `cyrus2/pytest.ini` (if missing)
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
pythonpath = ..
```

### Step 2: Write tests (RED)

**File**: `cyrus2/tests/test_whisper_config.py`

```python
"""Tests for Whisper model configuration (Issue 037).

Verifies CYRUS_WHISPER_MODEL env var support in cyrus_voice.py.
"""

from __future__ import annotations

import importlib
import io
import os
from contextlib import redirect_stdout

import pytest


def _reload_voice():
    """Re-import cyrus_voice to pick up env var changes."""
    import cyrus_voice
    return importlib.reload(cyrus_voice)


class TestWhisperModelDefault:
    """Default value when env var not set."""

    def test_defaults_to_medium_en(self):
        """AC2: WHISPER_MODEL defaults to medium.en."""
        os.environ.pop("CYRUS_WHISPER_MODEL", None)
        voice = _reload_voice()
        assert voice.WHISPER_MODEL == "medium.en"

    def test_valid_models_list_exists(self):
        """AC3: VALID_WHISPER_MODELS contains the four accepted models."""
        voice = _reload_voice()
        assert voice.VALID_WHISPER_MODELS == [
            "tiny.en", "base.en", "small.en", "medium.en"
        ]


class TestWhisperModelOverride:
    """CYRUS_WHISPER_MODEL env var behavior."""

    @pytest.mark.parametrize("model", ["tiny.en", "base.en", "small.en", "medium.en"])
    def test_valid_models_accepted(self, model):
        """AC1+AC3: Each valid model is accepted without warning."""
        os.environ["CYRUS_WHISPER_MODEL"] = model
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                voice = _reload_voice()
            assert voice.WHISPER_MODEL == model
            assert "WARN" not in buf.getvalue()
        finally:
            del os.environ["CYRUS_WHISPER_MODEL"]

    def test_reads_env_var(self):
        """AC1: WHISPER_MODEL reads from CYRUS_WHISPER_MODEL."""
        os.environ["CYRUS_WHISPER_MODEL"] = "tiny.en"
        try:
            voice = _reload_voice()
            assert voice.WHISPER_MODEL == "tiny.en"
        finally:
            del os.environ["CYRUS_WHISPER_MODEL"]


class TestWhisperModelValidation:
    """Invalid model name handling."""

    def test_invalid_model_warns_and_falls_back(self):
        """AC6: Invalid model warns and falls back to medium.en."""
        os.environ["CYRUS_WHISPER_MODEL"] = "invalid-model"
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                voice = _reload_voice()
            output = buf.getvalue()
            assert voice.WHISPER_MODEL == "medium.en"
            assert "WARN" in output
            assert "invalid-model" in output
            assert "medium.en" in output
        finally:
            del os.environ["CYRUS_WHISPER_MODEL"]

    def test_large_model_rejected(self):
        """large-v3 is not in valid list — treated as invalid."""
        os.environ["CYRUS_WHISPER_MODEL"] = "large-v3"
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                voice = _reload_voice()
            assert voice.WHISPER_MODEL == "medium.en"
            assert "WARN" in buf.getvalue()
        finally:
            del os.environ["CYRUS_WHISPER_MODEL"]

    def test_empty_string_falls_back(self):
        """Empty string is not valid — falls back to default."""
        os.environ["CYRUS_WHISPER_MODEL"] = ""
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                voice = _reload_voice()
            assert voice.WHISPER_MODEL == "medium.en"
        finally:
            del os.environ["CYRUS_WHISPER_MODEL"]
```

**Run** (expected: FAIL — `VALID_WHISPER_MODELS` doesn't exist, env var not read):
```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_whisper_config.py -v
```

### Step 3: Modify `cyrus_voice.py` (GREEN)

**Replace** the hardcoded `WHISPER_MODEL` assignment (line 48) with env var reading and validation:

```python
# BEFORE (line 48)
WHISPER_MODEL        = "medium.en"

# AFTER (lines 48-56)
VALID_WHISPER_MODELS = ["tiny.en", "base.en", "small.en", "medium.en"]
WHISPER_MODEL        = os.environ.get("CYRUS_WHISPER_MODEL", "medium.en")

if WHISPER_MODEL not in VALID_WHISPER_MODELS:
    print(f"WARN: CYRUS_WHISPER_MODEL={WHISPER_MODEL} not in {VALID_WHISPER_MODELS}")
    print(f"      Using default: medium.en")
    WHISPER_MODEL = "medium.en"
```

Note: `os` is already imported at line 23. No new imports needed.

**Add** a `[Config]` log line in `main()`, before the existing Whisper loading log (before line 473):

```python
    print(f"[Config] Whisper model: {WHISPER_MODEL}")
```

The existing line at 473 (`f"Loading Whisper {WHISPER_MODEL}..."`) already uses the constant and will pick up the configured value automatically.

**Run** (expected: all PASS):
```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_whisper_config.py -v
```

### Step 4: Update `.env.example`

**File**: `.env.example` — Append the Whisper model documentation after the existing `ANTHROPIC_API_KEY=` line:

```env
ANTHROPIC_API_KEY=

# ── Whisper Speech Recognition ─────────────────────────────────────────────
# Model for speech-to-text. Larger = more accurate but slower and more VRAM.
# Options: tiny.en (39M, fastest), base.en (74M), small.en (244M), medium.en (769M, default)
# CYRUS_WHISPER_MODEL=medium.en
```

Note: If plan 029 has already expanded `.env.example`, append the Whisper section after the existing content rather than replacing.

### Step 5: Verify end-to-end

```bash
cd /home/daniel/Projects/barf/cyrus

# 1. Tests pass
cd cyrus2 && pytest tests/test_whisper_config.py -v && cd ..

# 2. Default — module-level constant is medium.en
python3 -c "
import cyrus_voice
assert cyrus_voice.WHISPER_MODEL == 'medium.en'
assert 'medium.en' in cyrus_voice.VALID_WHISPER_MODELS
print('Default OK')
"

# 3. Override — tiny.en accepted
CYRUS_WHISPER_MODEL=tiny.en python3 -c "
import cyrus_voice
assert cyrus_voice.WHISPER_MODEL == 'tiny.en'
print('Override OK')
"

# 4. Invalid — warns and falls back
CYRUS_WHISPER_MODEL=invalid python3 -c "
import cyrus_voice
assert cyrus_voice.WHISPER_MODEL == 'medium.en'
print('Fallback OK')
"

# 5. .env.example has the var
grep 'CYRUS_WHISPER_MODEL' .env.example
```

### Step 6: Commit

```bash
cd /home/daniel/Projects/barf/cyrus
git add cyrus_voice.py .env.example cyrus2/
git commit -m "feat(voice): make Whisper model configurable via CYRUS_WHISPER_MODEL

Add CYRUS_WHISPER_MODEL env var support (default: medium.en). Validates
against allowed models (tiny.en, base.en, small.en, medium.en), warns
and falls back to default on invalid input. Logs selected model at startup.

Issue: 037-Add-configurable-whisper-model"
```

## Files Created/Modified

| File | Action | Purpose |
|---|---|---|
| `cyrus_voice.py` | **Modify** (line 48 → 8 lines, +1 log line in main) | Read `CYRUS_WHISPER_MODEL` from env, validate, log |
| `.env.example` | **Update** | Document `CYRUS_WHISPER_MODEL` with model size info |
| `cyrus2/__init__.py` | **Create** (if missing) | Make cyrus2 a Python package |
| `cyrus2/tests/__init__.py` | **Create** (if missing) | Test package init |
| `cyrus2/pytest.ini` | **Create** (if missing) | pytest config with `pythonpath = ..` |
| `cyrus2/tests/test_whisper_config.py` | **Create** | 9 tests for env var config + validation behavior |

## Risk Assessment

**Very low risk.** Production change is 8 lines replacing 1 line in the config block, plus 1 log line in `main()`. No changes to audio pipeline, VAD, TTS, or brain communication.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Module reload in tests fails due to audio hardware imports | Tests can't run in CI | Medium | `cyrus_voice.py` imports `sounddevice`, `keyboard`, etc. at top level. Tests may need mocking of hardware dependencies. If reload fails, fall back to subprocess-based tests (`python3 -c "..."` with env vars). |
| Test infrastructure conflicts with plans 029, 018, 022 | Merge conflicts | Low | All plans handle "create if missing". Identical minimal structure. |
| User sets valid-for-faster-whisper but unlisted model (e.g., `large-v3`) | Warn + fallback, user surprised | Low | Warning message is clear. User can check the valid list. If demand arises for `large` support, expand `VALID_WHISPER_MODELS` later. |
| `os.environ.get` returns empty string when var set to `""` | Could bypass simple `if` check | Low | Empty string is not in `VALID_WHISPER_MODELS`, so validation catches it and falls back to default. |
