---
id=006-Deprecate-main-py-monolith
title=Issue 006: Deprecate main.py monolith
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=46716
total_output_tokens=6
total_duration_seconds=102
total_iterations=1
run_count=1
---

# Issue 006: Deprecate main.py monolith

## Sprint
Cyrus 2.0 Rewrite — Sprint 1

## Priority
Critical

## References
- docs/15-recommendations.md — #2 (deprecate main.py monolith)
- Issue 005 (must extract common code first)

## Description
After common code extraction (Issue 005), `main.py` becomes redundant. The split architecture (brain + voice) is strictly better: it allows independent restart/upgrade and clearer separation of concerns. Reduce `main.py` to a thin wrapper that delegates to `cyrus_brain.py`, and add a deprecation warning on startup.

## Blocked By
- Issue 005 (Extract shared code into cyrus_common.py)

## Acceptance Criteria
- [ ] `cyrus2/main.py` refactored to be a thin wrapper
- [ ] Deprecation warning logged on startup (visible to user)
- [ ] All business logic and state management removed from `main.py`
- [ ] `main.py` imports and delegates to `cyrus_brain.py` functions
- [ ] Documentation updated: recommend `cyrus_brain.py + cyrus_voice.py` as primary mode
- [ ] Tests confirm wrapper forwards calls correctly

## Implementation Steps

1. **Identify the core functions** in current `main.py` that should move to `cyrus_brain.py` or stay in `main.py` as wrapper-only:
   - Session management → stays in `cyrus_brain.py` (already there)
   - Main event loop → stays in `cyrus_brain.py`
   - Permission handling → stays in `cyrus_brain.py`
   - VAD/TTS initialization → should move to `cyrus_brain.py` (Issue 008)

2. **Refactor `cyrus2/main.py`** to:
   ```python
   """
   Cyrus - All-in-one monolith mode (DEPRECATED)

   Combines voice, brain, and TTS in a single process.
   This mode is maintained for backward compatibility only.

   Recommended: Use split mode instead:
     python cyrus_brain.py &
     python cyrus_voice.py
   """

   import logging
   import sys

   # Import everything from cyrus_brain as the main implementation
   from cyrus_brain import main as brain_main

   def main():
       logger = logging.getLogger(__name__)
       logger.warning(
           "⚠️  DEPRECATION: main.py monolith mode is deprecated. "
           "Use split mode instead:\n"
           "  python cyrus_brain.py &\n"
           "  python cyrus_voice.py\n"
           "Split mode allows independent restart and clearer separation of concerns."
       )
       # Delegate to brain's main
       return brain_main()

   if __name__ == "__main__":
       try:
           main()
       except KeyboardInterrupt:
           print("\n[Cyrus] Shutting down.")
           sys.exit(0)
   ```

3. **Update documentation** in `/home/daniel/Projects/barf/cyrus/cyrus2/README.md`:
   - Add section: "Recommended: Split Mode" (brain + voice)
   - Add section: "Legacy: Monolith Mode" (main.py, with deprecation note)
   - Provide examples for both

4. **Update comments** in `cyrus2/cyrus_brain.py`:
   - Add: "This is the primary entry point for Cyrus. main.py is deprecated; use this directly."

5. **Verify no critical code** is in old `main.py` only:
   - Search for functions/classes defined in `main.py` but not in `cyrus_brain.py`
   - Any found should be moved to `cyrus_brain.py` in Issue 008

6. **Log the deprecation warning** every time `main.py` is run:
   ```bash
   python cyrus2/main.py
   # Should print:
   # ⚠️  DEPRECATION: main.py monolith mode is deprecated...
   ```

## Files to Create/Modify
- Modify: `cyrus2/main.py` (reduce to ~20 lines)
- Modify: `cyrus2/cyrus_brain.py` (add comment about being primary entry point)
- Create/Update: `cyrus2/README.md` (document split vs monolith mode)

## Testing
- Run `python cyrus2/main.py` and verify deprecation warning is shown
- Run `python cyrus2/cyrus_brain.py` directly and verify it works
- Run both in split mode and verify they communicate correctly
- Grep for functions defined only in old main.py: `grep "^def " cyrus2/main.py | grep -v "brain_main"`

## Stage Log

### GROOMED — 2026-03-11 18:07:04Z

- **From:** NEW
- **Duration in stage:** 102s
- **Input tokens:** 46,716 (final context: 46,716)
- **Output tokens:** 6
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
