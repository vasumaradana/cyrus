# Implementation Plan: Add Extension Focus Tracking

**Issue**: [032-Add-extension-focus-tracking](/home/daniel/Projects/barf/cyrus/issues/032-Add-extension-focus-tracking.md)
**Created**: 2026-03-18
**PROMPT**: `.claude/agents/` (fullstack-developer or frontend-developer subagent)

## Gap Analysis

**Already exists**:
- `cyrus-companion/src/extension.ts` — main extension with `activate()`, output channel (`out`), workspace name extraction, `context.subscriptions` pattern
- `cyrus-companion/out/brain-connection.js` — compiled `BrainConnectionManager` class with `connect()`, `destroy()`, auto-reconnect, message dispatch (from Issue 031 — compiled reference only, TypeScript source not yet written)
- `cyrus-companion/out/extension.js` — compiled extension that already integrates `BrainConnectionManager` with `brainManager` variable, `handleBrainMessage` stub, and proper lifecycle (dispose/destroy). This is the **target state for Issue 031** and serves as our reference.
- `cyrus-companion/out/brain-connection.test.js` — compiled Jest tests for BrainConnectionManager (12 test cases)
- No test framework configured in `package.json` yet (no Jest dependency, no test script)

**Needs building** (for Issue 032 specifically):
1. **Focus tracking listener** — `vscode.window.onDidChangeWindowState` in `activate()`
2. **Send focus/blur messages** — write `{"type":"focus",...}` or `{"type":"blur",...}` to brain via `BrainConnectionManager`
3. **`send()` method on BrainConnectionManager** — the compiled class has no public `send(msg)` method; only `write()` directly on the internal socket in `onConnected()`. Need to add a `send(msg: object): boolean` method.
4. **Debounce** — prevent hammering brain on rapid focus switches (100ms threshold)
5. **Guard against null connection** — only send if brainManager exists and is connected
6. **Tests** — unit tests for focus tracking behavior

**IMPORTANT dependency note**: Issue 031 (brain connection TS source) is a prerequisite. The compiled `out/` JS serves as the reference implementation. If 031 isn't built yet when we implement 032, we need the `BrainConnectionManager` class with a `send()` method available. The plan assumes 031 is done or we implement the `send()` method as part of 032.

## Approach

**Selected approach**: Add focus tracking as a small, focused addition to `extension.ts`. Add a `send()` method to `BrainConnectionManager` to encapsulate writing to the socket (rather than exposing the raw socket).

**Why this approach**:
- Follows the existing pattern where `BrainConnectionManager` owns the socket and encapsulates protocol details
- Debounce at 100ms is simple and avoids adding external dependencies (matches issue's suggestion)
- Sending only when connection is active prevents errors naturally — `send()` returns false if not connected
- Registering listener in `context.subscriptions` ensures proper cleanup

**Alternative considered**: Writing directly to `brainManager.socket` — rejected because it breaks encapsulation and the socket may not exist if disconnected.

## Rules to Follow
- `.claude/rules/` — directory is empty; no project-specific rules to follow
- Follow existing code style: TypeScript strict, zero runtime npm deps, Node built-ins + VS Code API only

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Implement focus tracking | `fullstack-developer` subagent | Write TypeScript code for extension.ts changes |
| Add send() to BrainConnectionManager | `fullstack-developer` subagent | Modify brain-connection.ts (if 031 source exists) |
| Write tests | `fullstack-developer` subagent | Jest unit tests following existing test patterns |
| Review implementation | `code-reviewer` subagent | Validate quality and edge cases |

## Prioritized Tasks

- [x] **1. Add `send()` method to BrainConnectionManager** — Add `send(msg: object): boolean` that JSON-serializes and writes to socket if connected, returns false otherwise. This is needed before focus tracking can send messages. _(Skip if Issue 031 already provides this method.)_
- [x] **2. Add focus tracking listener in `activate()`** — Register `vscode.window.onDidChangeWindowState` listener that:
  - Checks if `brainManager` exists
  - Applies 100ms debounce via `lastFocusTime` timestamp
  - Constructs `{type: "focus"|"blur", workspace: "...", timestamp: ...}` message
  - Calls `brainManager.send(msg)`
  - Logs to output channel: `[Brain] Sent: focus` or `[Brain] Sent: blur`
  - Wraps in try/catch for resilience
- [x] **3. Register listener in context.subscriptions** — Push the disposable returned by `onDidChangeWindowState` to `context.subscriptions`
- [x] **4. Write unit tests for focus tracking** — Test debounce, message format, null-connection guard, logging
- [x] **5. Compile and verify** — `npm run compile` must pass clean

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| Event listener added in extension activate() | Test that onDidChangeWindowState is registered during activate | unit |
| On focus gain, sends `{"type":"focus","workspace":"...","timestamp":...}` | Mock WindowState with `focused:true`, verify message sent via brainManager.send() | unit |
| On focus loss, sends `{"type":"blur","workspace":"...","timestamp":...}` | Mock WindowState with `focused:false`, verify message sent via brainManager.send() | unit |
| Messages sent only if brain connection active | Simulate no brainManager / disconnected state, verify no write attempted | unit |
| Focus/blur events logged to output channel | Verify logger.appendLine called with `[Brain] Sent: focus` / `[Brain] Sent: blur` | unit |
| Handles rapid focus changes gracefully | Fire multiple events within 100ms, verify only first sends | unit |

**No cheating** — cannot claim done without all 6 test categories passing.

## Validation (Backpressure)

- **Tests**: All focus tracking unit tests must pass (`npx jest` or equivalent)
- **Lint**: TypeScript compilation must pass without errors (`npm run compile`)
- **Build**: Extension must compile cleanly
- **Manual**: Described in issue — click away from VS Code and back, verify focus/blur messages in output channel

## Files to Create/Modify

- **Modify**: `cyrus-companion/src/extension.ts` — added focus tracking listener in `activate()`, subscription registration via `createFocusHandler` ✅
- **Modify**: `cyrus-companion/src/brain-connection.ts` — added `send(msg: object): boolean` method ✅
- **Create**: `cyrus-companion/src/focus-tracker.ts` — extracted `createFocusHandler` factory (not in original plan; extracted for testability, follows brain-connection.ts pattern) ✅
- **Create**: `cyrus-companion/src/focus-tracking.test.ts` — 20 unit tests covering all acceptance criteria ✅
- **Modify**: `cyrus-companion/src/__mocks__/vscode.ts` — added `onDidChangeWindowState` mock to window ✅
- `cyrus-companion/package.json` — already had Jest configured from Issue 031 ✅

## Key Implementation Details

### Focus Tracking Code (in activate):
```typescript
// Module-level debounce state
let lastFocusTime = 0;

// In activate(), after brainManager is created:
const focusDisposable = vscode.window.onDidChangeWindowState((state: vscode.WindowState) => {
    if (!brainManager) { return; }

    const now = Date.now();
    if (now - lastFocusTime < 100) { return; }  // Debounce
    lastFocusTime = now;

    const msgType = state.focused ? 'focus' : 'blur';
    const msg = {
        type: msgType,
        workspace: workspaceName,
        timestamp: now,
    };

    try {
        brainManager.send(msg);
        out.appendLine(`[Brain] Sent: ${msgType}`);
    } catch (e) {
        out.appendLine(`[Brain] Failed to send ${msgType}: ${e}`);
    }
});
context.subscriptions.push(focusDisposable);
```

### BrainConnectionManager.send() method:
```typescript
/** Send a JSON message to the brain. Returns false if not connected. */
send(msg: object): boolean {
    if (!this.socket || this.destroyed) { return false; }
    try {
        this.socket.write(JSON.stringify(msg) + '\n');
        return true;
    } catch {
        return false;
    }
}
```
