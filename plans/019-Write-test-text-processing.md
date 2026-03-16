# Plan 019: Write test_text_processing.py (Tier 1)

## Summary

Create `cyrus2/tests/test_text_processing.py` with 32 parametrized test cases covering three pure text-processing functions: `clean_for_speech()` (15 cases), `_sanitize_for_speech()` (9 cases), and `_strip_fillers()` (8 cases). Zero mocking — all functions are pure `str → str` transforms.

## Prerequisites

- **Issue 018** (PLANNED) — creates `cyrus2/tests/` directory, `conftest.py`, and pytest config with `pythonpath = [".."]` so `import cyrus_brain` works from test files.
- **Issue 005** — cyrus_common.py foundation (dependency listed in issue, but text processing functions have no dependency on it).

If the builder runs before 018 is complete, it must create the minimal directory structure (`cyrus2/tests/__init__.py`) and ensure `pythonpath` is configured. The conftest fixtures themselves are not needed — Tier 1 tests use no fixtures.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/tests/test_text_processing.py` | Does not exist | Create with 32 test cases |
| `cyrus2/tests/` directory | Does not exist (created by issue 018) | Verify exists; create if missing |
| pytest `pythonpath = [".."]` | Defined in plan 018's pyproject.toml config | Verify; add if missing |
| Functions importable | Source at cyrus root: `cyrus_brain.py`, `cyrus_voice.py` | Import via `pythonpath` config |

## Source Code Under Test

### `_sanitize_for_speech(text: str) -> str` — cyrus_brain.py:153-164

Eight chained `.replace()` calls converting TTS-hostile Unicode to ASCII:

| Unicode | Char | Replacement |
|---|---|---|
| `\u2014` | — (em dash) | `, ` |
| `\u2013` | – (en dash) | `, ` |
| `\u2026` | … (ellipsis) | `...` |
| `\u2018` | ' (left single quote) | `'` |
| `\u2019` | ' (right single quote) | `'` |
| `\u201c` | " (left double quote) | `"` |
| `\u201d` | " (right double quote) | `"` |
| `\u2022` | • (bullet) | `, ` |

### `clean_for_speech(text: str) -> str` — cyrus_brain.py:167-183

Sequential pipeline: 10 regex substitutions → `_sanitize_for_speech()` → word truncation at `MAX_SPEECH_WORDS = 50` → `.strip()`.

Transformations in order:
1. Code blocks (triple backtick) → `"See the chat for the code."`
2. Inline code (single backtick) → content only
3. Headings (`# `, `## `, etc.) → removed
4. Bold/italic (`*x*`, `**x**`, `***x***`) → `x`
5. Links (`[label](url)`) → `label`
6. Horizontal rules (`---`, `***`, `___`) → space
7. Bullet lists (`\n- item`) → `. item`
8. Numbered lists (`\n1. item`) → `. item`
9. Newlines → space
10. Multiple spaces → single space
11. Unicode sanitization via `_sanitize_for_speech()`
12. Word-count truncation: if `len(words) > 50`, keep first 50 + `". See the chat for the full response."`
13. Final `.strip()`

### `_strip_fillers(text: str) -> str` — cyrus_voice.py:113-118

Fixed-point loop applying `_FILLER_RE` until no change:

```python
_FILLER_RE = re.compile(
    r"^(?:uh+|um+|er+|so|okay|ok|right|hey|please|can you|could you|would you)\s+",
    re.IGNORECASE,
)
```

Strips leading filler words/phrases iteratively. `"um so can you help"` → `"help"` (4 iterations).

## Design Decisions

### 1. Use `@pytest.mark.parametrize` throughout

All three functions are pure `str → str` transforms — perfect for parametrize. Each test function has one `@pytest.mark.parametrize` decorator with a list of `(input, expected)` tuples. IDs derived from descriptive slugs for readable output.

### 2. Import strategy

```python
from cyrus_brain import clean_for_speech, _sanitize_for_speech
from cyrus_voice import _strip_fillers
```

These imports trigger module-level code in both files (pygetwindow, sounddevice, etc.). The test environment must have all production dependencies installed. This matches the project's intent — Cyrus is a Windows desktop app and tests run on the same machine.

### 3. Test naming convention

Functions named `test_<function_name>` with parametrize IDs providing scenario context. pytest output:

```
test_text_processing.py::test_sanitize_for_speech[em_dash] PASSED
test_text_processing.py::test_clean_for_speech[strips_markdown_headers] PASSED
test_text_processing.py::test_strip_fillers[single_um] PASSED
```

### 4. No conftest fixtures needed

Tier 1 pure function tests need no fixtures from conftest.py. The only "setup" is importing the functions.

## Acceptance Criteria → Test Mapping

| AC | Requirement | Verification |
|---|---|---|
| AC1 | `cyrus2/tests/test_text_processing.py` exists with 30+ test cases | File exists, `pytest --collect-only` shows ≥30 items |
| AC2 | `test_clean_for_speech()` covers ~15 cases | 15 parametrized cases |
| AC3 | `test_sanitize_for_speech()` covers ~8 cases | 9 parametrized cases |
| AC4 | `test_strip_fillers()` covers ~8 cases | 8 parametrized cases |
| AC5 | All tests pass: `pytest tests/test_text_processing.py -v` | Exit code 0 |
| AC6 | Test names clearly indicate scenario | Parametrize IDs are descriptive English slugs |

## Test Case Inventory

### `test_sanitize_for_speech` — 9 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `em_dash` | `"hello\u2014world"` | `"hello, world"` | Em dash → comma-space |
| `en_dash` | `"pages 1\u20135"` | `"pages 1, 5"` | En dash → comma-space |
| `ellipsis` | `"wait\u2026"` | `"wait..."` | Typographic ellipsis → three dots |
| `smart_single_quotes` | `"\u2018don\u2019t\u2019"` | `"'don't'"` | Curly singles → straight |
| `smart_double_quotes` | `"\u201cHello\u201d"` | `'"Hello"'` | Curly doubles → straight |
| `bullet` | `"\u2022 item one"` | `", item one"` | Bullet → comma-space |
| `mixed_unicode` | `"\u201cHello\u201d \u2014 \u2018world\u2019"` | `'"Hello" , \'world\''` | Multiple replacements combined |
| `plain_ascii_unchanged` | `"Hello, world!"` | `"Hello, world!"` | No Unicode → pass-through |
| `empty_string` | `""` | `""` | Edge case: empty input |

### `test_clean_for_speech` — 15 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `strips_markdown_headers` | `"# Title\n## Sub"` | `"Title Sub"` | Heading markers removed |
| `strips_bold` | `"**bold text**"` | `"bold text"` | Double-asterisk emphasis removed |
| `strips_italic` | `"*italic text*"` | `"italic text"` | Single-asterisk emphasis removed |
| `strips_bold_italic` | `"***both***"` | `"both"` | Triple-asterisk emphasis removed |
| `removes_code_blocks` | Text with triple-backtick code block | Contains `"See the chat for the code."`, no backticks | Code block replaced with message |
| `strips_inline_code` | `` "run `npm install` now" `` | `"run npm install now"` | Backticks removed, content kept |
| `converts_links` | `"click [here](https://x.com) now"` | `"click here now"` | Link → label text only |
| `removes_horizontal_rules` | `"above\n---\nbelow"` | `"above below"` | Divider → space |
| `converts_bullet_lists` | `"intro\n- one\n- two"` | `"intro. one. two"` | Bullets → sentence markers |
| `converts_numbered_lists` | `"intro\n1. first\n2. second"` | `"intro. first. second"` | Numbers → sentence markers |
| `collapses_newlines` | `"line one\n\n\nline two"` | `"line one line two"` | Multiple newlines → single space |
| `collapses_whitespace` | `"too   many   spaces"` | `"too many spaces"` | Multiple spaces → single space |
| `truncates_long_text` | 60-word string | First 50 words + `". See the chat for the full response."` | MAX_SPEECH_WORDS = 50 |
| `empty_string` | `""` | `""` | Edge case: empty input |
| `plain_text_unchanged` | `"Hello world"` | `"Hello world"` | No markdown → pass-through |

### `test_strip_fillers` — 8 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `single_um` | `"um hello"` | `"hello"` | Basic single filler |
| `single_uh` | `"uh what is that"` | `"what is that"` | Another common filler |
| `extended_filler` | `"uhhh hello"` | `"hello"` | Repeated chars (`uh+`) |
| `multiple_sequential` | `"um so can you help"` | `"help"` | Chain of fillers stripped iteratively |
| `case_insensitive` | `"UM hello"` | `"hello"` | IGNORECASE flag works |
| `no_fillers` | `"hello world"` | `"hello world"` | No change when no fillers present |
| `filler_mid_sentence` | `"hello um world"` | `"hello um world"` | Only strips from start (^ anchor) |
| `empty_string` | `""` | `""` | Edge case: empty input |

**Total: 32 test cases** (9 + 15 + 8)

## Implementation Steps

### Step 1: Verify test infrastructure exists

```bash
cd /home/daniel/Projects/barf/cyrus

# Check issue 018 artifacts
test -d cyrus2/tests/ && echo "OK: tests dir" || echo "MISSING: tests dir"
test -f cyrus2/tests/__init__.py && echo "OK: __init__" || echo "MISSING: __init__"
test -f cyrus2/tests/conftest.py && echo "OK: conftest" || echo "MISSING: conftest"
```

If `cyrus2/tests/` doesn't exist, create the minimal structure:

```bash
mkdir -p cyrus2/tests
touch cyrus2/tests/__init__.py
```

If `pythonpath` isn't configured in `pyproject.toml`, ensure it's set so `import cyrus_brain` resolves to the cyrus root.

### Step 2: Create `cyrus2/tests/test_text_processing.py`

Write all 32 test cases using `@pytest.mark.parametrize`. Structure:

```python
"""Tier 1 pure-function tests for text processing.

Tests cover:
    clean_for_speech     — markdown stripping, code block removal, word truncation
    _sanitize_for_speech — Unicode to ASCII character replacement for TTS
    _strip_fillers       — leading filler-word removal from speech input
"""

from __future__ import annotations

import pytest

from cyrus_brain import MAX_SPEECH_WORDS, clean_for_speech, _sanitize_for_speech
from cyrus_voice import _strip_fillers


@pytest.mark.parametrize(("text", "expected"), [...], ids=[...])
def test_sanitize_for_speech(text: str, expected: str) -> None:
    assert _sanitize_for_speech(text) == expected


@pytest.mark.parametrize(("text", "expected"), [...], ids=[...])
def test_clean_for_speech(text: str, expected: str) -> None:
    assert clean_for_speech(text) == expected


@pytest.mark.parametrize(("text", "expected"), [...], ids=[...])
def test_strip_fillers(text: str, expected: str) -> None:
    assert _strip_fillers(text) == expected
```

**Key notes for the builder:**

- Import `MAX_SPEECH_WORDS` from `cyrus_brain` to build the truncation test dynamically — don't hardcode 50.
- For `truncates_long_text`: generate input with `" ".join(f"word{i}" for i in range(60))`, expected = `" ".join(f"word{i}" for i in range(MAX_SPEECH_WORDS)) + ". See the chat for the full response."`.
- For `removes_code_blocks`: use a raw string with triple backticks. Verify the exact output by tracing through the regex pipeline.
- All `test_clean_for_speech` expected values must account for the full pipeline (all 10 regex subs + sanitize + truncation + strip). Trace each input through every step.

### Step 3: Run tests and iterate

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_text_processing.py -v
```

Expected: 32 tests pass. If any fail, trace the input through the function step by step and adjust expected values.

### Step 4: Verify test count

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_text_processing.py --collect-only -q | tail -1
```

Expected: `32 tests collected`

### Step 5: Run subset commands from acceptance criteria

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_text_processing.py::test_clean_for_speech -v
pytest tests/test_text_processing.py -k "sanitize" -v
pytest tests/test_text_processing.py -k "strip_fillers" -v
```

All three should pass independently.

## Import Risk

Both `cyrus_brain.py` and `cyrus_voice.py` have heavy module-level imports (pygetwindow, sounddevice, numpy, torch). If these aren't installed in the test environment, imports will fail with `ModuleNotFoundError`.

**Mitigation:** The project runs on the dev machine with all deps installed. If imports fail, the builder should:
1. First try `pip install -r requirements.txt` to ensure production deps are present.
2. If specific modules are unavailable (e.g., GPU-only packages), wrap the problematic top-level imports in try/except in the source modules — but that's a separate issue. Flag as STUCK.

## Files Created/Modified

| File | Action | Description |
|---|---|---|
| `cyrus2/tests/test_text_processing.py` | **Create** | 32 parametrized test cases across 3 test functions |
| `cyrus2/tests/` directory | **Verify** | Must exist (from issue 018) |
| `cyrus2/tests/__init__.py` | **Verify** | Must exist (from issue 018) |
