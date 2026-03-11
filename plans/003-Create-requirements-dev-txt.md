# Plan 003: Create requirements-dev.txt

## Summary

Create `cyrus2/requirements-dev.txt` with development-only dependencies: pytest, pytest-asyncio, pytest-mock, ruff, and pytest-cov. These are the tools for automated testing and code quality — separated from production dependencies for clean deployments. No version pins (Issue 004 handles that separately).

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/requirements-dev.txt` exists | `cyrus2/` exists but is empty | Create file |
| Contains pytest | Not present | Add line |
| Contains pytest-asyncio | Not present | Add line |
| Contains pytest-mock | Not present | Add line |
| Contains ruff | Not present | Add line |
| Contains pytest-cov (optional) | Not present | Add line — AC3 says "optional", but docs/14-test-suite.md and docs/17-ruff-linting.md both support including it. Include it. |
| Installable via `pip install -r` | N/A | Verify syntax |

## Design Decisions

1. **Include pytest-cov** — The acceptance criteria mark it as optional, but coverage reporting is standard practice and costs nothing to list. Including it now avoids a round-trip later.

2. **No version pins** — Issue 004 explicitly handles pinning for both production and dev dependencies. Following the same pattern as the existing root-level `requirements.txt`, `requirements-brain.txt`, and `requirements-voice.txt` which list bare package names.

3. **One package per line, alphabetical order** — Matches the convention in existing requirements files. Alphabetical order makes diffs cleaner and avoids merge conflicts when adding packages.

4. **Trailing newline** — Standard POSIX text file convention. All existing requirements files in the project end with a newline.

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC1 | File `cyrus2/requirements-dev.txt` exists | `test -f cyrus2/requirements-dev.txt` |
| AC2 | Contains pytest, pytest-asyncio, pytest-mock, ruff | Read file → assert all 4 packages present |
| AC3 | Optional: add pytest-cov | Read file → assert pytest-cov present |
| AC4 | Installable with `pip install -r` | `pip install --dry-run -r cyrus2/requirements-dev.txt` (dry-run avoids side effects) |

## Implementation Steps

### Step 1: Create `cyrus2/requirements-dev.txt`

Write the file with this exact content (alphabetical, one per line):

```
pytest
pytest-asyncio
pytest-cov
pytest-mock
ruff
```

**File path:** `cyrus2/requirements-dev.txt`

### Step 2: Verify file exists and content is correct

```bash
cd /home/daniel/Projects/barf/cyrus
test -f cyrus2/requirements-dev.txt && echo "OK: file exists" || echo "FAIL: file missing"
```

```bash
python3 -c "
import sys

with open('cyrus2/requirements-dev.txt') as f:
    packages = [line.strip() for line in f if line.strip()]

expected = ['pytest', 'pytest-asyncio', 'pytest-cov', 'pytest-mock', 'ruff']
errors = []

for pkg in expected:
    if pkg not in packages:
        errors.append(f'missing: {pkg}')

for pkg in packages:
    if pkg not in expected:
        errors.append(f'unexpected: {pkg}')

if packages != expected:
    errors.append(f'order wrong: got {packages}, expected {expected}')

if errors:
    print('FAIL:', errors)
    sys.exit(1)
print('All acceptance criteria pass')
"
```

### Step 3: Verify pip can parse the file

```bash
pip install --dry-run -r cyrus2/requirements-dev.txt 2>&1 | head -20
```

Expect: pip resolves all packages without errors. The `--dry-run` flag prevents actual installation.

## Risk Assessment

**Minimal risk.** This is a single new file with 5 lines of text. No code changes, no imports, no runtime impact. The only failure mode is a typo in a package name, caught by Step 3's dry-run verification.
