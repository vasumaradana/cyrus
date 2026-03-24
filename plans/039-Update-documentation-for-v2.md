# Implementation Plan: Update Documentation for v2

**Issue**: [039-Update-documentation-for-v2](/home/daniel/Projects/barf/cyrus/cyrus/issues/039-Update-documentation-for-v2.md)
**Created**: 2026-03-18
**PROMPT**: `/home/daniel/Projects/barf/cyrus/prompts/PROMPT_plan.md`

## Gap Analysis

**Already exists**:
- `docs/README.md` — Table of contents for 17 doc files, basic v1 Quick Start (split + monolith), reading order
- `README.md` (root) — Comprehensive v1 setup: clone, venv, companion extension build, hook config, release install, networking, commands, hotkeys, project structure. All paths reference root-level files (not cyrus2/)
- `docs/13-docker-containerization.md` — Docker implementation *blueprint* (phases 1-6, proposed Dockerfile/compose) but NO actual Docker files exist
- `docs/15-recommendations.md` — Lists auth, config, health checks as future features
- `docs/08-companion-extension.md` — VS Code extension docs (IPC, registration, focus)
- `cyrus2/.env.example` — 67-line comprehensive config reference with all env vars
- `cyrus2/cyrus_config.py` — 131 lines, all env vars with defaults and comments
- `cyrus-companion/` — Working extension (extension.ts, package.json) but NO README

**Needs building**:
1. **docs/README.md** — Major rewrite: add v2 architecture, Traditional Quick Start (cyrus2/ paths), Docker Quick Start, Configuration reference table, Authentication section, Extension setup, Health checks, Session persistence, Troubleshooting
2. **Root README.md** — Update all file paths from root to `cyrus2/`, update project structure section, add cyrus2 directory
3. **Migration guide** — Create `docs/18-migration-guide.md` (note: `14` is taken by test-suite)
4. **Minor**: docs/README.md TOC needs new entries

## Approach

Focus on `docs/README.md` as the primary deliverable since it's the main user-facing documentation. The root `README.md` also needs path updates. The migration guide gets a new doc number (18) since 14 is already `14-test-suite.md`.

**Key decision**: Docker Quick Start will document the *planned* Docker workflow from `13-docker-containerization.md` since actual Docker files don't exist yet — clearly marked as "coming soon" or referencing the design doc. All other sections (auth, config, health, session) will be documented based on actual code in `cyrus2/`.

**Why this approach**: The issue explicitly says "Blocked By: All Sprint 4-6 issues" — some features (Docker) are still in-progress. We document what's implemented and mark planned features appropriately.

## Rules to Follow
- No `.claude/rules/` files exist (directory is empty)

## Skills & Agents to Use
| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Write docs/README.md sections | `technical-writer` agent | Specialized documentation writing |
| Cross-reference accuracy | `docs-cross-referencing` skill | Ensure all doc links and references are correct |
| Verify config table | `Explore` subagent | Cross-check cyrus_config.py against documentation |

## Prioritized Tasks

- [x] **1. Rewrite `docs/README.md`** — This is the primary deliverable
  - [x] 1a. Update Table of Contents with new doc entries (migration guide)
  - [x] 1b. Add Architecture Overview section (monolithic → split brain + voice)
  - [x] 1c. Add Cyrus 2.0 Structure section (cyrus2/ directory layout)
  - [x] 1d. Rewrite Quick Start — Traditional Mode (cyrus2/ paths, .env setup, brain + voice)
  - [x] 1e. Add Quick Start — Docker Mode (compose up, port mappings, host.docker.internal)
  - [x] 1f. Add Configuration section — env vars reference table from cyrus_config.py
  - [x] 1g. Add Authentication section (CYRUS_AUTH_TOKEN setup, token generation)
  - [x] 1h. Add VS Code Companion Extension Setup section
  - [x] 1i. Add Health Checks and Monitoring section
  - [x] 1j. Add Session Persistence section
  - [x] 1k. Add Troubleshooting section (brain/Docker, extension, hook issues)
  - [x] 1l. Update Reading Order for v2

- [x] **2. Update root `README.md`**
  - [x] 2a. Update all file paths to reference `cyrus2/` directory
  - [x] 2b. Update Project Structure section to include cyrus2/ layout
  - [x] 2c. Add CYRUS_AUTH_TOKEN to environment setup
  - [x] 2d. Update Quick Start instructions to use cyrus2/ paths
  - [x] 2e. Add Docker mode mention with link to docs/README.md

- [x] **3. Create `docs/18-migration-guide.md`**
  - [x] 3a. v1 → v2 directory changes (root → cyrus2/)
  - [x] 3b. Configuration migration (.env changes, new env vars)
  - [x] 3c. main.py deprecation notice
  - [x] 3d. Hook path updates
  - [x] 3e. New features summary (auth, headless, config module)

- [x] **4. Verification pass**
  - [x] 4a. All file paths in docs reference cyrus2/ correctly
  - [x] 4b. Configuration table matches cyrus_config.py exactly (all 18 env vars verified)
  - [x] 4c. All internal doc links work (all 18 doc files verified)
  - [x] 4d. Quick Start steps are accurate and followable

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| docs/README.md updated with new v2 structure | Verify TOC includes all sections, cyrus2/ paths used | manual review |
| Quick Start includes standalone brain + voice modes | Verify Traditional Quick Start section exists with cyrus2/ commands | manual review |
| Docker Quick Start section added | Verify Docker section with compose up, port mappings | manual review |
| Configuration section documents all env vars | Cross-check table against `cyrus2/cyrus_config.py` and `cyrus2/.env.example` | script/grep |
| Authentication section explains TOKEN setup | Verify CYRUS_AUTH_TOKEN docs with generation command | manual review |
| Extension setup guide included | Verify companion extension build + install steps | manual review |
| Health check endpoint documented | Verify health check section exists | manual review |
| Session persistence explained | Verify CYRUS_STATE_FILE and persistence docs | manual review |
| Migration guide from v1 to v2 | Verify docs/18-migration-guide.md exists with upgrade path | file existence |
| All file paths updated to cyrus2/ | Grep for old root-level paths (e.g., bare `cyrus_brain.py` without `cyrus2/`) | grep check |

**No cheating** — cannot claim done without all acceptance criteria verified.

## Validation (Backpressure)

- **Config accuracy**: grep cyrus_config.py for all env vars, verify each appears in docs config table
- **Path correctness**: grep docs for bare `cyrus_brain.py` / `cyrus_voice.py` references that should be `cyrus2/`
- **Link validity**: verify all `./` relative links in docs/README.md point to existing files
- **No build/lint needed**: This is a docs-only issue

## Files to Create/Modify

- `docs/README.md` — Major rewrite: add all v2 sections (architecture, quick starts, config, auth, extension, health, session, troubleshooting)
- `README.md` (root) — Update paths to cyrus2/, add Docker mention, update project structure
- `docs/18-migration-guide.md` — New file: v1 to v2 migration guide

## Key Reference Files (read during implementation)

- `cyrus2/cyrus_config.py` — Source of truth for all env vars and defaults
- `cyrus2/.env.example` — Template with all config options
- `docs/13-docker-containerization.md` — Docker design (for Docker Quick Start content)
- `docs/08-companion-extension.md` — Extension details (for extension setup section)
- `cyrus-companion/package.json` — Extension metadata
- `cyrus2/cyrus_brain.py` — Brain service entry point
- `cyrus2/cyrus_voice.py` — Voice service entry point
