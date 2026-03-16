# Implementation Plan: Create pyproject.toml with Ruff Config

**Issue**: [001-Create-pyproject-toml-with-ruff-config](/home/daniel/Projects/barf/cyrus/issues/001-Create-pyproject-toml-with-ruff-config.md)
**Created**: 2026-03-16
**PROMPT**: `/home/daniel/Projects/barf/cyrus/prompts/PROMPT_plan.md`

## Gap Analysis

**Already exists**: `cyrus2/` directory (empty). Reference docs `docs/17-ruff-linting.md` and `docs/12-code-audit.md` define the desired Ruff configuration. No existing linting, formatting, or packaging config anywhere in the project.

**Needs building**: Single file `cyrus2/pyproject.toml` with:
- `[project]` section — name, version, description, requires-python
- `[tool.ruff]` section — target-version, line-length, exclude
- `[tool.ruff.lint]` section — select rule sets
- `[tool.ruff.format]` section — empty (use defaults)

## Approach

**Write the file verbatim from the issue's Config Content Reference.** The issue provides exact TOML content that also matches `docs/17-ruff-linting.md`. No deviations needed — this is a foundation file that subsequent issues (002-Run-ruff-autofix, 003-Create-requirements-dev-txt) depend on.

**Why this approach**: Content is fully specified in two sources (issue + docs/17) that agree. Adding anything beyond the spec would risk breaking downstream issue assumptions. The empty `[tool.ruff.format]` section is valid TOML and signals Ruff to use default formatting settings.

**Validation**: Python's `tomllib` (stdlib since 3.11) validates TOML syntax. The dev machine runs Python 3.11+, so `tomllib` is available even though the project targets `>=3.10`.

## Rules to Follow

- No `.claude/rules/` directory exists in this project — no rule files to reference.

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Create pyproject.toml | Direct file write | Single file, fully specified content — no agent needed |
| Validate TOML | `python3 -c "import tomllib; ..."` | Verify valid TOML syntax |
| Verify acceptance criteria | `python3` validation script | Programmatically check all 5 AC |

This issue is simple enough that no subagents or skills are needed.

## Prioritized Tasks

- [x] Create `cyrus2/pyproject.toml` with exact content from issue spec
- [x] Validate TOML syntax with `tomllib`
- [x] Verify all 5 acceptance criteria programmatically

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| AC1: File exists with project metadata (name: cyrus, version: 2.0.0, python>=3.10) | Parse TOML; assert `project.name == "cyrus"`, `project.version == "2.0.0"`, `project.requires-python == ">=3.10"` | verification |
| AC2: Ruff config includes rule sets: E, F, W, I, UP, B | Parse TOML; assert `tool.ruff.lint.select == ["E", "F", "W", "I", "UP", "B"]` | verification |
| AC3: Target version py310, line-length 88 | Parse TOML; assert `tool.ruff.target-version == "py310"` and `tool.ruff.line-length == 88` | verification |
| AC4: Exclude patterns include `.venv` and `cyrus-companion` | Parse TOML; assert both in `tool.ruff.exclude` | verification |
| AC5: Both `[tool.ruff.lint]` and `[tool.ruff.format]` sections present | Parse TOML; assert `"lint" in data["tool"]["ruff"]` and `"format" in data["tool"]["ruff"]` | verification |

**No cheating** — cannot claim done without all 5 acceptance criteria verified.

### Verification Script

```bash
python3 -c "
import tomllib, sys, os

path = 'cyrus2/pyproject.toml'
if not os.path.isfile(path):
    print(f'FAIL: {path} does not exist'); sys.exit(1)

with open(path, 'rb') as f:
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
if 'lint' not in ruff: errors.append('lint section missing')
if 'format' not in ruff: errors.append('format section missing')

if errors:
    print('FAIL:', errors); sys.exit(1)
print('All 5 acceptance criteria PASS')
"
```

## Validation (Backpressure)

- **TOML syntax**: `tomllib.load()` must succeed without exceptions
- **Acceptance criteria**: All 5 must pass via verification script above
- **No lint/build/test commands**: This is a config file with no code to lint, build, or test. Validation is TOML parsing + AC verification.

## Files to Create/Modify

- `cyrus2/pyproject.toml` — **New file**. Project metadata + Ruff linting/formatting configuration. Foundation for all subsequent Cyrus 2.0 issues.

## File Content

Exact content to write (from issue Config Content Reference):

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

## Risk Assessment

**Low risk.** Single new file, no dependencies on existing code, no modifications to existing files. Content is fully specified in the issue. Only failure mode is a TOML syntax error, caught by validation step.
