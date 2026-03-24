# Cyrus 2.0 Sprint Issues — Sprint 0 & Sprint 1

---

# Issue 001: Create pyproject.toml with project metadata and ruff config

## Sprint
Sprint 0 — Tooling & Foundation

## Priority
High

## References
- [Doc 17 — Ruff Linting & Formatting](./docs/17-ruff-linting.md) (Section 1)
- [Doc 12 — Code Audit](./docs/12-code-audit.md) (L4: No Modern Python Packaging)

## Description
Create a `pyproject.toml` file at the project root with modern Python packaging metadata and Ruff linting/formatting configuration. This establishes the project as a proper Python package and configures code quality standards for the entire team.

## Blocked By
- None

## Acceptance Criteria
- [ ] File `/home/daniel/Projects/barf/cyrus/pyproject.toml` exists
- [ ] Contains `[project]` section with name, version, description, and authors
- [ ] Contains `[tool.ruff]` configuration with target-version = "py310", line-length = 88
- [ ] Ruff lint rules include at minimum: E, F, W, I, UP, B (as per doc 17)
- [ ] Project excludes `.venv` and `cyrus-companion` directories
- [ ] Running `ruff check --version` returns success (confirms ruff will recognize config)

## Implementation Steps

1. Open a text editor and create the file at `/home/daniel/Projects/barf/cyrus/pyproject.toml`

2. Add the following content exactly as shown:

```toml
[project]
name = "cyrus"
version = "2.0.0"
description = "Voice interface for Claude Code via Whisper + Silero VAD + Edge TTS"
authors = [
    { name = "Daniel", email = "daniel@example.com" },
]
requires-python = ">=3.10"
readme = "README.md"
license = { text = "MIT" }

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.ruff]
target-version = "py310"
line-length = 88
exclude = [".venv", "cyrus-companion"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]

[tool.ruff.format]
# Uses project-wide defaults
```

3. Save the file

4. Verify it exists:
```bash
ls -la /home/daniel/Projects/barf/cyrus/pyproject.toml
```

5. Verify syntax by trying to read it:
```bash
cat /home/daniel/Projects/barf/cyrus/pyproject.toml
```

## Files to Create/Modify
- **Create:** `/home/daniel/Projects/barf/cyrus/pyproject.toml` (new file with project metadata and ruff config)

## Testing
Run these commands in `/home/daniel/Projects/barf/cyrus/`:
```bash
# Verify file exists
test -f pyproject.toml && echo "OK: pyproject.toml exists"

# Verify syntax by parsing it (Python)
python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))" && echo "OK: TOML syntax valid"

# Verify ruff sees it
ruff check . --version && echo "OK: ruff recognizes config"
```

---

# Issue 002: Run ruff auto-fix and format on all Python files

## Sprint
Sprint 0 — Tooling & Foundation

## Priority
High

## References
- [Doc 17 — Ruff Linting & Formatting](./docs/17-ruff-linting.md) (Sections 3–4)

## Description
Install Ruff and run both auto-fix and format passes on all Python files. This standardizes code style across the codebase and catches automatically-fixable issues (unused imports, line length, indentation). The changes prepare the codebase for Issue 005 (shared utilities extraction).

## Blocked By
- Issue 001 (pyproject.toml must exist for ruff to apply consistent config)

## Acceptance Criteria
- [ ] Ruff is installed in the current Python environment
- [ ] All Python files in `/home/daniel/Projects/barf/cyrus/` have been processed by `ruff check --fix`
- [ ] All Python files have been processed by `ruff format`
- [ ] Running `ruff check .` returns exit code 0 (zero violations)
- [ ] Running `ruff format --check .` returns exit code 0 (all files already formatted)
- [ ] No merge conflicts in git (changes are to formatting only)

## Implementation Steps

1. Install Ruff:
```bash
pip install ruff
```

Verify installation:
```bash
ruff --version
```

2. Navigate to project root:
```bash
cd /home/daniel/Projects/barf/cyrus
```

3. Run auto-fix (fixes issues like unused imports, line length):
```bash
ruff check --fix .
```

Expected output: Shows files modified, lists rule violations fixed (E, F, W, I, UP, B rules).

4. Run formatter (standardizes whitespace, line breaks, quote style):
```bash
ruff format .
```

Expected output: Shows files formatted or indicates all files already formatted.

5. Run verification checks:
```bash
ruff check .
```

This should return exit code 0 and print "All checks passed!" or similar. If violations remain, they are either:
- Violations outside the selected rule set (ignore — we only enforce E, F, W, I, UP, B)
- Violations that cannot be auto-fixed (rare; document and handle case-by-case)

6. Verify formatting consistency:
```bash
ruff format --check .
```

Should return exit code 0, indicating all files are formatted.

## Files to Create/Modify
- **Modify:** All `.py` files in `/home/daniel/Projects/barf/cyrus/`:
  - `main.py`
  - `cyrus_brain.py`
  - `cyrus_voice.py`
  - `cyrus_server.py`
  - `cyrus_hook.py`
  - `probe_uia.py`
  - `test_permission_scan.py`

(Formatting changes only — logic unchanged)

## Testing
```bash
cd /home/daniel/Projects/barf/cyrus

# Verify no lint violations
ruff check . && echo "✓ No lint violations"

# Verify files are formatted
ruff format --check . && echo "✓ All files properly formatted"

# Quick sanity check — run one file to ensure no syntax errors
python -m py_compile main.py cyrus_brain.py cyrus_voice.py && echo "✓ All files compile"
```

---

# Issue 003: Create requirements-dev.txt with dev dependencies

## Sprint
Sprint 0 — Tooling & Foundation

## Priority
High

## References
- [Doc 17 — Ruff Linting & Formatting](./docs/17-ruff-linting.md) (Section 2)
- [Doc 12 — Code Audit](./docs/12-code-audit.md) (H6: No Test Suite)

## Description
Create a `requirements-dev.txt` file listing all development-only dependencies (linting, testing, documentation tools). This separates development tooling from production dependencies and makes it clear what's needed to contribute.

## Blocked By
- None (can be done in parallel with Issue 001–002)

## Acceptance Criteria
- [ ] File `/home/daniel/Projects/barf/cyrus/requirements-dev.txt` exists
- [ ] Contains at least: ruff, pytest
- [ ] No duplicate entries
- [ ] File is readable by `pip install -r`

## Implementation Steps

1. Create the file `/home/daniel/Projects/barf/cyrus/requirements-dev.txt` with the following content:

```
ruff
pytest
```

2. Save the file

3. Verify it can be parsed by pip:
```bash
pip install --dry-run -r /home/daniel/Projects/barf/cyrus/requirements-dev.txt
```

Should output what packages would be installed without actually installing them.

## Files to Create/Modify
- **Create:** `/home/daniel/Projects/barf/cyrus/requirements-dev.txt` (new file)

## Testing
```bash
# Verify file exists
test -f /home/daniel/Projects/barf/cyrus/requirements-dev.txt && echo "OK"

# Verify contents are readable
cat /home/daniel/Projects/barf/cyrus/requirements-dev.txt

# Verify pip can parse it (dry-run)
pip install --dry-run -r /home/daniel/Projects/barf/cyrus/requirements-dev.txt 2>&1 | grep -q "Would install" && echo "OK: pip can parse file"
```

---

# Issue 004: Pin all production dependencies to exact versions

## Sprint
Sprint 0 — Tooling & Foundation

## Priority
High

## References
- [Doc 12 — Code Audit](./docs/12-code-audit.md) (H5: All Dependencies Unpinned)
- [Doc 15 — Feature Recommendations](./docs/15-recommendations.md) (#8: Pin dependencies)

## Description
Update all production requirements files (`requirements.txt`, `requirements-brain.txt`, `requirements-voice.txt`) to pin exact versions. Unpinned dependencies (especially torch, onnxruntime-gpu, faster-whisper) can break builds across environments. Exact pinning ensures reproducible installations.

## Blocked By
- None

## Acceptance Criteria
- [ ] All dependencies in `requirements.txt` have exact version pins (e.g., `torch==2.1.0`, not `torch>=2.0`)
- [ ] All dependencies in `requirements-brain.txt` have exact version pins
- [ ] All dependencies in `requirements-voice.txt` have exact version pins
- [ ] Each file contains only production dependencies (no pytest, ruff, etc.)
- [ ] All pinned versions work together (no conflicts reported by `pip check`)
- [ ] Running `pip install -r [file]` succeeds without warnings about incompatible versions

## Implementation Steps

1. First, capture the currently installed versions. In your active Python environment with Cyrus dependencies installed, run:
```bash
pip freeze > /tmp/pinned.txt
```

2. Examine the current unpinned requirements:
```bash
cat /home/daniel/Projects/barf/cyrus/requirements.txt
cat /home/daniel/Projects/barf/cyrus/requirements-brain.txt
cat /home/daniel/Projects/barf/cyrus/requirements-voice.txt
```

3. For each file, replace each line with the pinned version from `pip freeze`. For example:
   - **Before:** `pyautogui`
   - **After:** `pyautogui==1.0.9`

4. Read `/tmp/pinned.txt` to find exact versions:
```bash
grep -E "^(pyautogui|pyperclip|pygetwindow|uiautomation|comtypes|python-dotenv|websockets|numpy|sounddevice|keyboard|pygame|torch|silero-vad|faster-whisper|onnxruntime-gpu)" /tmp/pinned.txt
```

5. Update `/home/daniel/Projects/barf/cyrus/requirements.txt`:

```
pyautogui==1.0.9
pyperclip==1.8.2
pygetwindow==0.10
uiautomation==2.3
comtypes==1.1.14
python-dotenv==1.0.0
websockets==12.0
```

(Use exact versions from your environment; these are examples)

6. Update `/home/daniel/Projects/barf/cyrus/requirements-brain.txt`:

```
pyautogui==1.0.9
pyperclip==1.8.2
pygetwindow==0.10
uiautomation==2.3
comtypes==1.1.14
python-dotenv==1.0.0
websockets==12.0
```

7. Update `/home/daniel/Projects/barf/cyrus/requirements-voice.txt`:

```
numpy==1.24.3
sounddevice==0.4.6
keyboard==0.13.5
pygame==2.2.0
torch==2.1.0
silero-vad==5.0
faster-whisper==0.10.0
onnxruntime-gpu==1.17.0
```

(Substitute with versions from your environment)

8. Verify no conflicts:
```bash
pip check
```

Should output "No broken requirements found." If conflicts exist, adjust versions until compatible.

## Files to Create/Modify
- **Modify:** `/home/daniel/Projects/barf/cyrus/requirements.txt` (pin all versions)
- **Modify:** `/home/daniel/Projects/barf/cyrus/requirements-brain.txt` (pin all versions)
- **Modify:** `/home/daniel/Projects/barf/cyrus/requirements-voice.txt` (pin all versions)

## Testing
```bash
# Check for dependency conflicts
pip check && echo "OK: No conflicts"

# Verify format is correct (should install without error)
pip install --dry-run -r /home/daniel/Projects/barf/cyrus/requirements.txt 2>&1 | tail -5

# Verify each file is valid
for f in requirements.txt requirements-brain.txt requirements-voice.txt; do
  python -c "import re; [re.match(r'^[a-zA-Z0-9\-_]+==[0-9.]+$', line.strip()) or (print(f'Invalid: {line}') and exit(1)) for line in open('/home/daniel/Projects/barf/cyrus/' + f) if line.strip() and not line.startswith('#')]"
  echo "OK: $f format valid"
done
```

---

# Issue 005: Extract shared utilities into cyrus_common.py

## Sprint
Sprint 1 — Core Refactor

## Priority
Critical

## References
- [Doc 12 — Code Audit](./docs/12-code-audit.md) (C3: 90% Code Duplication)
- [Doc 15 — Feature Recommendations](./docs/15-recommendations.md) (#1: Extract cyrus_common.py)

## Description
Extract ~2,000 lines of duplicated code from `main.py` and `cyrus_brain.py` into a shared `cyrus_common.py` module. This eliminates the primary source of maintenance burden, prevents bugs from being fixed in one place but not the other, and makes subsequent refactors (Issues 006–008) single-file changes instead of multi-file.

This is the **highest-impact issue**. All other refactoring work depends on this one.

## Blocked By
- Issue 001 (pyproject.toml)
- Issue 002 (ruff formatting)

## Acceptance Criteria
- [ ] File `/home/daniel/Projects/barf/cyrus/cyrus_common.py` exists with 100+ lines
- [ ] Every function/class in the extraction table below is present and functional
- [ ] `main.py` imports the extracted code from `cyrus_common` and removes duplicates
- [ ] `cyrus_brain.py` imports the extracted code from `cyrus_common` and removes duplicates
- [ ] Both `main.py` and `cyrus_brain.py` still have all their original functionality (no missing imports)
- [ ] Running `python main.py --help` succeeds
- [ ] Running `python cyrus_brain.py --help` succeeds
- [ ] No circular imports
- [ ] `ruff check .` finds no violations in the new file

## Implementation Steps

### Step 1: Create cyrus_common.py with shared utilities

Create file `/home/daniel/Projects/barf/cyrus/cyrus_common.py`. This file will contain the extracted functions and constants.

**Extraction table** — Copy these functions/classes from their source to `cyrus_common.py`:

| Function/Constant | main.py lines | cyrus_brain.py lines | Destination in cyrus_common.py | Notes |
|---|---|---|---|---|
| `_extract_project()` | 146–150 | 113–116 | Keep cyrus_brain.py's version (has docstring) | Verify both are identical or near-identical before choosing |
| `_make_alias()` | 153–155 | 119–120 | Keep cyrus_brain.py's version | Both identical |
| `_resolve_project()` | 158–166 | 123–137 | Keep cyrus_brain.py's version (more robust, handles partial matching) | cyrus_brain.py's version sorts candidates by length |
| `_vs_code_windows()` | 169–180 | 140–150 | Keep main.py's version (no extra comments) | Both appear identical |
| `_sanitize_for_speech()` | (not in main.py) | 153–164 | Copy from cyrus_brain.py | Only in cyrus_brain.py; needed by clean_for_speech |
| `clean_for_speech()` | 1311–1325 | 167–183 | Keep cyrus_brain.py's version (calls _sanitize_for_speech) | cyrus_brain.py version is complete |
| `_FILLER_RE` | 1144 | 186–189 | Copy from cyrus_brain.py | Identical regex, copy with comment |
| `_strip_fillers()` | 1150–1156 | 192–197 | Keep cyrus_brain.py's version | Both identical |
| `_ANSWER_RE` | 275–287 | 276–287 | Keep main.py's version (more readable formatting) | Both identical |
| `_is_answer_request()` | 289–291 | 286–287 | Keep either (both identical) | Copy one version |
| `_fast_command()` | 322–371 | 290–328 | Keep main.py's version (lines 322–371 if it includes the full handler logic) | Verify both versions have same handlers |
| `play_chime()` | 207–218 | 263–271 | Keep main.py's version (pure function, no event loop dependency) | cyrus_brain.py version takes optional loop param; for common, use pure version |
| `play_listen_chime()` | 221–238 | 269–271 | Keep main.py's version (pure function) | Same reasoning; cyrus_brain wraps it |
| `_HALLUCINATIONS` | 1129 | 96 | Copy from cyrus_voice.py if needed | Mentioned in audit; check if in both files |
| `ChatWatcher` class | ~460–700 | ~400–640 | Extract to cyrus_common.py | Likely identical; may need diff to confirm |
| `PermissionWatcher` class | ~730–960 | ~720–960 | Extract to cyrus_common.py | Likely identical |
| `SessionManager` class | ~970–1050 | ~970–1110 | Extract to cyrus_common.py | Likely identical |

### Step 2: Check for exact line numbers and content

Before copying, verify actual line numbers in both files:

```bash
# Find _extract_project in main.py
grep -n "def _extract_project" /home/daniel/Projects/barf/cyrus/main.py

# Find _extract_project in cyrus_brain.py
grep -n "def _extract_project" /home/daniel/Projects/barf/cyrus/cyrus_brain.py

# (Repeat for each function)
```

If line numbers differ from the audit, use the `grep` output as the source of truth.

### Step 3: Build cyrus_common.py skeleton

Start with the imports needed by the extracted functions:

```python
"""
cyrus_common.py — Shared utilities between main.py and cyrus_brain.py

Contains pure functions and classes used by both entry points:
- Project name extraction and aliasing
- Speech cleaning and filler stripping
- Chime playback
- Command fast-path routing
- ChatWatcher, PermissionWatcher, SessionManager classes
"""

import re
import json
import threading
import time
from collections import deque

import numpy as np
import pyautogui
import pyperclip
import pygetwindow as gw

# ── Configuration ──────────────────────────────────────────────────────────────

MAX_SPEECH_WORDS = 200  # (verify this is actually defined in main.py or cyrus_brain.py)
VSCODE_TITLE = "Visual Studio Code"

# ── Project extraction ─────────────────────────────────────────────────────────

def _extract_project(title: str) -> str:
    """'main.py - cyrus - Visual Studio Code'  →  'cyrus'"""
    # Copy from cyrus_brain.py lines 113–116 (or main.py 146–150, whichever)
    ...

# (Add all other functions/classes in order)
```

### Step 4: Copy function/class bodies exactly

For each item in the extraction table:
1. Read the exact lines from the source file
2. Copy the entire function/class (including docstring, decorators, etc.)
3. Paste into `cyrus_common.py`
4. Preserve indentation exactly

Example:
```python
def _make_alias(proj: str) -> str:
    """'my-web-app' → 'my web app',  'backend_service' → 'backend service'"""
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", proj.lower())).strip()
```

### Step 5: Update imports in cyrus_brain.py

After creating `cyrus_common.py`, update the imports in `/home/daniel/Projects/barf/cyrus/cyrus_brain.py`:

Add at the top (after existing imports, before local code):
```python
from cyrus_common import (
    _extract_project,
    _make_alias,
    _resolve_project,
    _vs_code_windows,
    _sanitize_for_speech,
    clean_for_speech,
    _FILLER_RE,
    _strip_fillers,
    _ANSWER_RE,
    _is_answer_request,
    _fast_command,
    play_chime,
    play_listen_chime,
    ChatWatcher,
    PermissionWatcher,
    SessionManager,
)
```

Then **delete** the original definitions of these functions/classes from `cyrus_brain.py` (keep only the imports).

### Step 6: Update imports in main.py

Repeat Step 5 for `/home/daniel/Projects/barf/cyrus/main.py`:

```python
from cyrus_common import (
    _extract_project,
    _make_alias,
    _resolve_project,
    _vs_code_windows,
    _sanitize_for_speech,
    clean_for_speech,
    _FILLER_RE,
    _strip_fillers,
    _ANSWER_RE,
    _is_answer_request,
    _fast_command,
    play_chime,
    play_listen_chime,
    ChatWatcher,
    PermissionWatcher,
    SessionManager,
)
```

Then **delete** the duplicate definitions from `main.py`.

### Step 7: Verify no imports are missing

Run syntax checks on all three files:
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_common.py
python -m py_compile /home/daniel/Projects/barf/cyrus/main.py
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

Each should return exit code 0 (no syntax errors).

### Step 8: Check for circular imports

Try importing both files:
```bash
cd /home/daniel/Projects/barf/cyrus
python -c "import cyrus_common; print('cyrus_common OK')"
python -c "import cyrus_brain; print('cyrus_brain OK')"  # may fail if it tries to initialize
python -c "import main; print('main OK')"  # may fail if it tries to initialize
```

If there are circular import issues, review the imports in each file. `cyrus_common.py` should **not** import from `main.py` or `cyrus_brain.py`.

### Step 9: Run linter on new file

```bash
ruff check /home/daniel/Projects/barf/cyrus/cyrus_common.py
ruff format /home/daniel/Projects/barf/cyrus/cyrus_common.py
```

Should produce no errors.

## Files to Create/Modify
- **Create:** `/home/daniel/Projects/barf/cyrus/cyrus_common.py` (150–300 lines of extracted code)
- **Modify:** `/home/daniel/Projects/barf/cyrus/cyrus_brain.py` (remove duplicate definitions, add import from cyrus_common)
- **Modify:** `/home/daniel/Projects/barf/cyrus/main.py` (remove duplicate definitions, add import from cyrus_common)

## Testing

1. **Syntax check:**
```bash
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_common.py
python -m py_compile /home/daniel/Projects/barf/cyrus/main.py
python -m py_compile /home/daniel/Projects/barf/cyrus/cyrus_brain.py
echo "All files compile"
```

2. **Linting:**
```bash
cd /home/daniel/Projects/barf/cyrus
ruff check . && echo "No lint errors"
```

3. **Functionality:**
```bash
# Test _extract_project
python -c "from cyrus_common import _extract_project; assert _extract_project('main.py - cyrus - Visual Studio Code') == 'cyrus'; print('OK')"

# Test _fast_command
python -c "from cyrus_common import _fast_command; assert _fast_command('pause') is not None; print('OK')"

# Test play_chime (should not error even if pygame unavailable)
python -c "from cyrus_common import play_chime; play_chime(); print('OK')"
```

4. **Verify no duplication:**
```bash
# Count occurrences of _extract_project definition (should be 1 in common + 0 in main/brain)
echo "=== _extract_project definitions ==="
grep -n "^def _extract_project" /home/daniel/Projects/barf/cyrus/*.py

# Should output only: cyrus_common.py:XX:def _extract_project
```

---

# Issue 006: Deprecate main.py monolith — update to import from cyrus_common.py and add deprecation warning

## Sprint
Sprint 1 — Core Refactor

## Priority
High

## References
- [Doc 15 — Feature Recommendations](./docs/15-recommendations.md) (#2: Deprecate main.py monolith)
- [Doc 12 — Code Audit](./docs/12-code-audit.md) (C3: Code Duplication)

## Description
After Issue 005 extraction, `main.py` is a monolithic all-in-one entry point that duplicates the split architecture of `cyrus_brain.py` + `cyrus_voice.py`. This issue adds a deprecation warning and transitions documentation to recommend the split mode. This prepares for eventually dropping main.py entirely (reducing codebase size by ~20%).

## Blocked By
- Issue 005 (cyrus_common.py extraction must be complete)

## Acceptance Criteria
- [ ] `main.py` imports all shared utilities from `cyrus_common`
- [ ] `main.py` has a deprecation warning printed on startup (visible in console)
- [ ] Warning clearly states "main.py is deprecated; use cyrus_brain.py + cyrus_voice.py instead"
- [ ] Deprecation message suggests reading docs/15-recommendations.md for migration
- [ ] `main.py` still starts and functions correctly despite warning
- [ ] README.md or docs explicitly recommend split mode over main.py
- [ ] Running `python main.py --help` shows deprecation warning before help

## Implementation Steps

### Step 1: Verify Issue 005 is complete

Confirm that `/home/daniel/Projects/barf/cyrus/cyrus_common.py` exists and contains all extracted functions:
```bash
test -f /home/daniel/Projects/barf/cyrus/cyrus_common.py && echo "OK"
```

### Step 2: Add imports from cyrus_common to main.py

At the top of `/home/daniel/Projects/barf/cyrus/main.py`, ensure this import block exists (added in Issue 005):

```python
from cyrus_common import (
    _extract_project,
    _make_alias,
    _resolve_project,
    _vs_code_windows,
    clean_for_speech,
    _FILLER_RE,
    _strip_fillers,
    _ANSWER_RE,
    _is_answer_request,
    _fast_command,
    play_chime,
    play_listen_chime,
    ChatWatcher,
    PermissionWatcher,
    SessionManager,
)
```

Verify the imports are there:
```bash
grep -n "from cyrus_common import" /home/daniel/Projects/barf/cyrus/main.py
```

### Step 3: Add deprecation warning to main() function

Locate the `main()` function definition in `/home/daniel/Projects/barf/cyrus/main.py` (around line 1435 per the audit).

At the **very start** of the `main()` function, add:

```python
def main():
    """Main entry point for Cyrus mono mode (DEPRECATED)."""
    import sys
    print(
        "\n⚠️  DEPRECATION WARNING ⚠️\n"
        "main.py is deprecated and will be removed in Cyrus 3.0.\n"
        "Use cyrus_brain.py + cyrus_voice.py (split mode) instead.\n"
        "See docs/15-recommendations.md for migration guide.\n"
    )

    # Rest of main() continues below...
```

(Adjust the print statement if you want a different message, but keep it visible and clear.)

### Step 4: Add warning to help text

If `main.py` has an argument parser (check for `argparse.ArgumentParser()`), update the description:

```python
parser = argparse.ArgumentParser(
    description="Cyrus — Voice interface for Claude Code (DEPRECATED — use split mode instead)"
)
```

### Step 5: Update README.md

Open `/home/daniel/Projects/barf/cyrus/README.md` and add a note about the deprecation. Example:

```markdown
## Installation & Usage

**Recommended:** Use split mode (cyrus_brain.py + cyrus_voice.py)

```bash
python cyrus_brain.py &     # starts brain on port 8766
python cyrus_voice.py &     # starts voice layer
```

### Deprecated

main.py is a monolithic all-in-one mode and is deprecated. It will be removed in Cyrus 3.0. Use split mode instead.
```

### Step 6: Verify no side effects

Ensure `main.py` still works by testing it does not crash on startup:

```bash
cd /home/daniel/Projects/barf/cyrus
timeout 5 python main.py --help 2>&1 | head -20
```

Should print the deprecation warning followed by help output. Exit code 0.

## Files to Create/Modify
- **Modify:** `/home/daniel/Projects/barf/cyrus/main.py` (add deprecation warning to main() function)
- **Modify:** `/home/daniel/Projects/barf/cyrus/README.md` (document deprecation and recommend split mode)

## Testing

1. **Verify deprecation warning appears:**
```bash
cd /home/daniel/Projects/barf/cyrus
python main.py --help 2>&1 | grep -i "deprecation"
echo $?  # should be 0 (grep found the string)
```

2. **Verify help still works:**
```bash
python main.py --help 2>&1 | tail -10  # should show argparse help
```

3. **Verify README mentions deprecation:**
```bash
grep -i "deprecated" /home/daniel/Projects/barf/cyrus/README.md && echo "OK"
```

---

# Issue 007: Break up _execute_cyrus_command() into dispatch table

## Sprint
Sprint 1 — Core Refactor

## Priority
Critical

## References
- [Doc 12 — Code Audit](./docs/12-code-audit.md) (C1: God Functions)

## Description
The `_execute_cyrus_command()` function in both `main.py` (lines 374–451) and `cyrus_brain.py` (lines 331–398) are god functions with deeply nested if/elif chains handling 6+ command types. Replace with a dispatch table mapping command names to handler functions, making each handler small, testable, and focused. This makes the code readable and enables unit tests.

## Blocked By
- Issue 005 (cyrus_common.py extraction)

## Acceptance Criteria
- [ ] A `_COMMAND_DISPATCH` dict exists mapping command names to handler functions
- [ ] Each handler function is < 20 lines (small, focused, testable)
- [ ] Original 40–80 line `_execute_cyrus_command()` shrinks to < 15 lines
- [ ] All command types handled by dispatch table (switch_project, unlock, which_project, pause, last_message, etc.)
- [ ] Unknown commands return appropriate error dict instead of silently failing
- [ ] `ruff check` finds no violations in updated code
- [ ] Both `main.py` and `cyrus_brain.py` use the same dispatch table (from `cyrus_common.py` if possible, or identical in both)

## Implementation Steps

### Step 1: Identify all command types

Read the `_execute_cyrus_command()` function in `/home/daniel/Projects/barf/cyrus/cyrus_brain.py` (lines 331–398 per audit) and list all command types it handles:

```bash
grep -n "if.*==" /home/daniel/Projects/barf/cyrus/cyrus_brain.py | grep -A 5 "def _execute_cyrus_command" | head -20
```

Expected commands (typical):
- `switch_project` — lock routing to a specific project
- `unlock` — unlock project lock, follow window focus
- `which_project` — speak which project is active
- `pause` — toggle listening
- `last_message` — replay last response

### Step 2: Extract handler functions

For each command type, extract the if/elif block into its own function. Example:

**Before (in _execute_cyrus_command):**
```python
if cmd_name == "switch_project":
    proj_name = cmd.get("project")
    if proj_name:
        # ... 10 lines of logic ...
        return {"action": "command", "message": f"Switched to {proj_name}"}
    else:
        return {"action": "error", "message": "No project specified"}
```

**After (new function):**
```python
def _handle_switch_project(cmd: dict, context: dict) -> dict:
    """Lock routing to the specified project."""
    proj_name = cmd.get("project")
    if proj_name:
        # ... logic ...
        return {"action": "command", "message": f"Switched to {proj_name}"}
    else:
        return {"action": "error", "message": "No project specified"}
```

### Step 3: Create dispatch table

Add this near the top of the file (after imports, before main logic):

```python
def _handle_switch_project(cmd: dict, context: dict) -> dict:
    """Lock routing to a specific project."""
    # implementation
    pass

def _handle_unlock(cmd: dict, context: dict) -> dict:
    """Unlock project lock, follow window focus."""
    # implementation
    pass

def _handle_which_project(cmd: dict, context: dict) -> dict:
    """Speak the currently active project."""
    # implementation
    pass

def _handle_pause(cmd: dict, context: dict) -> dict:
    """Toggle listening on/off."""
    # implementation
    pass

def _handle_last_message(cmd: dict, context: dict) -> dict:
    """Replay the last response."""
    # implementation
    pass

# (Add more handlers as needed)

_COMMAND_DISPATCH = {
    "switch_project": _handle_switch_project,
    "unlock": _handle_unlock,
    "which_project": _handle_which_project,
    "pause": _handle_pause,
    "last_message": _handle_last_message,
    # ... more commands ...
}
```

### Step 4: Rewrite _execute_cyrus_command()

Replace the entire if/elif chain with:

```python
def _execute_cyrus_command(cmd: dict, context: dict) -> dict:
    """
    Route a command to the appropriate handler via dispatch table.

    Args:
        cmd: Command dict with "type" and optional parameters.
        context: Context dict with session_mgr, loop, etc.

    Returns:
        Decision dict with routing action or error message.
    """
    cmd_name = cmd.get("type")
    if not cmd_name:
        return {"action": "error", "message": "No command type specified"}

    handler = _COMMAND_DISPATCH.get(cmd_name)
    if handler is None:
        return {"action": "error", "message": f"Unknown command: {cmd_name}"}

    try:
        return handler(cmd, context)
    except Exception as e:
        return {"action": "error", "message": f"Command failed: {e}"}
```

This is much shorter and clearer.

### Step 5: Extract to cyrus_common.py (if appropriate)

If the handlers are pure functions (no dependency on main.py or cyrus_brain.py specific state), consider moving the dispatch table and handlers to `cyrus_common.py`. If they depend on local state, keep them in the file but import and use the same dispatch pattern in both places.

### Step 6: Test each handler

For each handler, write a simple test:

```bash
python -c "
from cyrus_brain import _handle_switch_project
result = _handle_switch_project({'project': 'myapp'}, {})
print(result)
assert result.get('action') == 'command', 'Expected command action'
print('OK')
"
```

### Step 7: Verify both main.py and cyrus_brain.py are updated

Check that both files now use the dispatch table:

```bash
grep -n "_COMMAND_DISPATCH" /home/daniel/Projects/barf/cyrus/main.py
grep -n "_COMMAND_DISPATCH" /home/daniel/Projects/barf/cyrus/cyrus_brain.py
```

Both should reference the same dispatch table (either locally or imported from common).

## Files to Create/Modify
- **Modify:** `/home/daniel/Projects/barf/cyrus/cyrus_brain.py` (replace _execute_cyrus_command with dispatch table)
- **Modify:** `/home/daniel/Projects/barf/cyrus/main.py` (replace _execute_cyrus_command with dispatch table, or import from common)

## Testing

1. **Check that _execute_cyrus_command is < 15 lines:**
```bash
grep -n "^def _execute_cyrus_command" /home/daniel/Projects/barf/cyrus/cyrus_brain.py
# Count lines until next "def" or end of function
# Should be < 15 lines total
```

2. **Test dispatch table exists:**
```bash
python -c "from cyrus_brain import _COMMAND_DISPATCH; print(f'Handlers: {list(_COMMAND_DISPATCH.keys())}')"
```

3. **Test a handler works:**
```bash
python -c "
from cyrus_brain import _execute_cyrus_command
result = _execute_cyrus_command({'type': 'pause'}, {})
print('Result:', result)
assert 'action' in result, 'Missing action field'
print('OK')
"
```

4. **Verify no ruff errors:**
```bash
ruff check /home/daniel/Projects/barf/cyrus/cyrus_brain.py /home/daniel/Projects/barf/cyrus/main.py && echo "OK"
```

---

# Issue 008: Break up main() functions into smaller subsystem initializers

## Sprint
Sprint 1 — Core Refactor

## Priority
Critical

## References
- [Doc 12 — Code Audit](./docs/12-code-audit.md) (C2: Massive main() Functions)

## Description
The `main()` functions in both `main.py` (lines 1435–1755, 320 lines) and `cyrus_brain.py` (lines 1416–1549, 133 lines) combine routing, permission handling, initialization, and loop setup in one place. Extract initialization of major subsystems (VAD, TTS, routing loop, permission handling) into separate functions. This makes main() a thin orchestrator, improves readability, and allows subsystems to be tested/reused independently.

## Blocked By
- Issue 005 (cyrus_common.py extraction)
- Issue 007 (_execute_cyrus_command dispatch table)

## Acceptance Criteria
- [ ] `main()` function in both files is < 50 lines (down from 320 in main.py, 133 in cyrus_brain.py)
- [ ] At least 3 subsystem initializer functions exist (e.g., `_init_vad()`, `_init_tts()`, `_init_routing_loop()`)
- [ ] Each initializer is < 30 lines and does one thing (initialize or start one subsystem)
- [ ] `main()` calls initializers in sequence and returns control to asyncio/event loop
- [ ] No logic is lost — both files still have all original functionality
- [ ] `ruff check` finds no violations
- [ ] Running the file with `--help` works

## Implementation Steps

### Step 1: Identify subsystems in main()

Read the current `main()` function in `/home/daniel/Projects/barf/cyrus/cyrus_brain.py` (lines 1416–1549) and identify major initialization blocks:

```bash
sed -n '1416,1549p' /home/daniel/Projects/barf/cyrus/cyrus_brain.py | grep -E "(def |for |while |asyncio|threading|vad|tts|session)" | head -20
```

Expected subsystems (typical):
1. **Argument parsing** — argparse setup
2. **Session manager** — SessionManager init
3. **Routing loop** — spawn asyncio loop or thread
4. **Event handlers** — keyboard/voice event setup
5. **Server startup** — TCP socket binding

### Step 2: Extract argument parsing

Create a function that sets up and parses arguments:

```python
def _parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Cyrus Brain...")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8766, type=int)
    # ... other args ...
    return parser.parse_args()
```

Replace the inline `parser = ArgumentParser(...)` code in main() with a call to this function.

### Step 3: Extract session manager initialization

```python
def _init_session_manager(loop):
    """Create and start the SessionManager."""
    session_mgr = SessionManager(multi_session=True)
    asyncio.run_coroutine_threadsafe(session_mgr.load_aliases(), loop)
    return session_mgr
```

### Step 4: Extract routing loop initialization

```python
def _init_routing_loop():
    """Start the asyncio event loop in a background thread."""
    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return loop
```

### Step 5: Extract server/listener initialization

```python
def _init_voice_listener(loop, host, port):
    """Start the TCP server listening for voice connections."""
    async def voice_server():
        server = await asyncio.start_server(
            _handle_voice_connection,
            host=host,
            port=port
        )
        # ...

    asyncio.run_coroutine_threadsafe(voice_server(), loop)
```

### Step 6: Rewrite main()

Replace the monolithic main with:

```python
def main():
    """Orchestrate subsystem startup and run the routing loop."""
    args = _parse_args()
    loop = _init_routing_loop()
    session_mgr = _init_session_manager(loop)
    _init_voice_listener(loop, args.host, args.port)
    _init_permission_watcher(loop)
    _init_active_tracker(loop, session_mgr)

    print("[Brain] All subsystems initialized. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Brain] Shutting down...")
        loop.call_soon_threadsafe(loop.stop)
```

### Step 7: Verify subsystem order

Ensure initializers are called in the correct order (dependencies first). For example:
1. Parse args
2. Start asyncio loop (other subsystems need it)
3. Start session manager
4. Start server (listens for connections)
5. Start watchers (depend on session manager)

### Step 8: Extract to common (if applicable)

If initializers are reusable between main.py and cyrus_brain.py, move them to `cyrus_common.py`.

### Step 9: Test each subsystem separately (future)

This refactor makes it possible to test each subsystem in isolation:

```bash
python -c "
from cyrus_brain import _init_session_manager
import asyncio
loop = asyncio.new_event_loop()
mgr = _init_session_manager(loop)
print('SessionManager initialized:', mgr)
"
```

## Files to Create/Modify
- **Modify:** `/home/daniel/Projects/barf/cyrus/cyrus_brain.py` (extract main() into subsystem initializers)
- **Modify:** `/home/daniel/Projects/barf/cyrus/main.py` (extract main() into subsystem initializers)

## Testing

1. **Verify main() is < 50 lines:**
```bash
grep -n "^def main" /home/daniel/Projects/barf/cyrus/cyrus_brain.py
# Count lines until next "def" or end of file
# Should be < 50 lines
```

2. **Test subsystem initializers are created:**
```bash
python -c "
from cyrus_brain import _parse_args, _init_routing_loop
print('_parse_args:', _parse_args)
print('_init_routing_loop:', _init_routing_loop)
"
```

3. **Test main() can start (with timeout to avoid blocking):**
```bash
cd /home/daniel/Projects/barf/cyrus
timeout 3 python cyrus_brain.py 2>&1 | head -10
# Should start and print initialization messages before timeout
```

4. **Verify no ruff errors:**
```bash
ruff check /home/daniel/Projects/barf/cyrus/cyrus_brain.py /home/daniel/Projects/barf/cyrus/main.py && echo "OK"
```

---
