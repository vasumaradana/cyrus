# Plan 020: Write test_project_matching.py (Tier 1)

## Summary

Create `cyrus2/tests/test_project_matching.py` with 26 parametrized test cases covering three pure project-matching functions: `_extract_project()` (10 cases), `_make_alias()` (6 cases), and `_resolve_project()` (10 cases). Zero mocking — all functions are pure transforms (`str -> str` or `str, dict -> str | None`).

## Prerequisites

- **Issue 018** (PLANNED) — creates `cyrus2/tests/` directory, `conftest.py`, and `pytest.ini` with `pythonpath = ..` so `import cyrus_brain` works from test files.
- **Issue 005** — cyrus_common.py foundation (dependency listed in issue, but project matching functions have no dependency on it).

If the builder runs before 018 is complete, it must create the minimal directory structure and pytest config. See Step 1.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/tests/test_project_matching.py` | Does not exist | Create with 26 test cases |
| `cyrus2/tests/` directory | Does not exist (created by issue 018) | Verify exists; create if missing |
| `cyrus2/tests/__init__.py` | Does not exist | Verify exists; create if missing |
| `cyrus2/pytest.ini` with `pythonpath = ..` | Does not exist (created by issue 018) | Verify exists; create if missing |
| Functions importable | Source at cyrus root: `cyrus_brain.py` | Import via `pythonpath` config |

## Source Code Under Test

### `_extract_project(title: str) -> str` — cyrus_brain.py:113-116

```python
def _extract_project(title: str) -> str:
    t = title.replace(" - Visual Studio Code", "").lstrip("● ").strip()
    parts = [p.strip() for p in t.split(" - ") if p.strip()]
    return parts[-1] if parts else "VS Code"
```

Pipeline:
1. Remove literal ` - Visual Studio Code` suffix
2. Strip `●` and space chars from left (dirty/unsaved indicator)
3. Strip whitespace
4. Split on ` - `, filter empty parts
5. Return last part (most specific), or `"VS Code"` fallback if nothing remains

### `_make_alias(proj: str) -> str` — cyrus_brain.py:119-120

```python
def _make_alias(proj: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", proj.lower())).strip()
```

Pipeline:
1. Lowercase
2. Replace dashes and underscores with spaces
3. Collapse multiple spaces to single space
4. Strip leading/trailing whitespace

**Note:** Does NOT split camelCase — `"myProject"` becomes `"myproject"`, not `"my project"`. The issue's example is inaccurate here; tests must reflect actual behavior.

### `_resolve_project(query: str, aliases: dict) -> str | None` — cyrus_brain.py:123-137

```python
def _resolve_project(query: str, aliases: dict) -> str | None:
    q = re.sub(r"\s+", " ", re.sub(r"[-_]", " ", query.lower())).strip()
    if q in aliases:
        return aliases[q]
    candidates = []
    for alias, proj in aliases.items():
        if q in alias or alias in q:
            candidates.append((len(alias), alias, proj))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][2]
    return None
```

Resolution strategy:
1. Normalize query same way as aliases (lowercase, dashes/underscores to spaces)
2. **Exact match** — instant return
3. **Partial substring match** — bidirectional: query-in-alias OR alias-in-query
4. **Longest alias wins** — most specific match preferred (sort by `len(alias)` descending)
5. **No match** — return `None`

**Note:** This is substring matching, not fuzzy/edit-distance matching. No `difflib`, `fuzzywuzzy`, or `rapidfuzz` involved.

## Design Decisions

### 1. Use `@pytest.mark.parametrize` throughout

All three functions are pure transforms — perfect for parametrize. `_extract_project` and `_make_alias` use `(input, expected)` tuples. `_resolve_project` uses `(query, aliases, expected)` tuples since each case may need different alias dicts.

### 2. Import strategy

```python
from cyrus_brain import _extract_project, _make_alias, _resolve_project
```

Triggers module-level imports in `cyrus_brain.py` (pygetwindow, sounddevice, etc.). Test environment must have production dependencies installed.

### 3. Test naming convention

Follows plan 019 pattern — functions named `test_<function_name>` with parametrize IDs providing scenario context:

```
test_project_matching.py::test_extract_project[simple_project] PASSED
test_project_matching.py::test_make_alias[kebab_case] PASSED
test_project_matching.py::test_resolve_project[longest_alias_wins] PASSED
```

### 4. No conftest fixtures needed

Tier 1 pure function tests need no fixtures from conftest.py.

### 5. Issue examples corrected against real implementation

Several expected outputs in the issue don't match actual function behavior:
- Issue says `"myProject"` → `"my project"` via `_make_alias`. Actual: `"myproject"` (no camelCase splitting).
- Issue says `"path/to/project - VSCode"` → `"project"` via `_extract_project`. Actual: `"VSCode"` (only ` - Visual Studio Code` suffix is removed, not ` - VSCode`; then split on ` - ` returns last part).
- Issue says `"ProjectName [folder] - VS Code"` → `"ProjectName"`. Actual: `"VS Code"` (suffix ` - Visual Studio Code` doesn't match ` - VS Code`, so nothing is removed; split on ` - ` returns last part `"VS Code"`).

Tests reflect actual code behavior, not issue examples.

## Acceptance Criteria -> Test Mapping

| AC | Requirement | Verification |
|---|---|---|
| AC1 | `cyrus2/tests/test_project_matching.py` exists with 26+ test cases | File exists, `pytest --collect-only` shows >= 26 items |
| AC2 | `test_extract_project()` covers ~10 cases: VS Code title parsing | 10 parametrized cases |
| AC3 | `test_make_alias()` covers ~6 cases: kebab/snake/mixed conversions | 6 parametrized cases |
| AC4 | `test_resolve_project()` covers ~10 cases: matching/ambiguity/no-match | 10 parametrized cases |
| AC5 | All tests pass: `pytest tests/test_project_matching.py -v` | Exit code 0 |
| AC6 | Test names describe the title format or alias transformation | Parametrize IDs are descriptive English slugs |

## Test Case Inventory

### `test_extract_project` — 10 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `simple_project` | `"myproject - Visual Studio Code"` | `"myproject"` | Standard VS Code title |
| `file_and_project` | `"main.py - myproject - Visual Studio Code"` | `"myproject"` | File open; takes last segment after split |
| `deep_path` | `"file.py - src - myproject - Visual Studio Code"` | `"myproject"` | Multiple segments; last wins |
| `dirty_indicator` | `"● myproject - Visual Studio Code"` | `"myproject"` | Unsaved bullet indicator stripped by lstrip |
| `single_word` | `"Settings - Visual Studio Code"` | `"Settings"` | Single-word project name |
| `no_vscode_suffix` | `"some-editor-title"` | `"some-editor-title"` | Non-VS Code title; no replacement occurs |
| `brackets_preserved` | `"ProjectName [SSH: host] - Visual Studio Code"` | `"ProjectName [SSH: host]"` | Remote SSH brackets kept in output |
| `unicode_project` | `"日本語 - Visual Studio Code"` | `"日本語"` | Unicode project name preserved |
| `empty_after_strip` | `" - Visual Studio Code"` | `"VS Code"` | Nothing left after removal; fallback returned |
| `empty_string` | `""` | `"VS Code"` | Empty input; fallback returned |

### `test_make_alias` — 6 cases

| ID | Input | Expected | Rationale |
|---|---|---|---|
| `kebab_case` | `"my-project"` | `"my project"` | Dashes replaced with spaces |
| `snake_case` | `"my_project"` | `"my project"` | Underscores replaced with spaces |
| `camel_case_lowered` | `"myProject"` | `"myproject"` | Only lowercased; no camelCase split |
| `upper_kebab` | `"MY-PROJECT"` | `"my project"` | Uppercase lowered + dashes to spaces |
| `already_spaced` | `"my project"` | `"my project"` | Already normalized; no change |
| `mixed_separators` | `"my-_-Project"` | `"my project"` | Mixed dash/underscore/dash → spaces collapsed |

### `test_resolve_project` — 10 cases

| ID | Query | Aliases | Expected | Rationale |
|---|---|---|---|---|
| `exact_match` | `"my project"` | `{"my project": "MyProject"}` | `"MyProject"` | Direct exact match |
| `normalized_kebab` | `"my-project"` | `{"my project": "MyProject"}` | `"MyProject"` | Dashes normalized → exact match |
| `normalized_underscore` | `"my_project"` | `{"my project": "MyProject"}` | `"MyProject"` | Underscores normalized → exact match |
| `case_insensitive` | `"MY PROJECT"` | `{"my project": "MyProject"}` | `"MyProject"` | Uppercase lowered → exact match |
| `partial_query_in_alias` | `"other"` | `{"my other project": "OtherProj"}` | `"OtherProj"` | Query is substring of alias |
| `partial_alias_in_query` | `"my project v2"` | `{"my project": "MyProject"}` | `"MyProject"` | Alias is substring of query |
| `longest_alias_wins` | `"barf ts stuff"` | `{"barf": "Barf", "barf ts": "barf-ts"}` | `"barf-ts"` | Multiple partial matches; longer alias wins |
| `no_match` | `"nonexistent"` | `{"my project": "MyProject"}` | `None` | No exact or partial match |
| `empty_aliases` | `"anything"` | `{}` | `None` | Empty dict → no match possible |
| `special_chars_in_alias` | `"c++"` | `{"c++": "CPP", "c#": "CSharp"}` | `"CPP"` | Non-alphanumeric chars in alias; exact match |

**Total: 26 test cases** (10 + 6 + 10)

## Implementation Steps

### Step 1: Verify test infrastructure exists

```bash
cd /home/daniel/Projects/barf/cyrus

# Check issue 018 artifacts
test -d cyrus2/tests/ && echo "OK: tests dir" || echo "MISSING: tests dir"
test -f cyrus2/tests/__init__.py && echo "OK: __init__" || echo "MISSING: __init__"
test -f cyrus2/pytest.ini && echo "OK: pytest.ini" || echo "MISSING: pytest.ini"
```

If any are missing, create the minimal structure:

```bash
mkdir -p cyrus2/tests
touch cyrus2/tests/__init__.py
```

If `cyrus2/pytest.ini` doesn't exist, create it with:

```ini
[pytest]
pythonpath = ..
testpaths = tests
```

This makes `import cyrus_brain` resolve to `cyrus_brain.py` at the cyrus root.

### Step 2: Create `cyrus2/tests/test_project_matching.py`

Write all 26 test cases using `@pytest.mark.parametrize`. Structure:

```python
"""Tier 1 pure-function tests for project matching.

Tests cover:
    _extract_project  -- VS Code window title parsing
    _make_alias       -- kebab/snake/mixed case to normalized space-separated alias
    _resolve_project  -- substring-based project resolution from alias dict
"""

from __future__ import annotations

import pytest

from cyrus_brain import _extract_project, _make_alias, _resolve_project


@pytest.mark.parametrize(("title", "expected"), [...], ids=[...])
def test_extract_project(title: str, expected: str) -> None:
    assert _extract_project(title) == expected


@pytest.mark.parametrize(("proj", "expected"), [...], ids=[...])
def test_make_alias(proj: str, expected: str) -> None:
    assert _make_alias(proj) == expected


@pytest.mark.parametrize(("query", "aliases", "expected"), [...], ids=[...])
def test_resolve_project(query: str, aliases: dict, expected: str | None) -> None:
    assert _resolve_project(query, aliases) == expected
```

**Key notes for the builder:**

- `test_resolve_project` takes `(query, aliases, expected)` triples — each case supplies its own aliases dict to keep tests independent.
- Use the actual Unicode characters (`"日本語"`) in the source — Python 3 handles UTF-8 natively; no need for escape sequences.
- Each parametrize entry includes an explicit `ids=` list for readable pytest output.
- Do NOT import anything from conftest — these are pure function tests with zero fixture dependencies.

### Step 3: Run tests and iterate

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_project_matching.py -v
```

Expected: 26 tests pass. If any fail, trace the input through the function step by step and adjust expected values.

### Step 4: Verify test count

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_project_matching.py --collect-only -q | tail -1
```

Expected: `26 tests collected`

### Step 5: Run subset commands from acceptance criteria

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
pytest tests/test_project_matching.py::test_extract_project -v
pytest tests/test_project_matching.py -k "alias" -v
pytest tests/test_project_matching.py -k "resolve" -v
```

All three should pass independently.

## Import Risk

`cyrus_brain.py` has heavy module-level imports (pygetwindow, pyautogui, comtypes, uiautomation, sounddevice, numpy, torch). If these aren't installed in the test environment, imports will fail with `ModuleNotFoundError`.

**Mitigation:** The project runs on the dev machine with all deps installed. If imports fail, the builder should:
1. First try `pip install -r requirements.txt` to ensure production deps are present.
2. If specific modules are unavailable, flag as STUCK.

## Files Created/Modified

| File | Action | Description |
|---|---|---|
| `cyrus2/tests/test_project_matching.py` | **Create** | 26 parametrized test cases across 3 test functions |
| `cyrus2/tests/` directory | **Verify/Create** | Must exist (from issue 018, create if missing) |
| `cyrus2/tests/__init__.py` | **Verify/Create** | Must exist (from issue 018, create if missing) |
| `cyrus2/pytest.ini` | **Verify/Create** | Must exist with `pythonpath = ..` (from issue 018, create if missing) |
