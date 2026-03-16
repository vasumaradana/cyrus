# Plan 039: Update Documentation for v2

## Summary

Rewrite `docs/README.md` to serve as the v2 documentation hub covering: split brain/voice architecture, centralized configuration, Docker containerization, companion extension registration protocol, auth tokens, health checks, configurable Whisper models, and session persistence. Create `docs/18-migration-guide.md` for the v1→v2 upgrade path. Update the root `README.md` project structure section to include `cyrus2/` and Docker files.

This is a **documentation-only issue** — no Python/TypeScript code changes.

## Dependencies

**Blocked by all Sprint 4–6 issues (027–038).** These are all currently PLANNED (not built). The builder MUST run Step 1's inspection checks before writing anything — document only what actually exists in code.

## Critical Codebase Observations

| Fact | Detail |
|---|---|
| `cyrus2/` directory | Currently empty — Sprint 4+ issues create modules here (`cyrus_config.py`, etc.) but main scripts (`cyrus_brain.py`, `cyrus_voice.py`, `cyrus_hook.py`) stay at root |
| Root `README.md` | Exists — user-facing quick start with developer setup, release install, voice commands, hotkeys, project structure |
| `docs/README.md` | Exists — documentation hub with ToC for docs 01–17 and a basic quick start |
| `docs/14-test-suite.md` | Exists — migration guide must use number **18**, not 14 |
| `.env.example` | Currently only has `ANTHROPIC_API_KEY=` — Issue 027 expands it |
| No `Dockerfile` yet | Issue 035 creates it |
| No `cyrus_config.py` yet | Issue 027 creates it in `cyrus2/` |
| No auth tokens yet | Issue 028 adds `CYRUS_AUTH_TOKEN` |
| Companion extension | `cyrus-companion/src/extension.ts` exists (v1 IPC) — Issues 031–034 add registration protocol |
| `TEST_COMMAND=` (empty) | No automated tests for docs — verification is manual |
| Main scripts stay at root | Plans 027–038 do NOT move `cyrus_brain.py` etc. into `cyrus2/` — they create new modules there while modifying root scripts to import from `cyrus2/` |

## Gap Analysis

| Acceptance Criterion | Current State | Action |
|---|---|---|
| docs/README.md updated with v2 structure | ToC for docs 01–17 + basic v1 quick start | Major rewrite — add v2 architecture, config, auth, extension, health, persistence sections |
| Quick Start includes brain + voice | Basic two-terminal quick start in both READMEs | Expand with `.env` configuration, split requirements, companion extension steps |
| Docker Quick Start added | Does not exist | New section (if Issue 035 Dockerfile landed) |
| Configuration section documents all env vars | No config section anywhere | New section — env var reference from `cyrus2/cyrus_config.py` (if Issue 027 landed) |
| Authentication section explains TOKEN setup | Does not exist | New section (if Issue 028 landed) |
| Extension setup guide (Issues 031–033) | Doc 08 covers v1 IPC transport only | New section covering registration protocol + new settings |
| Health check endpoint documented | Does not exist | New section (if Issue 036 landed) |
| Session persistence explained | Does not exist | New section (if Issue 038 landed) |
| Migration guide v1 → v2 | Does not exist | Create `docs/18-migration-guide.md` |
| All file paths updated to cyrus2/ | Both READMEs reference root-level scripts | Update to match actual file locations (main scripts likely still at root — `cyrus2/` only has modules) |

## Design Decisions

### D1. Migration guide gets number 18, not 14

The issue spec says `docs/14-migration-guide.md` but `docs/14-test-suite.md` already exists. Next available slot after doc 17 is 18.

### D2. Builder inspects code before writing — no speculative docs

Since all blocking issues are PLANNED, the builder must check what actually landed (Step 1). Every v2 section is gated on a code inspection result. If a feature didn't land, the section is omitted entirely — no aspirational documentation.

**Degenerate case**: If Step 1 finds ALL features MISSING (nothing from Sprint 4–6 has been built), the builder still delivers value by:
- Polishing the existing docs/README.md structure (Architecture, improved Quick Start, Troubleshooting)
- Documenting the existing companion extension (v1 IPC, which exists today)
- Creating a minimal migration guide with the "What Changed" and "Deprecated Features" sections
- Updating root README Project Structure to include `cyrus2/` (the directory exists, even if empty)

### D3. Main scripts stay at root — only modules go in `cyrus2/`

Plans 027–038 create new files in `cyrus2/` (`cyrus_config.py`) but modify root-level scripts (`cyrus_brain.py`, etc.) to import from `cyrus2/`. The scripts themselves don't move. File path references in docs must match this reality:
- `cyrus_brain.py` (not `cyrus2/cyrus_brain.py`)
- `cyrus2/cyrus_config.py` (new module)
- `cyrus_hook.py` (stays at root — must stay dependency-free)

**AC10 interpretation**: The issue spec says "All file paths updated to cyrus2/" but since main scripts stay at root per Plans 027–038, the builder should interpret AC10 as "all file paths in docs match actual file locations on disk." The verification in Step 5 checks exactly this — every backtick-quoted path in docs must resolve to a real file.

### D4. Configuration table derived from actual code

If `cyrus2/cyrus_config.py` exists, the builder reads it and generates the config table from actual class attributes and `CYRUS_*` env var names. This prevents doc/code divergence. If it doesn't exist, use the table from the issue spec as a fallback template.

**Fallback env var reference** (from Plans 027/028/036/037/038 — use only if `cyrus_config.py` is missing):

| Variable | Default | Source Plan |
|----------|---------|-------------|
| `CYRUS_BRAIN_PORT` | `8766` | 027 |
| `CYRUS_HOOK_PORT` | `8767` | 027 |
| `CYRUS_MOBILE_PORT` | `8769` | 027 |
| `CYRUS_COMPANION_PORT` | `8770` | 027 |
| `CYRUS_HEALTH_PORT` | `8771` | 036 |
| `CYRUS_SERVER_PORT` | `8765` | 027 |
| `CYRUS_BRAIN_BIND_HOST` | `0.0.0.0` | 027 |
| `CYRUS_BRAIN_CONNECT_HOST` | `localhost` | 027 |
| `CYRUS_AUTH_TOKEN` | _(none)_ | 028 |
| `CYRUS_HEADLESS` | `0` | 030 |
| `CYRUS_WHISPER_MODEL` | `medium.en` | 037 |
| `CYRUS_TTS_TIMEOUT` | `25.0` | 027 |
| `CYRUS_SPEECH_THRESHOLD` | `0.5` | 027 |
| `CYRUS_FRAME_MS` | `32` | 027 |
| `CYRUS_FRAME_SIZE` | `512` | 027 |
| `CYRUS_SPEECH_WINDOW_MS` | `300` | 027 |
| `CYRUS_SILENCE_WINDOW_MS` | `1000` | 027 |
| `CYRUS_MAX_RECORD_MS` | `12000` | 027 |
| `CYRUS_SPEECH_RATIO` | `0.80` | 027 |
| `CYRUS_CHAT_POLL_SECS` | `0.5` | 027 |
| `CYRUS_CHAT_STABLE_SECS` | `1.2` | 027 |
| `CYRUS_PERMISSION_POLL_SECS` | `0.3` | 027 |
| `CYRUS_STATE_FILE` | `~/.cyrus/state.json` | 038 |
| `CYRUS_MAX_SPEECH_WORDS` | `50` | 027 |
| `CYRUS_SOCKET_TIMEOUT` | `10` | 027 |
| `CYRUS_HOOK_TIMEOUT` | `2` | 027 |

### D5. Root README.md gets a project structure update only

The root `README.md` is a comprehensive user-facing document (developer setup, release install, voice commands, hotkeys). Only the **Project Structure** section at the bottom needs updating to add `cyrus2/`, Docker files, and any new files. Don't rewrite the entire root README — that's out of scope.

### D6. `docs/README.md` becomes the v2 technical reference

The root README is for users (setup + usage). `docs/README.md` is for developers (architecture + config + protocol details + doc index). They serve different audiences and both need updating.

## Acceptance Criteria → Verification Mapping

| # | Criterion | Verification |
|---|---|---|
| AC1 | docs/README.md updated with v2 structure | Contains "Cyrus 2.0" or "v2" heading; includes architecture section with split services |
| AC2 | Quick Start includes brain + voice modes | Contains "Quick Start" section with `cyrus_brain.py` and `cyrus_voice.py` commands |
| AC3 | Docker Quick Start added | Contains "Docker" section with `docker compose up` (only if Dockerfile exists) |
| AC4 | Config section documents all env vars | Contains env var table; `comm` check shows no vars in `cyrus_config.py` missing from docs |
| AC5 | Authentication section explains TOKEN | Contains "Authentication" heading with `CYRUS_AUTH_TOKEN` (only if auth landed) |
| AC6 | Extension setup guide | Contains "Companion Extension" section with setup steps |
| AC7 | Health check documented | Contains "Health" section with endpoint URL (only if health check landed) |
| AC8 | Session persistence explained | Contains "Persistence" section (only if state file feature landed) |
| AC9 | Migration guide v1 → v2 | `docs/18-migration-guide.md` exists with structured migration content |
| AC10 | File paths match reality | All file paths referenced in docs exist on disk (see D3 for interpretation) |

## Implementation Steps

### Step 1: Inspect codebase for landed v2 features (GATE)

Before writing any docs, determine which Sprint 4–6 features actually exist. **This step gates all subsequent sections.**

```bash
cd /home/daniel/Projects/barf/cyrus

# Feature checks — record each as EXISTS or MISSING
echo "=== 027: Centralized config ==="
ls cyrus2/cyrus_config.py 2>/dev/null && echo "EXISTS" || echo "MISSING"

echo "=== 028: Auth tokens ==="
grep -rl "CYRUS_AUTH_TOKEN" . --include="*.py" 2>/dev/null | head -3
# EXISTS if any matches, MISSING if empty

echo "=== 029: Configurable hook host ==="
grep -r "CYRUS_BRAIN_HOST\|CYRUS_BRAIN_CONNECT_HOST" . --include="*.py" 2>/dev/null | head -3

echo "=== 030: Headless mode ==="
grep -r "CYRUS_HEADLESS" . --include="*.py" 2>/dev/null | head -3

echo "=== 031/034: Companion registration ==="
grep -r '"register"\|"type".*register' cyrus-companion/src/extension.ts 2>/dev/null | head -3

echo "=== 032: Focus tracking ==="
grep -r "onDidChangeWindowState\|\"focus\"\|\"blur\"" cyrus-companion/src/extension.ts 2>/dev/null | head -3

echo "=== 033: Permission handling ==="
grep -r "permission_respond" cyrus-companion/src/extension.ts 2>/dev/null | head -3

echo "=== 035: Docker files ==="
ls Dockerfile docker-compose.yml cyrus2/Dockerfile cyrus2/docker-compose.yml 2>/dev/null

echo "=== 036: Health check ==="
grep -rl "/health" . --include="*.py" 2>/dev/null | head -3

echo "=== 037: Configurable Whisper ==="
grep -r "CYRUS_WHISPER_MODEL" . --include="*.py" 2>/dev/null | head -3

echo "=== 038: Session persistence ==="
grep -r "CYRUS_STATE_FILE\|state\.json\|session.*persist" . --include="*.py" 2>/dev/null | head -3

echo "=== .env.example current state ==="
cat .env.example

echo "=== cyrus2/ contents ==="
ls -la cyrus2/

echo "=== Root scripts ==="
ls *.py
```

**Record results and use them to gate sections in Steps 2–4.**

### Step 2: Rewrite `docs/README.md`

**File**: `docs/README.md`

Replace the entire file. The target structure:

```
# Cyrus Documentation — v2

## Architecture
  - Split brain/voice services
  - Companion extension role
  - Port map table
  - Link to doc 01

## Quick Start (Traditional)
  - pip install split requirements
  - Configure .env (auth token + keys)
  - Start brain (Terminal 1)
  - Start voice (Terminal 2)
  - Install companion extension
  - Configure Claude Code hooks
  - Link to doc 10

## Quick Start (Docker)                    ← ONLY if Step 1 found Dockerfile
  - Copy .env.example, set tokens + CYRUS_HEADLESS=1
  - docker compose up
  - Port mappings table
  - Connect hook from host (use actual env var name from code)
  - Install companion extension on host
  - Link to doc 13

## Configuration                           ← ONLY if Step 1 found cyrus_config.py
  - Full env var reference table
  - Derived from cyrus2/cyrus_config.py class attributes
  - If cyrus_config.py missing, use D4 fallback table
  - Link to .env.example

## Authentication                          ← ONLY if Step 1 found CYRUS_AUTH_TOKEN
  - Why it exists (all ports were unauthenticated in v1)
  - Token generation command
  - Set in .env
  - Must match across all services

## VS Code Companion Extension
  - Always include — extension exists in v1
  - If registration (031) landed: document brainHost/brainPort settings, registration protocol
  - If focus tracking (032) landed: mention focus/blur events
  - If permission handling (033) landed: document permission_respond flow
  - Link to doc 08

## Health Checks                           ← ONLY if Step 1 found /health endpoint
  - Endpoint URL (port 8771 per Plan 036) + response format
  - Docker HEALTHCHECK usage

## Session Persistence                     ← ONLY if Step 1 found state file feature
  - State file location (CYRUS_STATE_FILE, default ~/.cyrus/state.json)
  - What's persisted (aliases, active project, pending queues)
  - Behavior on startup/shutdown (atomic writes, signal handlers)

## Troubleshooting
  - Always include — based on issue spec template
  - Brain won't start in Docker (if Docker exists)
  - Extension won't register (if registration exists)
  - Hook connection refused
  - Auth token mismatch (if auth exists)
  - General: check logs, verify ports, verify paths

## Reference Documents
  - Existing docs 01–17 table of contents (preserved from current file)
  - Add row 18 for migration guide

## Reading Order
  - Preserved from current file
```

**Content sources per section:**
- Architecture: adapt from `docs/01-overview.md` + root `README.md` architecture diagram
- Quick Start Traditional: issue spec Step 2 example, cross-reference with root `README.md` developer setup
- Quick Start Docker: issue spec Step 3 example + `docs/13-docker-containerization.md` Phase 4
- Configuration: read `cyrus2/cyrus_config.py` if it exists, otherwise use D4 fallback table
- Authentication: Issue 028 plan
- Extension: `docs/08-companion-extension.md` + Issues 031–033 plans
- Health: Issue 036 plan (port 8771, aiohttp, JSON response format)
- Session persistence: Issue 038 plan (atomic writes, signal handlers, state categories)
- Troubleshooting: issue spec Step 5

### Step 3: Create `docs/18-migration-guide.md`

**File**: `docs/18-migration-guide.md`

Structure:

```
# 18 — Migration Guide: v1 → v2

## What Changed in v2
  - Brief overview of all changes

## Breaking Changes                        ← Only list changes that actually landed
  ### Auth Required (if 028 landed)
  ### Centralized Config (if 027 landed)
  ### Companion Registration Protocol (if 031 landed)
  ### Headless Mode (if 030 landed)

## Step-by-Step Upgrade
  1. Back up .env
  2. git pull
  3. Update .env from new .env.example
  4. Update dependencies (pip install -r ...)
  5. Update companion extension (npm install && compile)
  6. Verify

## Deprecated Features
  - main.py monolith → split brain + voice (if 006 landed)
  - UIA-based permission handling → companion extension
  - Hardcoded constants → env var config
  - Discovery file IPC → registration protocol

## Port Map Changes
  - Table showing v1 vs v2 port authentication/features
```

**Builder instructions**: Only include migration steps for features that actually exist per Step 1. If auth didn't land, don't tell users to set CYRUS_AUTH_TOKEN. Match reality.

### Step 4: Update root `README.md` project structure

**File**: `README.md` (project root)

Update **only** the Project Structure section (lines 218–230). Add entries for:
- `cyrus2/` directory and its contents (whatever exists from Step 1)
- `Dockerfile` and `docker-compose.yml` (if they exist)
- `docs/` note about 18 docs (updated from current count)

Keep all other sections of root README intact — developer setup, release install, voice commands, hotkeys, hooks, etc. are all still accurate for v2.

### Step 5: Verify file paths and links

```bash
cd /home/daniel/Projects/barf/cyrus

# 1. Every file path in backticks in docs/README.md should exist on disk
grep -oP '`[^`]+\.(py|yml|json|txt|md|ts|toml)`' docs/README.md | tr -d '`' | sort -u | while read f; do
  # Skip paths with placeholders like /absolute/path/
  echo "$f" | grep -q "absolute\|path\|your" && continue
  if [ ! -f "$f" ]; then
    echo "BROKEN PATH: $f"
  fi
done

# 2. Every relative doc link resolves
grep -oP '\./[0-9]+-[^)]+\.md' docs/README.md | while read f; do
  if [ ! -f "docs/${f#./}" ]; then
    echo "BROKEN LINK: $f"
  fi
done

# 3. Migration guide exists
test -f docs/18-migration-guide.md && echo "AC9: OK" || echo "AC9: MISSING"
```

Fix any broken paths or links found.

### Step 6: Verify config table completeness (if applicable)

Only relevant if `cyrus2/cyrus_config.py` exists:

```bash
cd /home/daniel/Projects/barf/cyrus

if [ -f cyrus2/cyrus_config.py ]; then
  echo "=== Env vars in code but not in docs/README.md ==="
  comm -23 \
    <(grep -oP 'CYRUS_\w+' cyrus2/cyrus_config.py | sort -u) \
    <(grep -oP 'CYRUS_\w+' docs/README.md | sort -u)

  echo "=== Env vars in .env.example but not in docs/README.md ==="
  comm -23 \
    <(grep -oP 'CYRUS_\w+' .env.example | sort -u) \
    <(grep -oP 'CYRUS_\w+' docs/README.md | sort -u)
fi
```

Any missing vars must be added to the config table.

### Step 7: Final acceptance criteria spot-check

```bash
cd /home/daniel/Projects/barf/cyrus

# AC1: v2 structure
grep -c "v2\|2\.0\|Architecture" docs/README.md

# AC2: Quick start with both services
grep -c "cyrus_brain" docs/README.md
grep -c "cyrus_voice" docs/README.md

# AC3: Docker section (if applicable)
grep -c "docker compose\|Docker" docs/README.md

# AC6: Extension section
grep -c "Companion Extension\|companion" docs/README.md

# AC9: Migration guide
test -f docs/18-migration-guide.md && echo "OK" || echo "MISSING"

# AC10: File paths match reality — no references to files that don't exist
grep -oP '`[^`]*cyrus2/[^`]+`' docs/README.md | tr -d '`' | while read f; do
  [ ! -f "$f" ] && echo "STALE PATH: $f"
done
```

## Files to Create/Modify

| File | Action | Description |
|---|---|---|
| `docs/README.md` | **Rewrite** | v2 documentation hub — architecture, quick starts, config, auth, extension, health, persistence, troubleshooting, doc index |
| `docs/18-migration-guide.md` | **Create** | v1 → v2 upgrade path — breaking changes, step-by-step migration, deprecated features |
| `README.md` (root) | **Modify** | Update Project Structure section only — add `cyrus2/`, Docker files |

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Documenting features that don't exist yet | Misleading docs, broken instructions | Medium | Step 1 inspection gates every section; omit what's missing |
| File paths in docs don't match disk | Confusing setup | Low | Step 5 verifies all paths exist |
| Config table diverges from `cyrus_config.py` | Users set wrong env vars | Low | Step 6 cross-checks code vs docs |
| Root README rewrite breaks existing content | Loss of user setup instructions | Zero | Only Project Structure section is modified (D5) |
| Migration guide references unimplemented features | Users attempt impossible steps | Medium | Builder adapts guide to match Step 1 findings |
| All Sprint 4–6 features are MISSING (degenerate case) | Minimal docs improvement | Medium | D2 degenerate case protocol — builder still delivers polish + extension docs + minimal migration guide |

## Deltas from Issue Spec

| Issue spec says | Plan changes to | Rationale |
|---|---|---|
| `docs/14-migration-guide.md` | `docs/18-migration-guide.md` | Slot 14 occupied by `14-test-suite.md`; 18 is next available |
| File paths use `cyrus2/cyrus_brain.py` | Main scripts stay at root (`cyrus_brain.py`) | Plans 027–038 don't move main scripts — they create modules in `cyrus2/` and modify root scripts to import from there |
| `CYRUS_BRAIN_HOST` in config table | Use actual var name from `cyrus_config.py` (Plan 027 uses `CYRUS_BRAIN_CONNECT_HOST`) | Plan 027 separates bind host vs connect host; builder should use whatever the code actually defines |
| Write docs against planned architecture | Gate on actual code state | All blocking issues are PLANNED, not COMPLETE — builder must verify what landed |
| AC10 "All file paths updated to cyrus2/" | "All file paths match actual locations on disk" | Main scripts stay at root per D3; `cyrus2/` only contains modules. AC10 reinterpreted as path accuracy, not path relocation. |
