---
id=002-Run-ruff-autofix-and-format
title=Issue 002: Run Ruff Autofix and Format on v1 Codebase
state=PLANNED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=69376
total_output_tokens=28
total_duration_seconds=224
total_iterations=2
run_count=2
---

# Issue 002: Run Ruff Autofix and Format on v1 Codebase

## Sprint
Cyrus 2.0 Rewrite — Foundation (Week 1)

## Priority
Critical

## References
- docs/17-ruff-linting.md — Ruff check and format commands
- docs/12-code-audit.md — Code quality baseline

## Description
Copy all Python files from v1 (project root) into `cyrus2/` and apply Ruff autofix + formatting. This is the starting point for the rewrite: we port existing v1 code as-is, then transform it via subsequent issues. Ruff will enforce consistent style across all copied files.

## Blocked By
- Issue 001: Create pyproject.toml with Ruff Config (required for Ruff to recognize config)

## Acceptance Criteria
- [ ] All v1 .py files copied to cyrus2/ directory
- [ ] `ruff check --fix .` applied to cyrus2/ (all autofixable violations corrected)
- [ ] `ruff format .` applied to cyrus2/ (all files reformatted to line-length 88)
- [ ] `ruff check .` reports zero violations
- [ ] `ruff format --check .` confirms all files are formatted
- [ ] Git diff shows only formatting/import-ordering changes, no logic changes

## Implementation Steps
1. Ensure Issue 001 is complete (pyproject.toml exists)
2. From project root, identify all v1 Python files:
   - `main.py`
   - `cyrus_voice.py`
   - `cyrus_brain.py`
   - `cyrus_server.py`
   - `cyrus_hook.py`
   - `probe_uia.py`
   - `test_permission_scan.py`
3. Copy each file to cyrus2/:
   ```bash
   cp main.py cyrus2/
   cp cyrus_voice.py cyrus2/
   cp cyrus_brain.py cyrus2/
   cp cyrus_server.py cyrus2/
   cp cyrus_hook.py cyrus2/
   cp probe_uia.py cyrus2/
   cp test_permission_scan.py cyrus2/
   ```
4. Install ruff (if not already installed):
   ```bash
   pip install ruff
   ```
5. Run autofix on cyrus2/:
   ```bash
   cd cyrus2
   ruff check --fix .
   ```
6. Run formatter on cyrus2/:
   ```bash
   ruff format .
   ```
7. Verify all checks pass:
   ```bash
   ruff check .
   ```
8. If any violations remain that ruff cannot auto-fix, resolve manually or create follow-up issues

## Files to Create/Modify
- `cyrus2/main.py` (copy from root, apply ruff)
- `cyrus2/cyrus_voice.py` (copy from root, apply ruff)
- `cyrus2/cyrus_brain.py` (copy from root, apply ruff)
- `cyrus2/cyrus_server.py` (copy from root, apply ruff)
- `cyrus2/cyrus_hook.py` (copy from root, apply ruff)
- `cyrus2/probe_uia.py` (copy from root, apply ruff)
- `cyrus2/test_permission_scan.py` (copy from root, apply ruff)

## Testing
```bash
# Verify all files were copied
ls -la cyrus2/*.py

# Verify all checks pass
cd cyrus2
ruff check .

# Verify all files are formatted
ruff format --check .

# Review diff to ensure only formatting changed
git diff cyrus2/ | head -50
```

## Notes
- This is a **mechanical copy + format** step. No logic changes should occur.
- Any violations that ruff cannot auto-fix will be reported in the ruff check output.
- Common non-autofixable issues: very long lines (may need manual refactoring), unused imports in guarded try-blocks, or mypy-style comments.
- Subsequent issues (003+) will refactor the code to address architectural issues.

## Stage Log

### GROOMED — 2026-03-11 17:45:43Z

- **From:** NEW
- **Duration in stage:** 49s
- **Input tokens:** 35,013 (final context: 35,013)
- **Output tokens:** 3
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage

### PLANNED — 2026-03-11 19:50:32Z

- **From:** PLANNED
- **Duration in stage:** 175s
- **Input tokens:** 34,363 (final context: 34,363)
- **Output tokens:** 25
- **Iterations:** 1
- **Context used:** 17%
- **Model:** claude-opus-4-6
- **Trigger:** auto/plan
