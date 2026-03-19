---
id=031-Add-companion-extension-registration
title=Plan: Issue 031 — Add Companion Extension Registration
state=PLANNED
issue=031-Add-companion-extension-registration
---

# Plan: Issue 031 — Add Companion Extension Registration

**Issue**: [031-Add-companion-extension-registration](/home/daniel/Projects/barf/cyrus/cyrus/issues/031-Add-companion-extension-registration.md)
**Created**: 2026-03-18
**PROMPT**: `/home/daniel/Projects/barf/cyrus/cyrus/prompts/PROMPT_plan.md`

## Gap Analysis

**Already exists**:
- `cyrus-companion/src/extension.ts` — full extension with inbound server, submit pipeline, platform-adaptive networking (381 lines). Currently returns `Promise<void>` from `startServer()`, has NO brain connection logic.
- `cyrus-companion/package.json` — extension manifest with only `cyrusCompanion.focusCommand` setting. No `brainHost` or `brainPort` settings.
- `cyrus-companion/out/brain-connection.js` — **compiled JS reference** of the BrainConnectionManager class (177 lines). Full implementation ready to reverse-compile.
- `cyrus-companion/out/brain-connection.test.js` — **compiled JS reference** of comprehensive Jest tests (362 lines, 14 test cases).
- `cyrus-companion/out/extension.js` — **compiled JS reference** showing integration: imports BrainConnectionManager, creates/destroys in activate/deactivate, `startServer()` returns `Promise<number>`.
- `cyrus-companion/out/__mocks__/vscode.js` — compiled VS Code API mock for Jest.

**Needs building**:
1. `cyrus-companion/src/brain-connection.ts` — TypeScript source for BrainConnectionManager class (reverse-compile from `out/brain-connection.js`)
2. `cyrus-companion/src/brain-connection.test.ts` — TypeScript test source (reverse-compile from `out/brain-connection.test.js`)
3. `cyrus-companion/src/__mocks__/vscode.ts` — TypeScript mock source (reverse-compile from `out/__mocks__/vscode.js`)
4. Update `cyrus-companion/src/extension.ts` — integrate BrainConnectionManager (import, create, destroy, handleBrainMessage stub, change startServer return type)
5. Update `cyrus-companion/package.json` — add `brainHost` and `brainPort` settings + Jest devDependencies + Jest config
6. `startServer()` signature change: `Promise<void>` → `Promise<number>` (return listenPort for registration message)

## Approach

**Strategy: Reverse-compile from existing JS output.** The compiled `out/` directory already contains the exact working implementation. Write TypeScript source files that compile to match. This is low-risk because we have a reference implementation.

**Key architectural decision**: BrainConnectionManager is extracted into its own module (`brain-connection.ts`) rather than inlined in `extension.ts`. This enables unit testing without a live VS Code host — callers pass in a logger interface and config-getter function rather than importing vscode directly. This pattern is already established in the compiled output.

**startServer() signature change**: Currently returns `Promise<void>`, must return `Promise<number>` (the listen port). On Windows TCP, returns the actual bound port (8768-8778 range). On Unix sockets, returns 0 (port not meaningful). The brain connection needs this port in the registration message.

**Why not inline in extension.ts**: The compiled output shows the class is in its own module. This is better for testability — Jest can mock `net` without involving VS Code APIs.

## Rules to Follow

- `.claude/rules/` — currently empty, no custom rules
- Follow existing codebase conventions: zero runtime npm deps, Node.js built-ins + VS Code API only
- TypeScript strict mode (`tsconfig.json` has `strict: true`)
- Line-delimited JSON protocol (`\n` separator)
- Match the compiled JS output patterns exactly

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Create brain-connection.ts | `general-purpose` subagent | Write TypeScript from compiled JS reference |
| Create test files | `general-purpose` subagent | Write Jest tests from compiled JS reference |
| Update extension.ts | `general-purpose` subagent | Integrate BrainConnectionManager |
| Verify build | `general-purpose` subagent | Run `npm run compile` and Jest tests |

## Prioritized Tasks

- [x] **T1. Add settings and Jest config to package.json** — Add `cyrusCompanion.brainHost` (string, default "localhost") and `cyrusCompanion.brainPort` (integer, default 8770) to `contributes.configuration.properties`. Add Jest devDependencies (`jest`, `ts-jest`, `@types/jest`). Add `jest` config section and `test` script.
- [x] **T2. Create `src/__mocks__/vscode.ts`** — Minimal VS Code API mock for Jest. Exports: workspace (with getConfiguration mock), window (with createOutputChannel mock), commands, env (with clipboard).
- [x] **T3. Create `src/brain-connection.ts`** — BrainConnectionManager class with all required fields. Logger/BrainConfig interfaces exported.
- [x] **T4. Create `src/brain-connection.test.ts`** — 16 Jest tests (14 from reference + 2). Used `jest.mock('net', factory)` pattern to work around Node.js non-configurable property issue (neither direct assignment nor jest.spyOn work on Node.js module exports).
- [x] **T5. Update `src/extension.ts`** — Integration complete: startServer returns Promise<number>, activate creates BrainConnectionManager after server starts, destroy called in dispose/deactivate, handleBrainMessage stub added.
- [x] **T6. Compile** — `npm run compile` passes with zero errors
- [x] **T7. Run tests** — All 16 Jest tests pass

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| Extension connects to `brainHost:8770` on activation | `connects to configured brainHost and brainPort` | unit |
| Sends `{"type": "register", ...}` message | `sends registration message on successful connection` | unit |
| Connection status logged to output channel | `logs connected message to output channel` | unit |
| Auto-reconnect: initial 1s backoff | `schedules reconnect after disconnect with initial 1s backoff` | unit |
| Auto-reconnect: doubles (1s → 2s → 4s) | `doubles backoff on each subsequent disconnect` | unit |
| Auto-reconnect: cap at 30s | `caps backoff at 30s maximum` | unit |
| Backoff resets on reconnection success | `resets backoff to 1s on successful reconnection` | unit |
| New settings: brainHost default localhost, brainPort default 8770 | `uses defaults localhost:8770 when config returns undefined` | unit |
| Persistent connection: no reconnect after destroy | `does not reconnect after destroy() is called` | unit |
| Persistent connection: destroy cancels timer | `destroy() cancels a pending reconnect timer` | unit |
| Error handling: reconnect on error | `schedules reconnect on connection error` | unit |
| Error handling: disconnect logged | `logs disconnect message when connection closes` | unit |
| Incoming messages dispatched | `dispatches valid JSON messages to the message handler` | unit |
| Multi-chunk buffering works | `handles multi-chunk messages (buffering)` | unit |
| Invalid JSON handled gracefully | `logs invalid JSON from brain without crashing` | unit |
| Received message type logged | `logs received message type` | unit |

**No cheating** — cannot claim done without all 16 tests passing (14 from reference + 2 additional coverage).

## Validation (Backpressure)

- **Tests**: All Jest unit tests in `brain-connection.test.ts` must pass
- **Lint**: TypeScript strict mode compilation must succeed with zero errors
- **Build**: `npm run compile` must succeed
- **Manual verification**: Extension loads without errors in VS Code (output channel shows "[Brain] Connected" or "[Brain] Reconnecting")

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| **Create** | `cyrus-companion/src/brain-connection.ts` | BrainConnectionManager class (~120 lines TS) |
| **Create** | `cyrus-companion/src/brain-connection.test.ts` | Jest tests (~250 lines TS) |
| **Create** | `cyrus-companion/src/__mocks__/vscode.ts` | VS Code API mock (~40 lines TS) |
| **Modify** | `cyrus-companion/src/extension.ts` | Brain connection integration (~25 lines changed/added) |
| **Modify** | `cyrus-companion/package.json` | Settings + Jest config (~25 lines added) |

## Key Technical Details

- **Registration message format**: `{"type": "register", "workspace": "...", "safe": "...", "port": ...}\n`
- **Backoff sequence**: 1000ms → 2000ms → 4000ms → 8000ms → 16000ms → 30000ms (capped)
- **Logger interface**: `{ appendLine(msg: string): void }` — compatible with VS Code OutputChannel
- **Config getter**: `() => { brainHost: string, brainPort: number }` — reads VS Code settings lazily
- **Port value**: TCP port on Windows (8768-8778 range), 0 on Unix (socket-based, port not meaningful)
- **handleBrainMessage**: Stub for now — will be implemented in Issues 032/033
- **Compiled JS reference files** in `out/` directory serve as the source of truth for implementation
