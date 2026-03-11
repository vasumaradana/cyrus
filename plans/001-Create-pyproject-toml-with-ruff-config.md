# Plan 001: Create pyproject.toml with Ruff Config

## Summary

Create `cyrus2/pyproject.toml` with project metadata and Ruff linting/formatting configuration. This is the foundation file for the Cyrus 2.0 rewrite — all subsequent issues depend on it existing.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/pyproject.toml` exists | Directory exists, empty | Create file |
| Project metadata (name, version, python) | Nothing | Add `[project]` section |
| Ruff rule sets E, F, W, I, UP, B | No linting config anywhere | Add `[tool.ruff.lint]` |
| target-version py310, line-length 88 | N/A | Add `[tool.ruff]` |
| Exclude `.venv` and `cyrus-companion` | N/A | Add to `[tool.ruff]` exclude |
| `[tool.ruff.lint]` section present | N/A | Create section |
| `[tool.ruff.format]` section present | N/A | Create section |

No existing `pyproject.toml` or TOML files exist anywhere in the project. The `cyrus2/` directory exists but is empty.

## Design Decisions

1. **File content matches issue spec exactly** — the issue provides a complete `Config Content Reference` section. No deviations needed; the config aligns with `docs/17-ruff-linting.md`.

2. **Validation approach** — Python's `tomllib` (stdlib in 3.11+, `tomli` backport for 3.10) can validate the TOML. Since the target is `python>=3.10`, we use `tomllib` with a fallback to `tomli` for validation. Simplest: just use `python3 -c "import tomllib; ..."` since the dev machine likely has 3.11+.

3. **No extra sections** — only what the acceptance criteria require. Future issues will add `[project.dependencies]`, `[build-system]`, etc.

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC1 | File exists with project metadata | `test -f cyrus2/pyproject.toml` + parse and check `[project]` fields |
| AC2 | Ruff rule sets E, F, W, I, UP, B | Parse TOML → assert `tool.ruff.lint.select` equals expected list |
| AC3 | target-version py310, line-length 88 | Parse TOML → assert `tool.ruff.target-version` and `tool.ruff.line-length` |
| AC4 | Exclude patterns include .venv and cyrus-companion | Parse TOML → assert `tool.ruff.exclude` contains both |
| AC5 | Both lint and format sections present | Parse TOML → assert `tool.ruff.lint` and `tool.ruff.format` keys exist |

## Implementation Steps

### Step 1: Create `cyrus2/pyproject.toml`

Write the file with this exact content:

```toml
[project]
name = "cyrus"
version = "2.0.0"
description = "Cyrus 2.0 - AI voice assistant with VS Code integration"
requires-python = ">=3.10"

[tool.ruff]
target-version = "py310"
line-length = 88
exclude = [".venv", "cyrus-companion"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]

[tool.ruff.format]
```

**File path:** `cyrus2/pyproject.toml`

### Step 2: Validate TOML syntax

```bash
python3 -c "
import tomllib
with open('cyrus2/pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
print('Valid TOML')
print('Sections:', list(data.keys()))
"
```

### Step 3: Verify all acceptance criteria

```bash
python3 -c "
import tomllib, sys

with open('cyrus2/pyproject.toml', 'rb') as f:
    data = tomllib.load(f)

errors = []

# AC1: project metadata
p = data.get('project', {})
if p.get('name') != 'cyrus': errors.append('name != cyrus')
if p.get('version') != '2.0.0': errors.append('version != 2.0.0')
if p.get('requires-python') != '>=3.10': errors.append('requires-python != >=3.10')

# AC2: rule sets
rules = data.get('tool', {}).get('ruff', {}).get('lint', {}).get('select', [])
expected = ['E', 'F', 'W', 'I', 'UP', 'B']
if rules != expected: errors.append(f'select {rules} != {expected}')

# AC3: target-version and line-length
ruff = data.get('tool', {}).get('ruff', {})
if ruff.get('target-version') != 'py310': errors.append('target-version != py310')
if ruff.get('line-length') != 88: errors.append('line-length != 88')

# AC4: exclude patterns
exclude = ruff.get('exclude', [])
if '.venv' not in exclude: errors.append('.venv not in exclude')
if 'cyrus-companion' not in exclude: errors.append('cyrus-companion not in exclude')

# AC5: both sections present
if 'lint' not in data.get('tool', {}).get('ruff', {}): errors.append('lint section missing')
if 'format' not in data.get('tool', {}).get('ruff', {}): errors.append('format section missing')

if errors:
    print('FAIL:', errors)
    sys.exit(1)
print('All acceptance criteria pass')
"
```

## Risk Assessment

**Low risk.** This is a single new file with no dependencies on existing code. The content is fully specified in the issue. The only failure mode is a TOML syntax error, caught by Step 2.
