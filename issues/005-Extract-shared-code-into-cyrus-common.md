---
id=005-Extract-shared-code-into-cyrus-common
title=Issue 005: Extract shared code into cyrus_common.py
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=79166
total_output_tokens=11
total_duration_seconds=156
total_iterations=2
run_count=2
---

# Issue 005: Extract shared code into cyrus_common.py

## Sprint
Cyrus 2.0 Rewrite — Sprint 1

## Priority
Critical

## References
- docs/12-code-audit.md — C3 (90% code duplication)
- docs/15-recommendations.md — #1 (extract cyrus_common.py)

## Description
`main.py` and `cyrus_brain.py` duplicate ~2,000 lines of identical helper functions, classes, and constants. Extract all shared logic into a new `cyrus_common.py` module. Both entry points then import from it, eliminating duplication and making every subsequent refactor a single-file change.

## Blocked By
None

## Acceptance Criteria
- [ ] `cyrus2/cyrus_common.py` created with all shared functions and classes
- [ ] All functions/classes from the C3 duplication table extracted
- [ ] Both `cyrus2/main.py` and `cyrus2/cyrus_brain.py` import from `cyrus_common.py`
- [ ] No duplicate function/class definitions across files
- [ ] ~2,000 lines of duplication eliminated
- [ ] All tests pass (unit tests for pure functions added in Issue 009)

## Implementation Steps

1. **Create** `/home/daniel/Projects/barf/cyrus/cyrus2/cyrus_common.py`

2. **Extract all helper functions** (copy from source, update imports as needed):
   - `_extract_project(title: str) -> str`
   - `_make_alias(proj: str) -> str`
   - `_resolve_project(query: str, aliases: dict) -> str | None`
   - `_vs_code_windows() -> list[tuple[str, str]]`
   - `clean_for_speech(text: str) -> str`
   - `_sanitize_for_speech(text: str) -> str`
   - `_strip_fillers(text: str) -> str`
   - `_is_answer_request(text: str) -> bool`
   - `_fast_command(text: str, aliases: dict) -> tuple[str, list[str]] | None`
   - `play_chime()` (handles both audio playback and fallback)
   - `play_listen_chime()`

3. **Extract all classes**:
   - `ChatWatcher` (polls VS Code chat input field)
   - `PermissionWatcher` (monitors permission dialogs)
   - `SessionManager` (manages chat history per project)

4. **Extract all constants**:
   - `_FILLER_RE` (regex pattern for speech fillers)
   - `_HALLUCINATIONS` (set of common Whisper misrecognitions)
   - `_CHAT_INPUT_HINT`
   - `VSCODE_TITLE`
   - `MAX_SPEECH_WORDS` (keep configurable in main.py / cyrus_brain.py for override)

5. **Update imports** in `cyrus2/main.py`:
   ```python
   from cyrus_common import (
       _extract_project, _make_alias, _resolve_project, _vs_code_windows,
       clean_for_speech, _strip_fillers, _is_answer_request, _fast_command,
       play_chime, play_listen_chime,
       ChatWatcher, PermissionWatcher, SessionManager,
       _FILLER_RE, _HALLUCINATIONS
   )
   ```

6. **Update imports** in `cyrus2/cyrus_brain.py`:
   ```python
   from cyrus_common import (
       _extract_project, _make_alias, _resolve_project, _vs_code_windows,
       clean_for_speech, _strip_fillers,
       ChatWatcher, PermissionWatcher, SessionManager,
       _FILLER_RE, _HALLUCINATIONS
   )
   ```

7. **Remove** all duplicate definitions from `cyrus2/main.py` and `cyrus2/cyrus_brain.py`

8. **Verify** no import errors by running:
   ```bash
   cd /home/daniel/Projects/barf/cyrus/cyrus2
   python -c "import cyrus_common; print('OK')"
   ```

## Files to Create/Modify
- Create: `cyrus2/cyrus_common.py` (1,500–2,000 lines)
- Modify: `cyrus2/main.py` (add imports, remove duplicates)
- Modify: `cyrus2/cyrus_brain.py` (add imports, remove duplicates)

## Testing
- Import `cyrus_common` in both `main.py` and `cyrus_brain.py` without errors
- Verify duplicate definitions are gone: `grep -r "^def _extract_project" cyrus2/`
- Run linter on all three files: `pylint cyrus_common.py main.py cyrus_brain.py`
- Line count comparison (before vs after): `wc -l cyrus2/*.py`

## Stage Log

### NEW — 2026-03-11 17:49:25Z

- **From:** NEW
- **Duration in stage:** 90s
- **Input tokens:** 52,964 (final context: 52,964)
- **Output tokens:** 8
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage


### GROOMED — 2026-03-11 17:58:52Z

- **From:** NEW
- **Duration in stage:** 66s
- **Input tokens:** 26,202 (final context: 26,202)
- **Output tokens:** 3
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** interview
## Interview Q&A

1. **Q:** The refactoring of main.py to use service-delegation (required before extraction per the interview)—should this refactoring be a separate issue completed first, or is it part of 005's scope?
   **A:** Part of 005's scope (refactor main.py first, then extract shared code)

2. **Q:** The issue lists `_sanitize_for_speech()` as a function to extract, but it only exists in cyrus_brain.py, not in main.py. Should the extraction ignore this function, add it to main.py first, or handle it differently?
   **A:** Only extract to cyrus_common.py and have cyrus_brain.py import it (main.py won't use it)

3. **Q:** MAX_SPEECH_WORDS has different values in each file (main.py=30, cyrus_brain.py=50). The issue acknowledges this but implies it should be extracted. Should it remain configurable per file instead of being shared?
   **A:** Extract to cyrus_common.py with a per-file override mechanism
