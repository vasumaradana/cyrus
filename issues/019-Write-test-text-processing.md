---
id=019-Write-test-text-processing
title=Issue 019: Write test_text_processing.py (Tier 1)
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=44702
total_output_tokens=8
total_duration_seconds=103
total_iterations=1
run_count=1
---

# Issue 019: Write test_text_processing.py (Tier 1)

## Sprint
Sprint 3 — Test Suite

## Priority
Critical

## References
- [docs/14-test-suite.md — Tier 1: Pure Function Tests](../docs/14-test-suite.md#tier-1-pure-function-tests-zero-mocking)
- `cyrus2/cyrus_brain.py:153-191` (functions to test)
- `cyrus2/cyrus_voice.py:113-118` (_strip_fillers)

## Description
Tier 1 pure function tests for text processing: clean_for_speech(), _sanitize_for_speech(), and _strip_fillers(). Approximately 30 test cases covering markdown stripping, Unicode normalization, code block truncation, and filler word removal. Zero mocking required.

## Blocked By
- Issue 005 (cyrus_common.py foundation)
- Issue 018 (conftest.py fixtures)

## Acceptance Criteria
- [ ] `cyrus2/tests/test_text_processing.py` exists with 30+ test cases
- [ ] `test_clean_for_speech()` covers ~15 cases: markdown, code blocks, truncation, edge cases
- [ ] `test_sanitize_for_speech()` covers ~8 cases: Unicode→ASCII (em dash, quotes, accents, etc.)
- [ ] `test_strip_fillers()` covers ~8 cases: leading filler words (um, uh, like, you know)
- [ ] All tests pass: `pytest tests/test_text_processing.py -v`
- [ ] Test names clearly indicate the scenario (e.g., test_clean_for_speech_strips_markdown)

## Implementation Steps
1. Create `cyrus2/tests/test_text_processing.py`
2. Import functions from `cyrus_brain.py` and `cyrus_voice.py`:
   ```python
   from cyrus_brain import clean_for_speech, _sanitize_for_speech
   from cyrus_voice import _strip_fillers
   ```
3. Write test_clean_for_speech() with cases:
   - Markdown headers/bold/italic stripped
   - Code blocks (``` ```) truncated/removed
   - URL truncation
   - Length truncation at 1024 chars
   - Empty string handling
   - Whitespace normalization
4. Write test_sanitize_for_speech() with cases:
   - Em dash (—) → hyphen
   - Quotes (" ' « ») → normal quotes
   - Accented chars (é, ñ, ü) → unaccented
   - Symbols (™, ©, →) → text equivalents
   - Mixed Unicode preservation where safe
5. Write test_strip_fillers() with cases:
   - "um hello" → "hello"
   - "uh you know what" → "what"
   - "like really cool" → "really cool"
   - No fillers returns unchanged
   - Multiple filler words in sequence
6. Use pytest.mark.parametrize for data-driven tests

## Files to Create/Modify
- `cyrus2/tests/test_text_processing.py` (new)

## Testing
```bash
pytest cyrus2/tests/test_text_processing.py -v
pytest cyrus2/tests/test_text_processing.py::test_clean_for_speech -v  # Run one family
pytest cyrus2/tests/test_text_processing.py -k "sanitize" -v  # Run by pattern
```

## Stage Log

### GROOMED — 2026-03-11 18:25:03Z

- **From:** NEW
- **Duration in stage:** 103s
- **Input tokens:** 44,702 (final context: 44,702)
- **Output tokens:** 8
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
