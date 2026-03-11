# Plan 002: Run Ruff Autofix and Format on v1 Codebase

## Summary

Copy all 7 v1 Python files from the project root into `cyrus2/` and apply Ruff autofix + formatting. This is a mechanical copy-and-format step — no logic changes. The result is a clean, consistently styled starting point for the v2 rewrite.

## Dependency

**Blocked by Issue 001** (state: PLANNED). `cyrus2/pyproject.toml` must exist with the Ruff config before `ruff check` and `ruff format` can discover their settings. The builder must verify `cyrus2/pyproject.toml` exists before proceeding — if it doesn't, the build cannot continue.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| All 7 v1 .py files in `cyrus2/` | `cyrus2/` exists but is empty | Copy files |
| `ruff check --fix .` applied | No ruff run yet | Run autofix |
| `ruff format .` applied | No formatting yet | Run formatter |
| `ruff check .` reports zero violations | N/A | Verify + manually fix remainders |
| `ruff format --check .` confirms formatted | N/A | Verify |
| Git diff shows only formatting changes | N/A | Review diff |

## Design Decisions

1. **Copy order doesn't matter** — all 7 files are independent modules with no cross-imports within `cyrus2/`. A single `cp` batch suffices.

2. **Ruff autofix before format** — `ruff check --fix` handles import sorting (I), unused imports (F401), pyupgrade (UP), and bugbear (B) fixes first. Then `ruff format` handles whitespace/line-length. This order is intentional: import changes can affect line lengths, so formatting comes last.

3. **E501 (line length) strategy** — The configured rule set includes `E` which contains E501. `ruff format` will reflow most long lines automatically (like Black). However, truly unsplittable tokens (long strings, regex patterns, URLs) may remain over 88 chars. Based on a scan of the v1 code:
   - `cyrus_brain.py` has ~35 long lines (regex patterns, f-strings)
   - `main.py` has ~30 long lines (complex f-strings, comments)
   - Other files have 0–3 long lines each

   **Approach**: After `ruff format`, run `ruff check .` and manually fix any remaining E501 violations by:
   - Extracting long strings into variables
   - Splitting f-strings across lines with parenthesized expressions
   - Wrapping long regex patterns with `re.compile()` multi-line strings

   If the count is large (>20 remaining), add `"E501"` to the `ignore` list in `pyproject.toml` with a comment explaining the formatter handles line length (this is ruff's own recommendation when using `ruff format`), and create a follow-up issue for manual line-length cleanup.

4. **No logic changes** — the acceptance criterion "git diff shows only formatting/import-ordering changes" means we must not alter any runtime behavior. If ruff's autofix suggests a change that alters logic (unlikely with the selected rule sets, but possible with UP rules on conditional imports), we skip that fix with a `# noqa` comment.

5. **Ruff installation** — ruff must be available. The builder should check `ruff --version` and install via `pip install ruff` if missing. This is a dev tool, not a runtime dependency.

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Verification Command |
|---|---|---|
| AC1 | All v1 .py files copied to `cyrus2/` | `ls cyrus2/*.py` — expect 7 files matching source names |
| AC2 | `ruff check --fix .` applied | Run the command; captured output shows fixes applied |
| AC3 | `ruff format .` applied | Run the command; captured output shows files reformatted |
| AC4 | `ruff check .` reports zero violations | Exit code 0, output "All checks passed" |
| AC5 | `ruff format --check .` confirms formatted | Exit code 0, output shows all files already formatted |
| AC6 | Git diff shows only formatting changes | `git diff cyrus2/` — review for logic changes (none expected) |

## Implementation Steps

### Step 1: Verify prerequisite (Issue 001)

```bash
cd /home/daniel/Projects/barf/cyrus
test -f cyrus2/pyproject.toml && echo "OK: pyproject.toml exists" || echo "BLOCKED: pyproject.toml missing"
```

If missing, the build cannot proceed — fail with a clear message.

### Step 2: Ensure ruff is available

```bash
ruff --version || pip install ruff
```

### Step 3: Copy all v1 Python files to `cyrus2/`

```bash
cp main.py cyrus2/
cp cyrus_voice.py cyrus2/
cp cyrus_brain.py cyrus2/
cp cyrus_server.py cyrus2/
cp cyrus_hook.py cyrus2/
cp probe_uia.py cyrus2/
cp test_permission_scan.py cyrus2/
```

**Verify:** `ls -la cyrus2/*.py` — expect exactly 7 files.

### Step 4: Run `ruff check --fix` on `cyrus2/`

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
ruff check --fix .
```

Capture output. Expected fix categories:
- **I001**: import sorting/grouping
- **F401**: unused imports removed
- **UP**: syntax modernized (e.g., `dict()` → `{}`, old-style type hints)
- **W**: whitespace warnings

Review output to confirm no logic-altering fixes.

### Step 5: Run `ruff format` on `cyrus2/`

```bash
ruff format .
```

Capture output — shows count of reformatted files.

### Step 6: Check for remaining violations

```bash
ruff check .
```

**If zero violations** → proceed to Step 8.

**If violations remain** → go to Step 7.

### Step 7: Resolve remaining violations

For each violation class:

- **E501 (line too long)**: Manually shorten lines by extracting variables, splitting strings, or using parenthesized line continuation. If >20 E501 violations remain after formatting, add `ignore = ["E501"]` to `[tool.ruff.lint]` in `pyproject.toml` (per ruff's recommendation when using ruff format) and note this in the commit message.
- **Other non-autofixable**: Fix manually. If a fix would change logic, add `# noqa: XXXX` with a comment explaining why.

Re-run `ruff check .` after each fix pass until zero violations.

### Step 8: Final verification

```bash
# All checks pass
ruff check .

# All files formatted
ruff format --check .

# Review diff for logic changes (should be formatting/import-ordering only)
cd /home/daniel/Projects/barf/cyrus
git diff cyrus2/ | head -200
```

Visually confirm the diff contains only:
- Import reordering
- Whitespace/indentation changes
- Line wrapping
- Syntax modernization (UP rules — still not logic changes)

## Risk Assessment

**Low-medium risk.** The copy step is trivial. The ruff autofix + format step is mechanical. The main risk is non-autofixable E501 violations in `cyrus_brain.py` and `main.py` (~65 long lines combined), which may require manual intervention or an E501 ignore rule. No logic changes should result from the selected rule sets (E, F, W, I, UP, B).

## Estimated Scope

- 7 files copied
- ~4,600 lines of Python reformatted
- Primary effort: resolving any remaining E501 violations after formatting
