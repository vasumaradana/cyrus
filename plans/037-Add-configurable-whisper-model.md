# Implementation Plan: Add Configurable Whisper Model

**Issue**: [037-Add-configurable-whisper-model](/home/daniel/Projects/barf/cyrus/cyrus/issues/037-Add-configurable-whisper-model.md)
**Created**: 2026-03-18
**PROMPT**: [PROMPT_plan](/home/daniel/Projects/barf/cyrus/prompts/PROMPT_plan.md)

## Gap Analysis

**Already exists**:
- Centralized config module `cyrus2/cyrus_config.py` (Issue 027) with `os.environ.get("CYRUS_*", default)` pattern
- `.env.example` with full documentation of all current env vars
- `cyrus2/cyrus_voice.py` line 63: hardcoded `WHISPER_MODEL = "medium.en"` as a module-level constant
- `cyrus2/cyrus_voice.py` line 540: startup log `log.info("Loading Whisper %s on %s...", WHISPER_MODEL, WHISPER_DEVICE)`
- WhisperModel loading at lines 541-543 already uses the `WHISPER_MODEL` variable
- Test infrastructure: `cyrus2/tests/test_027_cyrus_config.py` with `_reload_with_env()` helper, unittest.TestCase classes

**Needs building**:
- `WHISPER_MODEL` and `VALID_WHISPER_MODELS` in `cyrus2/cyrus_config.py` with env var `CYRUS_WHISPER_MODEL`
- Validation logic: warn on invalid model name, fallback to `medium.en`
- Import `WHISPER_MODEL` from `cyrus_config` in `cyrus_voice.py` (replace hardcoded value)
- `CYRUS_WHISPER_MODEL` documented in `cyrus2/.env.example`
- Config startup log: `[Config] Whisper model: {WHISPER_MODEL}`
- Test file `cyrus2/tests/test_037_whisper_model_config.py`

## Approach

**Follow existing config pattern exactly.** The centralized config module (Issue 027) established a clear pattern: env var read at import time with typed annotation and default. This issue adds one string config value with validation — the only novel part is the `VALID_WHISPER_MODELS` whitelist with fallback, which mirrors the existing `AUTH_TOKEN` auto-generation pattern (warn to stderr, set a safe default).

**Why validation in cyrus_config.py (not cyrus_voice.py):** The config module already handles validation for AUTH_TOKEN. Keeping validation centralized means any consumer of WHISPER_MODEL gets a validated value. This matches the module's documented purpose.

**Why print() not logging:** cyrus_config.py uses `print(..., file=sys.stderr)` for warnings (see AUTH_TOKEN pattern) because it imports no third-party packages — this keeps it safe for CI/test/headless use.

## Rules to Follow
- `.claude/skills/python-expert/AGENTS.md` — Type hints mandatory, Google-style docstrings, PEP 8
- `.claude/skills/python-testing/SKILL.md` — TDD red-green-refactor, 80%+ coverage, acceptance-driven tests
- `.claude/skills/python-code-style/SKILL.md` — 120-char line limit, ruff linting, Google-style docstrings
- `.claude/skills/python-linting/SKILL.md` — `ruff check .` must pass

## Skills & Agents to Use
| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Add config values | `python-expert` skill | Type safety, PEP 8, docstring conventions |
| Write tests | `python-testing` skill | TDD with pytest, acceptance-driven tests |
| Lint validation | `python-linting` skill | ruff check enforcement |

## Prioritized Tasks
- [x] 1. Add `WHISPER_MODEL` and `VALID_WHISPER_MODELS` to `cyrus2/cyrus_config.py`:
  - New section "Whisper speech-to-text" after Miscellaneous
  - `VALID_WHISPER_MODELS: list[str] = ["tiny.en", "base.en", "small.en", "medium.en"]`
  - `WHISPER_MODEL: str = os.environ.get("CYRUS_WHISPER_MODEL", "medium.en")`
  - Validation: if not in list, print warning to stderr, reset to `"medium.en"`
- [x] 2. Document `CYRUS_WHISPER_MODEL` in `cyrus2/.env.example`:
  - New section "Whisper speech-to-text" before Authentication
  - Include model sizes: tiny.en (39M), base.en (244M), small.en (774M), medium.en (1.5GB, default)
- [x] 3. Update `cyrus2/cyrus_voice.py`:
  - Add `WHISPER_MODEL` to the existing `from cyrus2.cyrus_config import (...)` block
  - Remove hardcoded `WHISPER_MODEL = "medium.en"` on line 63
  - Keep `WHISPER_DEVICE` and `WHISPER_COMPUTE_TYPE` as-is (they depend on local `_CUDA` detection, not config)
  - Existing startup log already logs the model — no change needed
- [x] 4. Write tests in `cyrus2/tests/test_037_whisper_model_config.py`:
  - Follow exact pattern from `test_027_cyrus_config.py`
  - Reuse `_reload_with_env()` helper pattern
  - Test default value is `"medium.en"`
  - Test each valid model override: tiny.en, base.en, small.en, medium.en
  - Test invalid model falls back to `"medium.en"` with warning
  - Test `VALID_WHISPER_MODELS` list contains exactly the 4 expected models
  - Test `.env.example` contains `CYRUS_WHISPER_MODEL`
- [x] 5. Run ruff check and fix any lint issues
- [x] 6. Run full test suite to verify no regressions

## Acceptance-Driven Tests
| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| `CYRUS_WHISPER_MODEL` env var read in cyrus_config.py | Test WHISPER_MODEL is importable from cyrus_config | unit |
| Defaults to `medium.en` | Test WHISPER_MODEL == "medium.en" with no env var set | unit |
| Valid options: tiny.en, base.en, small.en, medium.en | Test VALID_WHISPER_MODELS contains exactly these 4 values | unit |
| Voice module loads specified model on startup | Test env var override changes WHISPER_MODEL value (for each valid model) | unit |
| Logs model selected at startup | Test startup log message includes model name (existing log in cyrus_voice.py) | integration |
| Configuration validated (warn on invalid model name) | Test invalid model triggers stderr warning and falls back to medium.en | unit |
| Works on CPU and GPU | No code-level test needed — WHISPER_DEVICE/COMPUTE_TYPE are orthogonal to model selection | n/a |

**No cheating** — cannot claim done without required tests passing.

## Validation (Backpressure)
- Tests: `cd cyrus2 && uv run pytest tests/test_037_whisper_model_config.py -v` must pass
- Full suite: `cd cyrus2 && uv run pytest -q` must pass with no regressions
- Lint: `cd cyrus2 && uv run ruff check .` must pass

## Files to Create/Modify
- `cyrus2/cyrus_config.py` — add WHISPER_MODEL, VALID_WHISPER_MODELS with validation
- `cyrus2/.env.example` — document CYRUS_WHISPER_MODEL with model sizes
- `cyrus2/cyrus_voice.py` — import WHISPER_MODEL from cyrus_config, remove hardcoded value
- `cyrus2/tests/test_037_whisper_model_config.py` (new) — acceptance-driven tests

## Key Design Decisions

**Validation with fallback (not crash):** Invalid model names produce a stderr warning and fall back to `medium.en`, matching the AUTH_TOKEN pattern. Crashing on invalid config would be hostile — the user may have a typo but still wants the system to work.

**String type (no enum):** Whisper model names are strings passed to `WhisperModel()` constructor. Using a Python enum would add complexity for no benefit — the whitelist validation is sufficient.

**Keep WHISPER_DEVICE/COMPUTE_TYPE in cyrus_voice.py:** These depend on runtime CUDA detection (`_CUDA` flag computed from `torch.cuda.is_available()`). Moving them to cyrus_config.py would require importing torch there, violating the "no hardware imports" rule. They are orthogonal to model selection.

**4 models only (no large/turbo):** The issue specifies exactly `tiny.en`, `base.en`, `small.en`, `medium.en`. The `.en` suffix means English-only variants which are smaller and faster. Non-English and `large` models are excluded by design — they can be added later if needed.
