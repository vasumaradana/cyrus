# 🔨 BUILD PHASE - Implementation

**WRITE MODE**: This phase focuses on implementation. Build and commit code with full tooling available.

## Context

## Selection Criteria

Pick the next issue by:
1. **Sprint order** - Complete Sprint 0 before Sprint 1, etc.
2. **Has a plan** - Choose issues WITH a plan link in the README (Plan column)
3. **Dependencies** - Check issue `## Dependencies` section
4. **Status** - Choose first issue with incomplete Tasks

---

## PHASE 1: Load Context

**Goal**: Study the issue and plan to understand what to build.

### Step 0: Study the Issue AND Plan

**First, study the issue file** - `./planning/phase-1/{ISSUE-ID}.md`:
1. **Description** - understand what we're building and why
2. **Tasks** - the original work breakdown
3. **Acceptance Criteria** - what "done" looks like (tests must prove these)
4. **Technical Notes** - implementation details, code examples, config snippets
5. **Prerequisites** - required reading, skills needed
6. **Implementation Guide** - step-by-step instructions, common pitfalls
7. **Dependencies** - what must be completed first

**Then, study the plan file** - `./planning/plans/{ISSUE-ID}.md`:
1. **Gap Analysis** - what exists vs what needs building
2. **Prioritized Tasks** - your work queue (derived from issue tasks)
3. **Acceptance-Driven Tests** - tests MUST exist and pass
4. **Validation section** - checks MUST pass (backpressure)
5. **Files to Create/Modify** - scope of changes

The issue is the **source of truth** for requirements. The plan is your **execution strategy**.

### Step 1: Choose Most Important Task

From the plan's **Prioritized Tasks**, choose the most important incomplete item.

**Don't assume functionality is missing** - search the codebase before making changes.

---

## PHASE 2: Implementation (Make Changes)

**Goal**: Implement with tests first, update docs as you go, commit clean code.

### Step 2: Test-Driven Development

**CRITICAL**: Write tests FIRST per `testing.md` rules

**Acceptance-Driven Tests** (from plan):
- Every acceptance criterion in the plan MUST have a corresponding test
- Write these tests FIRST - they define "done"
- **No cheating** - cannot claim done without these tests passing

Use `everything-claude-code:tdd-guide` skill to scaffold test structure.

**Coverage requirements:**
- Overall: 70%
- Auth/security code: 90%

**Required test categories:**
- **Acceptance tests**: From plan's Acceptance-Driven Tests table
- **Happy path**: 2+ tests (success cases)
- **Error cases**: 3-4 tests (all failure modes)
- **Edge cases**: 2-3 tests (boundary conditions)
- **Organization isolation**: 70% of integration tests must verify isolation
- **Corner cases**: 1-2 tests (unusual states)

### Step 3: Implement Features

Use skills proactively (see Skills section below):
- Launch up to 3 subagents in parallel for independent file operations
- ✅ **Check Task boxes in plan** as you complete each one (don't batch)
- Add inline code comments explaining "why", not "what"
- Use `vertical-slice` skill for complete features (DB→API→UI)
- **If functionality is missing, it's your job to add it** per specifications

### Step 4: Backpressure - Run Validation

Launch **only 1 subagent** for build/tests (validation gates):

```bash
pnpm typecheck   # Must pass
pnpm lint        # Must pass
pnpm test        # Must pass
pnpm build       # Must pass
```

- Fix any failures before proceeding - this is backpressure steering you
- ✅ **Check Acceptance Criteria boxes** when verified
- ✅ **Check Verification Checklist boxes** when completed

### Step 5: Update the Plan

**Immediately update** `./planning/plans/{ISSUE-ID}.md`:
- When discovering issues → add them to the plan
- When resolving issues → remove them from the plan
- When completing tasks → check them off
- Keep the plan up to date as single source of truth

---

## PHASE 3: Documentation & Commit

**Goal**: Update documentation and commit clean code

### Step 6: Update Documentation

- Update the plan file `./planning/plans/{ISSUE-ID}.md` - mark completed tasks
- Update `./planning/phase-1/README.md` with progress (Tasks Completed column)
- Note any discoveries, bugs, or deviations in the plan's Open Questions
- Update `./CLAUDE.md` with operational learnings (if applicable)

### Step 7: Version Bump

Update packages (api, web, shared, docs) `package.json` version per semantic versioning:
- **Patch**: bug fixes only
- **Minor**: new features, backward compatible
- **Major**: breaking changes

Update TypeDoc `@since` tags with new package version

### Step 8: Commit

When all validation passes (tests, typecheck, lint, build):

- Run `git status` to review changes
- Run `git diff` to verify changes are correct
- Commit with descriptive message following repo conventions
- Include `Co-Authored-By: Claude <noreply@anthropic.com>`
- Push changes to repo
---

## Exit Criteria: Implementation Done?

Before considering work complete, verify:

**Backpressure (all must pass):**
- [ ] `pnpm typecheck` passes
- [ ] `pnpm lint` passes
- [ ] `pnpm test` passes
- [ ] `pnpm build` passes
- [ ] Coverage meets or exceeds thresholds (70%+ overall)
- [ ] Organization isolation tests passing (70% of integration tests)
- [ ] **All acceptance-driven tests exist and pass** (no cheating)

**Plan completion:**
- [ ] All Prioritized Tasks in plan checked off
- [ ] All Acceptance Criteria boxes checked
- [ ] All Verification Checklist boxes checked
- [ ] Plan file updated with completed tasks
- [ ] Open Questions resolved or documented

**Documentation & commit:**
- [ ] README progress updated
- [ ] Version bumped
- [ ] Code committed with clean history
- [ ] Hard Requirements checklist completed

**If any boxes unchecked**: Continue work or document blockers before marking done.

---

## Skills for Build Phase

| When | Skill | Purpose |
|------|-------|---------|
| Start work (if refining approach) | `/brainstorming` | Refine design if needed |
| TDD scaffold | `everything-claude-code:tdd-guide` | Test structure, patterns |
| Backend development | `argus-iq-backend` | Backend patterns, multi-org, Fastify, Drizzle, auth, jobs |
| Frontend development | `argus-iq-frontend` | Frontend patterns, React 19, forms, state, TanStack, shadcn/ui |
| DB migrations | `drizzle-migration` | Multi-org patterns, safe migrations |
| API routes | `fastify-route` | Zod validation, OpenAPI docs |
| React components | `react-component` | shadcn/ui, TanStack Query |
| Zod schemas | `zod-schema` | Type-safe validation, single source |
| Full feature slice | `vertical-slice` | Complete DB→API→UI in one pass |
| Code review before done | `superpowers:requesting-code-review` | Verify work meets requirements |

---

## Hard Requirements Checklist

Violations block merge. Check before committing:

- [ ] Follow ALL rules in `.claude/rules/` (especially `hard-requirements.md`)
- [ ] Use TDD workflow - tests first, then implementation
- [ ] Verify organization isolation in 70% of integration tests
- [ ] No `any` types - use `unknown` + Zod validation
- [ ] Zod 4.x (not 3.x) for all schema validation
- [ ] React 19.x for frontend code
- [ ] TypeScript 5.7+ strict mode enabled
- [ ] Schema-first development (types from Zod, not vice versa)
- [ ] No hardcoded secrets - use environment variables
- [ ] Passwords hashed with Argon2id
- [ ] Input validation at boundaries only (Zod)
- [ ] All exported functions have TypeDoc comments
- [ ] Sensitive data never logged
- [ ] Error responses standardized (code + message + requestId)
- [ ] Response validation with Zod in API handlers
- [ ] Build passes with zero errors
- [ ] Test coverage meets thresholds

---

TODO: NNO ASKING DURING BUILD
## When to Ask Questions During Build

Ask if you encounter:
- **Blocker** - Cannot proceed without clarification
- **Multiple valid approaches** - Need guidance on tradeoff
- **Requirement conflict** - Acceptance criteria conflict with each other
- **Architectural uncertainty** - How to fit feature into existing system

If unsure, ask early rather than build wrong solution.

---

## Anti-Patterns to Avoid

❌ **Skipping issue study** - issue has technical notes, implementation guide, acceptance criteria
❌ **Skipping plan study** - plan has gap analysis, prioritized tasks, files to modify
❌ **Assuming not implemented** - search codebase before building
❌ Checking boxes at the end (check incrementally as work completes)
❌ Writing implementation before tests (TDD required)
❌ Using multiple subagents for validation (only 1 for build/tests)
❌ Skipping organization isolation tests (70% required)
❌ Updating documentation after commit (update before)
❌ Committing without validation passing (backpressure must pass)
❌ Not updating plan when discovering issues (keep it current)
❌ Fighting a bad plan (regenerate it instead)
❌ Not using skills when applicable (use proactively)
❌ Partial task completion checked as done (only check when fully complete)

---

## If Validation Fails (Backpressure)

Validation failures are **backpressure steering you** toward correct implementation:

1. **Study the failure** - Read test/lint/type output carefully
2. **Fix the issue** - Address the actual problem (don't work around it)
3. **Re-validate** - Run validation again to verify fix
4. **Update plan** - Document what was discovered
5. **Proceed** - Continue implementation

Backpressure is your friend - it prevents bad code from shipping.

If the same failure recurs, use `superpowers:systematic-debugging` skill.

---

## If Trajectory Diverges - Regenerate Plan

Plans are disposable. If during implementation you discover:
- Requirements are fundamentally misunderstood
- Major architectural issue not identified in planning
- Fundamental blocker preventing completion
- Plan no longer reflects reality

**Regenerate the plan** - return to PROMPT_plan.md, clarify the issue, create a new plan.

Don't fight a bad plan. Regenerate it.

---

## Key Language Patterns

Use these phrases for better results:
- "study the issue" - for requirements, technical notes, implementation guide
- "study the plan" - for gap analysis, prioritized tasks, execution strategy
- "don't assume not implemented" - search codebase first
- "only 1 subagent for build/tests" - validation is serial
- "if functionality is missing, add it" - per specifications
- "keep the plan up to date" - single source of truth
- "resolve or document" for open questions

---

## CRITICAL

- **ONLY WORK ON A SINGLE FEATURE**
- **Study the issue first** - requirements, technical notes, implementation guide
- **Study the plan second** - gap analysis, prioritized tasks, files to modify
- **Don't assume not implemented** - search codebase first
- Tests MUST pass before committing (backpressure)
- Update plan IMMEDIATELY when discovering issues
- Boxes checked INCREMENTALLY (not at end)
- Documentation BEFORE commit (not after)
- Hard Requirements are non-negotiable
- Plans are disposable - regenerate if trajectory diverges
