# Implementation Plan: Extract Shared Code into cyrus_common.py

**Issue**: [005-Extract-shared-code-into-cyrus-common](/home/daniel/Projects/barf/cyrus/issues/005-Extract-shared-code-into-cyrus-common.md)
**Created**: 2026-03-16
**PROMPT**: `/home/daniel/Projects/barf/cyrus/prompts/PROMPT_plan.md`

## Gap Analysis

**Already exists**:
- `main.py` (~1,756 lines) at project root — full monolith with all voice, VAD, TTS, routing, and UI automation
- `cyrus_brain.py` (~1,773 lines) at project root — evolved brain engine with websocket IPC, hook integration, mobile support
- Both files share ~90% identical code: 9 pure functions, 3 classes, 8+ constants/regexes
- Detailed code audit in `docs/12-code-audit.md` identifying all C3 duplication (14 items)
- 52 agent definitions in `.claude/agents/`

**Needs building**:
- `cyrus2/` directory populated with v1 files (blocked by **Issue 002**, state: PLANNED)
- `cyrus2/cyrus_common.py` — new shared module (~900–1,100 lines)
- Refactored `cyrus2/main.py` — imports from common, duplicates removed (~900–1,000 lines)
- Refactored `cyrus2/cyrus_brain.py` — imports from common, duplicates removed (~700–850 lines)
- Callback-based class constructors to decouple communication patterns
- Chime registration system (local audio vs websocket IPC)

**BLOCKER**: Issue 002 must complete first — it copies all 7 v1 Python files into `cyrus2/` and applies Ruff formatting. `cyrus2/main.py` and `cyrus2/cyrus_brain.py` must exist before this issue can proceed.

## Approach

**Strategy**: Use cyrus_brain.py's implementations as the canonical base (superset), inject callbacks for communication pattern differences, extract into cyrus_common.py, then update both entry points to import from common.

**Why this approach**:
- cyrus_brain.py is the evolved version — every difference from main.py is either a brain enhancement (guarded by state main.py never activates) or an architectural integration point (parameterizable via callbacks)
- main.py is being deprecated (Issue 006), so brain's implementations are canonical
- Callback injection is the cleanest way to decouple classes from their output mechanism (tts_queue vs websocket) without feature flags or subclassing
- Per Interview Q1: "refactor main.py first, then extract" — factory functions ARE the service-delegation refactoring

### Three Tiers of Duplication

| Tier | Items | Difficulty | Lines saved |
|------|-------|-----------|-------------|
| **1. Pure functions** | 9 functions | Trivial — identical implementations | ~400 |
| **2. Constants** | 8 constants/regexes | Trivial — identical (except MAX_SPEECH_WORDS) | ~60 |
| **3. Classes** | ChatWatcher, PermissionWatcher, SessionManager | Medium — different communication patterns | ~1,200 |

### Eight Divergences — Resolutions

1. **`_resolve_project` differs**: brain normalizes query (dashes/underscores → spaces) and returns longest-matching alias. main.py does simple `.lower().strip()`. **Use brain's version** — strictly more robust.

2. **`clean_for_speech` differs**: brain calls `_sanitize_for_speech()` for Unicode → ASCII cleanup. main.py omits it. **Use brain's version** — main.py gains TTS quality improvement.

3. **`play_chime` / `play_listen_chime` differ fundamentally**: main.py = local numpy/pygame audio; brain = websocket IPC `{"type": "chime"}`. **Callback registration pattern** — `register_chime_handlers()` in common, each entry point registers its backend.

4. **`MAX_SPEECH_WORDS`** (main=30, brain=50): **Extract with default=50**, `clean_for_speech()` accepts optional `max_words` param. main.py passes `max_words=30`.

5. **`_HALLUCINATIONS`** exists only in main.py: **Extract to common anyway** — belongs with speech-processing constants.

6. **`ChatWatcher` diverges** in `flush_pending()` and `start()`: **Dependency injection** — constructor accepts `enqueue_speech_fn` and `chime_fn` callables.

7. **`PermissionWatcher` diverges** (brain adds pre-arm, auto-allow, Quick Pick scanning): **Extract brain's version (superset)** — constructor accepts `speak_urgent_fn` and `stop_speech_fn`. Pre-arm is inert unless explicitly activated.

8. **`SessionManager` diverges** (brain omits tts_queue, adds IPC whisper-prompt push): **Factory injection** — constructor accepts `make_chat_watcher_fn`, `make_perm_watcher_fn`, `on_whisper_prompt_fn`.

### Out of Scope
- `_execute_cyrus_command()` — Issue 007 (dispatch table refactor)
- `main()` function decomposition — Issue 008
- `submit_to_vscode()` / `_find_chat_input()` — fundamentally different implementations
- `cyrus_voice.py` deduplication — follow-up issue

## Rules to Follow

No `.claude/rules/` directory exists in this project. No formal rules apply.

General principles from MEMORY.md:
- **Fix everything you see** — if lint/type/test issues encountered during extraction, fix them
- **No arbitrary values** — use standard constants

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Extract functions/constants to cyrus_common.py | `refactoring-specialist` subagent | Systematic code extraction with behavior preservation |
| Wire callback factories in both entry points | `python-pro` subagent | Idiomatic Python patterns, async/callback wiring |
| Lint/format validation | `ruff` (CLI tool) | Verify all three files pass ruff check + format |

## Prioritized Tasks

- [x] **Step 1: Verify Prerequisites** — Confirmed `cyrus2/main.py` and `cyrus2/cyrus_brain.py` exist (Issue 002 complete). Baseline: brain 1,997 lines, main 1,955 lines.
- [x] **Step 2: Create cyrus_common.py — Imports, Constants, Pure Functions** — Extracted all 8 constants/regexes and 9 pure functions. Added chime registration system. `py_compile` passes.
- [x] **Step 3: Add ChatWatcher class** — Extracted brain's version with `enqueue_speech_fn`, `chime_fn`, and `max_speech_words` injection. All brain extras preserved.
- [x] **Step 4: Add PermissionWatcher class** — Extracted brain's version with `speak_urgent_fn` and `stop_speech_fn` callbacks. All brain extras preserved.
- [x] **Step 5: Add SessionManager class** — Extracted with factory injection. `recent_responses()` from main.py included.
- [x] **Step 6: Full import smoke test** — All symbols import correctly from cyrus_common.
- [x] **Step 7: Update cyrus_brain.py** — Import block added, factory functions created, chime handlers registered, SessionManager constructed with factories, all duplicates deleted.
- [x] **Step 8: Update main.py** — Import block added, `play_chime`/`play_listen_chime` renamed to `_local_*` variants, local audio handlers registered, factory functions added, `max_speech_words=30` override passed to ChatWatcher, duplicates deleted.
- [x] **Step 9: Verify no duplicate definitions remain** — grep check passed: all 12 items (9 functions + 3 classes) appear only in cyrus_common.py.
- [x] **Step 10: Verify no circular imports** — `py_compile` on all three files passes cleanly.
- [x] **Step 11: Ruff lint and format** — `ruff check` + `ruff format --check` pass on all three files (0 errors).
- [x] **Step 12: Line count comparison** — Result: common 1,307 + brain 1,076 + main 1,186 = 3,569 total (vs. ~3,952 lines pre-refactor in brain+main alone). Shared code now lives once instead of twice.

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| `cyrus2/cyrus_common.py` created with all shared functions and classes | `python3 -m py_compile cyrus_common.py` + import smoke test of all 22 symbols | integration |
| All functions/classes from C3 duplication table extracted | Full import test: all 9 functions, 3 classes, 8 constants importable | integration |
| Both `cyrus2/main.py` and `cyrus2/cyrus_brain.py` import from `cyrus_common.py` | `grep "from cyrus_common import" main.py cyrus_brain.py` shows both files | verification |
| No duplicate function/class definitions across files | `grep -l "^def _extract_project" main.py cyrus_brain.py` returns empty (repeat for all 9+3) | verification |
| ~2,000 lines of duplication eliminated | `wc -l` comparison: combined post < combined pre by ~1,500+ lines | verification |
| All tests pass (unit tests for pure functions added in Issue 009) | `python3 -c "import cyrus_common"`, `python3 -m py_compile` on all 3 files, ruff passes | integration |

**No cheating** — cannot claim done without all verification passing.

**Note**: Full unit tests are Issue 009's scope. This issue verifies via import tests, compile checks, duplicate grep checks, and lint. The issue explicitly states "All tests pass (unit tests for pure functions added in Issue 009)".

## Validation (Backpressure)

- **Compile**: `python3 -m py_compile cyrus2/cyrus_common.py cyrus2/main.py cyrus2/cyrus_brain.py`
- **Imports**: `python3 -c "import cyrus_common; import main; import cyrus_brain"` (may partially fail on non-Windows without UIA — cyrus_common import is the critical check)
- **Lint**: `ruff check cyrus2/cyrus_common.py cyrus2/main.py cyrus2/cyrus_brain.py`
- **Format**: `ruff format --check cyrus2/cyrus_common.py cyrus2/main.py cyrus2/cyrus_brain.py`
- **No duplicates**: grep check for all 12 extracted items (9 functions + 3 classes)
- **Line reduction**: `wc -l` shows ~1,500+ lines eliminated

## Files to Create/Modify

- **Create**: `cyrus2/cyrus_common.py` (~900–1,100 lines) — all shared constants, functions, classes, chime registration
- **Modify**: `cyrus2/main.py` — add imports from common, create factory functions, rename local chime functions, add `max_words=30` overrides, delete ~750 lines of duplicates
- **Modify**: `cyrus2/cyrus_brain.py` — add imports from common, create factory functions, register chime handlers, construct SessionManager with factories, delete ~800 lines of duplicates

## Design Decisions

### D1. Brain as canonical base
Since main.py is being deprecated (Issue 006), brain's implementations win. They are a strict superset.

### D2. Callback-based communication
Classes are decoupled from output mechanism via constructor-injected callables. Each entry point wires its own backend:
- **main.py**: tts_queue puts + local audio chimes
- **brain**: _speak_queue puts + websocket IPC chimes

### D3. MAX_SPEECH_WORDS override
Default = 50 in common. `clean_for_speech(text, max_words=MAX_SPEECH_WORDS)` — main.py passes `max_words=30`.

### D4. Chime registration
`register_chime_handlers(chime_fn, listen_chime_fn)` in common. `play_chime(loop=None)` dispatches to registered handler. main.py registers local audio; brain registers websocket.

### D5. Extra constants extracted opportunistically
`WAKE_WORDS` and `VOICE_HINT` — identically duplicated but not explicitly in issue. Extract per "fix everything you see."

### D6. Interview Q&A compliance
1. Q1: Service-delegation refactoring is part of 005's scope → factory functions are the delegation layer
2. Q2: `_sanitize_for_speech()` extracted to common, brain imports it, main.py benefits via `clean_for_speech()`
3. Q3: MAX_SPEECH_WORDS default=50 with per-file parameter override

### D7. `_fast_command` return type
Issue shows `tuple[str, list[str]] | None` — actual code returns `dict | None`. Use actual return type.

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Issue 002 not complete (cyrus2/ empty) | **Blocker** | **High** (currently true) | Fail early in Step 1. Cannot proceed. |
| Runtime behavior change from `_resolve_project` upgrade | Low | Low | Brain version proven in production |
| Callback wiring errors in class factories | Medium | Medium | Step 6 smoke test + Step 10 import check |
| Module-global state (`_whisper_prompt`) | Medium | Low | Globals stay in caller modules; common uses callbacks only |
| `comtypes.CoInitializeEx()` missing in main.py poll threads | Low | Medium | Gated behind try/except in common |
| Import weight of numpy/pygame in common | None | None | try/except makes deps optional |

## Method-Level Class Comparison (Reference)

### ChatWatcher (main.py ~456–701, brain ~403–637)

| Method | Status | Difference |
|--------|--------|-----------|
| `__init__` | Identical | — |
| `last_spoken` (property) | Identical | — |
| `flush_pending()` | **Different** | main takes `tts_queue, loop`; brain uses global `_speak_queue` |
| `_find_webview()` | Identical | — |
| `_walk()` | Identical | — |
| `_extract_response()` | Identical | Logic same, only comment differences |
| `start()` | **Major diff** | Brain adds: comtypes.CoInitializeEx, coord caching, hook skip, 3-tuple speak, websocket chime |

### PermissionWatcher (main.py ~706–962, brain ~638–1026)

| Method | Status | Difference |
|--------|--------|-----------|
| `__init__` | **Different** | Brain adds 5 fields: `_vscode_win`, `_pre_armed*` (4). Plus `_AUTO_ALLOWED_TOOLS` |
| `is_pending` / `prompt_pending` | Identical | — |
| `_find_webview()` | **Minor diff** | Brain caches `self._vscode_win` |
| `_scan_window_for_permission()` | **Brain only** | ARIA live region scanning |
| `_scan()` | **Major diff** | Brain: 2-stage detection, coord caching |
| `arm_from_hook()` | **Brain only** | Pre-arms from SDK PreToolUse hook |
| `handle_response()` | **Major diff** | Brain: dual-mode keyboard/button approval |
| `handle_prompt_response()` | Identical | Only print prefix differs |
| `start()` | **Major diff** | Brain: state machine with 20s timeout, poll ticks, pre-arm upgrade |

### SessionManager (main.py ~967–1048, brain ~1027–1104)

| Method | Status | Difference |
|--------|--------|-----------|
| `__init__` | Identical | — |
| `aliases` / `multi_session` / `perm_watchers` | Identical | — |
| `on_session_switch()` | **Different** | main takes `tts_queue`; print prefix differs |
| `last_response()` | Identical | — |
| `recent_responses()` | **main.py only** | Returns last N responses |
| `rename_alias()` | Identical | — |
| `_add_session()` | **Major diff** | Brain sends whisper_prompt via websocket; different params |
| `start()` | **Different** | main takes `tts_queue`; print prefix differs |
