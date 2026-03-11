# Cyrus 2.0 Rewrite — Sprint Plan Overview

All rewrite code goes in `./cyrus2/`. Issues reference planning docs in `./docs/` (12-17).

## Sprint Summary

| Sprint | Name | Issues | Focus |
|--------|------|--------|-------|
| 0 | Tooling & Foundation | 001-004 | pyproject.toml, ruff, dev deps, pin versions |
| 1 | Core Refactor | 005-008 | Extract cyrus_common.py, deprecate main.py, dispatch table |
| 2 | Quality & Safety | 009-017 | Logging, thread safety, error handling, security |
| 3 | Test Suite | 018-026 | pytest setup, 4 tiers of tests (~130 cases) |
| 4 | Configuration & Auth | 027-029 | Config module, TCP auth, hook configurability |
| 5 | Docker & Extension | 030-035 | Headless mode, companion registration, Dockerfile |
| 6 | Polish | 036-039 | Health checks, Whisper config, persistence, docs |

## Dependency Graph

```
Sprint 0 (001-004) ─── no blockers
    │
    ▼
Sprint 1 (005-008) ─── 002 (formatted code to refactor)
    │
    ├──▶ Sprint 2 (009-017) ─── 005 (common code extracted)
    │       │
    │       ▼
    │   Sprint 3 (018-026) ─── 009 (logging), 005 (common)
    │
    ▼
Sprint 4 (027-029) ─── 005 (common), 009 (logging)
    │
    ▼
Sprint 5 (030-035) ─── 027 (config), 005 (common)
    │
    ▼
Sprint 6 (036-039) ─── 030 (headless), 027 (config)
```

## Issue Index

### Sprint 0 — Tooling & Foundation
| # | Title | Priority | Blocked By | Ref |
|---|-------|----------|------------|-----|
| 001 | Create pyproject.toml with ruff config | High | None | doc 17 |
| 002 | Run ruff autofix and format | High | 001 | doc 17 |
| 003 | Create requirements-dev.txt | High | None | docs 14, 17 |
| 004 | Pin all production dependencies | High | None | doc 12 H5 |

### Sprint 1 — Core Refactor
| # | Title | Priority | Blocked By | Ref |
|---|-------|----------|------------|-----|
| 005 | Extract shared code into cyrus_common.py | Critical | 002 | doc 12 C3 |
| 006 | Deprecate main.py monolith | Critical | 005 | doc 15 #2 |
| 007 | Break up _execute_cyrus_command into dispatch table | Critical | 005 | doc 12 C1 |
| 008 | Break up main() functions into subsystems | Critical | 005 | doc 12 C2 |

### Sprint 2 — Quality & Safety
| # | Title | Priority | Blocked By | Ref |
|---|-------|----------|------------|-----|
| 009 | Create cyrus_log module | High | None | doc 16 |
| 010 | Replace prints in cyrus_brain.py (66) | High | 009 | doc 16 |
| 011 | Replace prints in cyrus_voice.py (32) | High | 009 | doc 16 |
| 012 | Replace prints in cyrus_server.py (4) | High | 009 | doc 16 |
| 013 | Add threading locks to shared state | Critical | 005 | doc 12 C4 |
| 014 | Replace broad exception handlers (81) | High | 009 | doc 12 H1 |
| 015 | Add focus verification before keystrokes | High | None | doc 12 H2 |
| 016 | Fix file handle leak | High | None | doc 12 H4 |
| 017 | Add permission approval logging | High | 009 | doc 12 H3 |

### Sprint 3 — Test Suite
| # | Title | Priority | Blocked By | Ref |
|---|-------|----------|------------|-----|
| 018 | Setup pytest framework with conftest | Critical | 003 | doc 14 |
| 019 | Write test_text_processing.py (~30 cases) | High | 005, 018 | doc 14 Tier 1 |
| 020 | Write test_project_matching.py (~26 cases) | High | 005, 018 | doc 14 Tier 1 |
| 021 | Write test_fast_command.py (~25 cases) | High | 005, 018 | doc 14 Tier 1 |
| 022 | Write test_hook.py (~12 cases) | High | 018 | doc 14 Tier 2 |
| 023 | Write test_permission_keywords.py (~12 cases) | Medium | 005, 018 | doc 14 Tier 3 |
| 024 | Write test_vad_logic.py (~15 cases) | Medium | 005, 018 | doc 14 Tier 3 |
| 025 | Write test_chat_extraction.py (~10 cases) | Medium | 005, 018 | doc 14 Tier 4 |
| 026 | Write test_companion_protocol.py (~8 cases) | Medium | 005, 018 | doc 14 Tier 4 |

### Sprint 4 — Configuration & Auth
| # | Title | Priority | Blocked By | Ref |
|---|-------|----------|------------|-----|
| 027 | Create centralized config module | High | 005 | docs 12 M1/M2, 15 #5 |
| 028 | Add TCP authentication | High | 027 | doc 15 #3 |
| 029 | Make hook brain host configurable | Medium | None | doc 13 Phase 5 |

### Sprint 5 — Docker & Extension
| # | Title | Priority | Blocked By | Ref |
|---|-------|----------|------------|-----|
| 030 | Add headless mode to brain | Critical | 005, 027 | doc 13 Phase 1 |
| 031 | Add companion extension registration | High | 030 | doc 13 Phase 2 |
| 032 | Add extension focus tracking | High | 031 | doc 13 Phase 2 |
| 033 | Add extension permission handling | High | 031 | doc 13 Phase 2 |
| 034 | Add brain registration listener | High | 030 | doc 13 Phase 3 |
| 035 | Create Dockerfile and compose | High | 030 | doc 13 Phase 4 |

### Sprint 6 — Polish
| # | Title | Priority | Blocked By | Ref |
|---|-------|----------|------------|-----|
| 036 | Add health check endpoint | Medium | 030 | doc 15 #6 |
| 037 | Add configurable Whisper model | Medium | 027 | doc 15 #9 |
| 038 | Add session state persistence | Medium | 005 | doc 15 #10 |
| 039 | Update documentation for v2 | Medium | All | All docs |

## Key Metrics
- **39 issues** across 7 sprints
- **~130 test cases** planned
- **~2,000 lines** of duplication eliminated (issue 005)
- **218 print() calls** replaced with structured logging (issues 009-012)
- **81 broad exception handlers** fixed (issue 014)
- **6 race condition variables** protected (issue 013)
