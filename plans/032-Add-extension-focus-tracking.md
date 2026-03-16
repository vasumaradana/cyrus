# Plan: 032-Add-extension-focus-tracking

## Summary

Add a `vscode.window.onDidChangeWindowState` event listener to the companion extension that sends `focus`/`blur` JSON messages over the persistent brain connection (port 8770). Include 100ms debounce to handle rapid focus switching and guard against absent/broken connections.

## Gap Analysis

**Already exists in `cyrus-companion/src/extension.ts`:**
- `net` module imported
- `out` OutputChannel for logging
- Workspace name extraction (`vscode.workspace.workspaceFolders?.[0]?.name ?? 'default'`)
- `activate()` function with `context.subscriptions` for cleanup
- `sleep()` utility

**Does NOT yet exist (needs building):**
- `brainConnection` module-level variable (Issue 031 not yet built — builder must add a stub)
- `onDidChangeWindowState` event listener
- Debounce mechanism
- Focus/blur message formatting and sending

**Dependency note:** Issue 031 (brain connection + registration) is still GROOMED. The builder must declare `let brainConnection: net.Socket | undefined;` as a module-level stub so focus tracking code compiles and works once 031 populates the variable. Issue 031's implementation will use and manage this same variable.

## Key Design Decisions

1. **Stub `brainConnection` now**: Declare `let brainConnection: net.Socket | undefined;` at module level alongside existing `server`, `cleanupPath`, `out`. This is the same variable 031 will connect/manage. Adding it now avoids a compile error and keeps the focus tracking code self-contained.

2. **Debounce at 100ms**: The issue suggests 100ms. This prevents hammering the brain during rapid Alt-Tab sequences. Use a simple timestamp comparison — no timer/setTimeout needed.

3. **Connection guard**: Check `brainConnection && !brainConnection.destroyed` before writing. If the connection is absent or broken, silently skip (no error thrown). This matches acceptance criterion "Messages sent only if brain connection active".

4. **Subscription cleanup**: Push the `onDidChangeWindowState` disposable into `context.subscriptions` so VS Code disposes it on deactivation.

5. **Message format matches doc spec**: `{"type": "focus"|"blur", "workspace": "...", "timestamp": <epoch_ms>}` — newline-delimited JSON, consistent with the existing protocol in `handleConnection()`.

## Acceptance Criteria → Implementation Map

| Criterion | Implementation |
|-----------|---------------|
| Event listener added in extension `activate()` | Register `vscode.window.onDidChangeWindowState` in `activate()`, push to `context.subscriptions` |
| On focus gain, sends `{"type": "focus", ...}` | In listener callback, when `event.focused === true`, write JSON to `brainConnection` |
| On focus loss, sends `{"type": "blur", ...}` | In listener callback, when `event.focused === false`, write JSON to `brainConnection` |
| Messages sent only if brain connection active | Guard: `if (!brainConnection \|\| brainConnection.destroyed) return;` |
| Focus/blur events logged to output channel | `out.appendLine(\`[Brain] Sent: ${msgType}\`)` and error logging on write failure |
| Handles rapid focus changes gracefully | 100ms debounce via `lastFocusTime` timestamp comparison |

## Implementation Steps

### Step 1: Add `brainConnection` stub at module level

**File:** `cyrus-companion/src/extension.ts`, after the existing module-level state section (after line 41)

Add to the `// ── Module-level state` section:

```typescript
let brainConnection: net.Socket | undefined;  // managed by brain registration (issue 031)
```

This goes alongside the existing `let server`, `let cleanupPath`, `let out` declarations.

**Verify:** `npm run compile` in `cyrus-companion/` — compiles cleanly.

### Step 2: Add focus tracking listener with debounce in `activate()`

**File:** `cyrus-companion/src/extension.ts`, inside `activate()` function, after the `startServer()` call (after line 59)

Add the focus tracking listener and debounce state:

```typescript
// ── Focus tracking (brain connection) ──────────────────────────
let lastFocusTime = 0;

const focusDisposable = vscode.window.onDidChangeWindowState((event: vscode.WindowState) => {
    // Debounce: ignore events within 100ms of previous
    const now = Date.now();
    if (now - lastFocusTime < 100) {
        return;
    }
    lastFocusTime = now;

    // Guard: only send if brain connection is active
    if (!brainConnection || brainConnection.destroyed) {
        return;
    }

    const workspace = vscode.workspace.workspaceFolders?.[0]?.name ?? 'default';
    const msgType = event.focused ? 'focus' : 'blur';
    const msg = {
        type: msgType,
        workspace,
        timestamp: now,
    };

    try {
        brainConnection.write(JSON.stringify(msg) + '\n');
        out.appendLine(`[Brain] Sent: ${msgType}`);
    } catch (e) {
        out.appendLine(`[Brain] Failed to send ${msgType}: ${e}`);
    }
});

context.subscriptions.push(focusDisposable);
```

**Placement rationale:** After `startServer()` but before the existing `context.subscriptions.push` block. The `lastFocusTime` is scoped inside `activate()` — it only needs to persist for the lifetime of the extension.

**Verify:** `npm run compile` — compiles cleanly.

### Step 3: Verify compilation

**Command:** `cd cyrus-companion && npm run compile`

This is the only automated verification available. The `TEST_COMMAND` in `.barfrc` is empty and the extension has no test framework.

### Step 4: Manual testing checklist

Once Issues 031 and 034 are also built, verify:

1. Open VS Code with extension → brain receives `focus` message on window focus
2. Click away from VS Code → brain receives `blur` message
3. Click back → brain receives `focus` with correct workspace name and timestamp
4. Rapidly Alt-Tab 10+ times → no connection errors, debounce filters rapid events
5. Kill brain connection → no exceptions in extension (guard silently skips)
6. Reconnect brain → focus/blur messages resume

## Risk Notes

- **Dependency chain**: 034 (brain listener) → 031 (extension registration) → 032 (this issue). Since neither 031 nor 034 are built, the `brainConnection` stub will always be `undefined` at runtime until 031 is completed. The code is correct but inert until then.
- **No automated tests**: The cyrus-companion has no test framework (`package.json` has no test script, no test files exist). Verification is compilation-only. This is acceptable given the project's current state.
- **`brainConnection.destroyed` property**: Node.js `net.Socket` has `destroyed: boolean` since Node 8. The extension targets `@types/node ^20.0.0`, so this is safe.
