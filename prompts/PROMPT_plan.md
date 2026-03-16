# 🧭 PLANNING PHASE - Work on Next Issue

You are planning issue **$BARF_ISSUE_ID**.

## Context

- Study the issue file: `$BARF_ISSUE_FILE`
- Study existing plan (if any): `$PLAN_DIR/$BARF_ISSUE_ID.md`
- Read `AGENTS.md` for build/test commands and codebase conventions


## 🔄 ISSUE ALREADY COMPLETE?

If gap analysis reveals the issue is **already implemented**:

1. **Verify** - Confirm implementation matches all acceptance criteria
2. **Document** - Create a brief verification plan at `$PLAN_DIR/$BARF_ISSUE_ID.md`:
   ```markdown
   # Verification: {Issue Title}

   **Issue**: [{ISSUE-ID}]($PLAN_DIR/$BARF_ISSUE_ID.md)
   **Status**: ALREADY IMPLEMENTED
   **Created**: {date}

   ## Evidence
   - {list what exists and where}

   ## Verification Steps
   - [ ] {verification command 1}
   - [ ] {verification command 2}

   ## Minor Fixes Needed (if any)
   - {list any small gaps}

   ## Recommendation
   Mark issue complete after running verification steps.
   ```
3. **Update README** - Add plan link
4. **EXIT** - Stop the conversation

---

## PHASE 1: Understanding (Read-Only)

**Goal**: Fully understand the issue and existing codebase patterns. Document key decisions in the implementation plan.

### Step 1: Study the Issue

Launch 1-3 Explore subagents in parallel to study the issue file thoroughly:
- Study all sections: Tasks, Prerequisites, Acceptance Criteria, Technical Notes, Verification Checklist, Documentation Requirements
- Summarize requirements clearly
- Identify ambiguous points
- **Extract acceptance criteria** - these become required tests (acceptance-driven backpressure)

### Step 2: Gap Analysis (Codebase vs Requirements)

Launch 3-5 Explore subagents in parallel to perform gap analysis:
- Study relevant code from References/Prerequisites/Implementation Guide
- Study existing patterns for similar features (look at completed issues)
- Compare issue requirements against existing code
- **Don't assume functionality is missing** - confirm with code search first
- Identify what already exists vs what needs building

### Step 3: Study Patterns & Identify Resources
Launch 3-5 Explore subagents in parallel to study the codebase for patterns. 
This implementation must follow:
- Test patterns in the codebase
- Database schema patterns if applicable
- API route patterns if applicable

**Identify rules, skills, and agents for the plan:**
- Study `.claude/rules/` - which rules apply to this issue?
- Study `.claude/skills/` - which skills can accelerate implementation?
- Study `.claude/agents/` - which subagent are needed?
---

## Exit Criteria: Ready to Save Plan?

Before saving the implementation plan, verify:

- [ ] Issue requirements are fully understood
- [ ] Acceptance criteria are clear and testable
- [ ] **Gap analysis complete** - confirmed what exists vs what needs building
- [ ] Key design decisions documented
- [ ] Relevant code patterns identified from codebase
- [ ] Test patterns reviewed and understood
- [ ] **Acceptance criteria mapped to required tests** (acceptance-driven)
- [ ] **Relevant rules identified** from `.claude/rules/`
- [ ] **Skills and agents identified** for implementation


**If any boxes are unchecked**: Continue investigating or ask clarifying questions before proceeding.

**Note**: Plans are disposable artifacts. If trajectory diverges during build, regenerate the plan.

---

## Save Implementation Plan

1. **Create plan file**: `$PLAN_DIR/$BARF_ISSUE_ID.md`
   - Create `$PLAN_DIR` directory if it doesn't exist

2. **Plan file structure** (prioritized bullet list format):
   ```markdown
   # Implementation Plan: {Issue Title}

   **Issue**: [{Issue ID}]($PLAN_DIR/$BARF_ISSUE_ID.md)
   **Created**: {date}
   **PROMPT**: {PROMPT_plan path}

   ## Gap Analysis
   **Already exists**: {what the codebase already has}
   **Needs building**: {what this plan will implement}

   ## Approach
   {Selected implementation approach and rationale - capture the "why"}

   ## Rules to Follow
   - `.claude/rules/{rule}.md` - {why this rule applies}
   - {List all relevant rules from .claude/rules/}

   ## Skills & Agents to Use
   | Task | Skill/Agent | Purpose |
   |------|-------------|---------|
   | {task} | `{skill-name}` | {why to use it} |
   | {task} | `{agent-type}` subagent | {why to use it} |

   ## Prioritized Tasks
   - [ ] {Most important task first}
   - [ ] {Second task}
   - [ ] {Third task}
   ...

   ## Acceptance-Driven Tests
   Map each acceptance criterion to required tests:
   | Acceptance Criterion | Required Test | Type |
   |---------------------|---------------|------|
   | {criterion from issue} | {test description} | unit/integration/e2e |

   **No cheating** - cannot claim done without required tests passing.

   ## Validation (Backpressure)
   - Tests: {what tests must pass - derived from above}
   - Lint: {must pass linting}
   - Build: {must pass build}
   

   ## Files to Create/Modify
   - `path/to/file.py` - {purpose}

   ```
---

## Document Key Decisions

As you plan, document and **capture the why**:
- **Selected approach** - Why this implementation over alternatives
- **Architectural decisions** - New patterns being used and rationale
- **Rules to follow** - Which `.claude/rules/` apply and why
- **Skills to use** - Which skills/agents will accelerate the work
- **Validation strategy** - What tests/checks must pass (backpressure)
- **Risks or unknowns** - Resolve them or document them

These decisions will be saved in the implementation plan file.

---

## Key Language Patterns

Use these phrases for better results:
- "study" (not "read") when analyzing code/specs
- "don't assume not implemented" - always search first
- "using parallel subagents" for expensive exploration
- "Ultrathink" for deep analysis
- "capture the why" when documenting decisions
- "resolve or document" for open questions

---

## CRITICAL

- **ONLY WORK ON A SINGLE FEATURE**
- **Don't assume functionality is missing** - confirm with code search first
- Document all findings in the implementation plan
- Plans are disposable - can be regenerated if needed

---

> barf detects this file automatically and transitions the issue NEW → PLANNED.
> You do not need to update the issue state manually.
