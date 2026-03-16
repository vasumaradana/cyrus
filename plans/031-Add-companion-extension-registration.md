# Plan: 031 — Add Companion Extension Registration

## Overview

Add outbound TCP connection from the VS Code companion extension to the Cyrus Brain
on port 8770. On activation, send a registration message with workspace metadata and
the extension's listening port. Implement auto-reconnect with exponential backoff.
Add VS Code settings for configurable brain host and port.

**Files to modify:**
- `cyrus-companion/package.json`
- `cyrus-companion/src/extension.ts`

## Design Decisions

### 1. Listen port via module-level state

The brain connection needs the extension's listen port for the registration message.
Current `startServer()` doesn't expose the port. Rather than changing its signature
(which would ripple into the `.then()` chain), store it as module-level state
`let listenPort = 0` — consistent with existing `server` and `cleanupPath` pattern.

- **Windows (TCP)**: `listenPort` = the TCP port from `listenOnFreePort`
- **Unix (socket)**: `listenPort` stays 0 — the brain derives the socket path from the
  `safe` name in the registration message

### 2. Brain connection as module-level state

New module-level variables, following the existing pattern:

```typescript
let brainSocket: net.Socket | undefined;
let brainReconnectTimer: ReturnType<typeof setTimeout> | undefined;
let brainReconnectBackoff = 1000;
```

### 3. Backoff sequence matches AC exactly

AC requires: **1s, 2s, 4s, max 30s**. Schedule the timeout at the *current* backoff
value, then double it. This produces `1000 → 2000 → 4000 → 8000 → 16000 → 30000`.

```typescript
function scheduleReconnect(...): void {
    out.appendLine(`[Brain] Reconnecting in ${brainReconnectBackoff}ms`);
    brainReconnectTimer = setTimeout(() => connectToBrain(...), brainReconnectBackoff);
    brainReconnectBackoff = Math.min(brainReconnectBackoff * 2, 30000);
}
```

(The issue's reference code doubles *before* scheduling, which makes the first
reconnect 2s instead of 1s — this plan corrects that to match the AC.)

### 4. Double-reconnect prevention

Both `error` and `close` fire for the same disconnect. Guard with a
`reconnectScheduled` flag that resets on successful connect. Prevents overlapping
timers.

### 5. Robust buffer parsing

The issue's reference code uses `if (nl !== -1)` — processes only one message per
data event. Use a `while` loop instead so back-to-back messages in a single chunk
are all consumed. This is a minor correctness improvement.

### 6. Cleanup on deactivation

`deactivate()` and the subscription dispose handler both need to:
- Clear `brainReconnectTimer` (prevent reconnect after shutdown)
- Destroy `brainSocket` (close TCP connection)

### 7. No automated tests

The extension has no test framework. All code depends on `vscode` API and `net` TCP.
The issue's testing section is manual-only. Setting up a test harness (mock VS Code,
mock TCP) is out of scope for this issue. Verification: `npm run compile` succeeds.

---

## Implementation Steps

### Step 1: Add VS Code settings to `package.json`

**File:** `cyrus-companion/package.json`

Add two properties to `contributes.configuration.properties`:

```json
"cyrusCompanion.brainHost": {
    "type": "string",
    "default": "localhost",
    "description": "Hostname/IP of Cyrus Brain (for registration and receiving responses)"
},
"cyrusCompanion.brainPort": {
    "type": "integer",
    "default": 8770,
    "description": "Port Cyrus Brain listens on for extension registration"
}
```

**Verify:** `npm run compile` in `cyrus-companion/`.

---

### Step 2: Store listen port in module state

**File:** `cyrus-companion/src/extension.ts`

1. Add `let listenPort = 0;` alongside existing module-level variables (line ~40).
2. In `startTcp()`, after `listenOnFreePort` resolves, set `listenPort = port`.
3. No change to `startUnixSocket()` — `listenPort` stays 0 on Unix.

**Verify:** `npm run compile`.

---

### Step 3: Add brain connection manager

**File:** `cyrus-companion/src/extension.ts`

Add a new section after the existing helpers block (`// ── Helpers ──`), before the
connection handler:

```
// ── Brain connection ─────────────────────────────────────────────────────────
```

#### Module-level state (add near line 40)

```typescript
let brainSocket: net.Socket | undefined;
let brainReconnectTimer: ReturnType<typeof setTimeout> | undefined;
let brainReconnectBackoff = 1000;
let brainReconnectScheduled = false;
```

#### `connectToBrain(workspace, safe, port)`

```typescript
function connectToBrain(workspace: string, safe: string, port: number): void {
    const brainHost = vscode.workspace
        .getConfiguration('cyrusCompanion')
        .get<string>('brainHost', 'localhost');
    const brainPort = vscode.workspace
        .getConfiguration('cyrusCompanion')
        .get<number>('brainPort', 8770);

    brainReconnectScheduled = false;

    brainSocket = net.createConnection(brainPort, brainHost, () => {
        out.appendLine(`[Brain] Connected to ${brainHost}:${brainPort}`);
        brainReconnectBackoff = 1000; // Reset on success

        const regMsg = {
            type: 'register',
            workspace,
            safe,
            port,
        };
        brainSocket!.write(JSON.stringify(regMsg) + '\n');
        out.appendLine(`[Brain] Registered: ${workspace} (port ${port})`);
    });

    brainSocket.on('error', (err) => {
        out.appendLine(`[Brain] Connection error: ${err.message}`);
        scheduleReconnect(workspace, safe, port);
    });

    brainSocket.on('close', () => {
        out.appendLine('[Brain] Disconnected');
        scheduleReconnect(workspace, safe, port);
    });

    // Handle incoming messages from brain (line-delimited JSON)
    let buffer = '';
    brainSocket.on('data', (chunk: Buffer) => {
        buffer += chunk.toString();
        let nl = buffer.indexOf('\n');
        while (nl !== -1) {
            const line = buffer.slice(0, nl);
            buffer = buffer.slice(nl + 1);
            try {
                const msg = JSON.parse(line);
                handleBrainMessage(msg);
            } catch (e) {
                out.appendLine(`[Brain] Invalid JSON: ${e}`);
            }
            nl = buffer.indexOf('\n');
        }
    });
}
```

#### `scheduleReconnect(workspace, safe, port)`

```typescript
function scheduleReconnect(workspace: string, safe: string, port: number): void {
    if (brainReconnectScheduled) return; // Prevent double-schedule from error+close
    brainReconnectScheduled = true;

    out.appendLine(`[Brain] Reconnecting in ${brainReconnectBackoff}ms`);
    brainReconnectTimer = setTimeout(
        () => connectToBrain(workspace, safe, port),
        brainReconnectBackoff,
    );
    brainReconnectBackoff = Math.min(brainReconnectBackoff * 2, 30000);
}
```

#### `handleBrainMessage(msg)` — stub

```typescript
function handleBrainMessage(msg: Record<string, unknown>): void {
    const type = msg.type;
    out.appendLine(`[Brain] Received: ${type}`);
    // Will be implemented in Issue 032, 033
}
```

**Verify:** `npm run compile`.

---

### Step 4: Wire brain connection into `activate()` and cleanup

**File:** `cyrus-companion/src/extension.ts`

#### In `activate()` — chain `connectToBrain` after server starts

Change:
```typescript
startServer(safe)
    .then(() => out.appendLine('[Cyrus] Ready.'))
    .catch(err => { ... });
```

To:
```typescript
startServer(safe)
    .then(() => {
        out.appendLine('[Cyrus] Ready.');
        connectToBrain(workspaceName, safe, listenPort);
    })
    .catch(err => { ... });
```

#### In `activate()` — add brain cleanup to dispose

Change the subscription dispose to also clean up brain connection:

```typescript
context.subscriptions.push({
    dispose: () => {
        server?.close();
        tryUnlink(cleanupPath);
        if (brainReconnectTimer) clearTimeout(brainReconnectTimer);
        brainSocket?.destroy();
    },
});
```

#### In `deactivate()` — add brain cleanup

```typescript
export function deactivate(): void {
    server?.close();
    tryUnlink(cleanupPath);
    if (brainReconnectTimer) clearTimeout(brainReconnectTimer);
    brainSocket?.destroy();
}
```

**Verify:** `npm run compile`.

---

### Step 5: Final verification

```bash
cd cyrus-companion && npm run compile
```

Confirm zero errors, zero warnings.

---

## Acceptance Criteria → Verification Map

| # | Criterion | Implementation | Verified by |
|---|-----------|---------------|-------------|
| 1 | Extension connects to `brainHost:8770` on activation | `connectToBrain()` called from `activate()` after server starts | `npm run compile` + manual: check output channel shows `[Brain] Connected` |
| 2 | Sends `{"type":"register",...}` message | `brainSocket.write(JSON.stringify(regMsg) + '\n')` in connect callback | Manual: brain logs show registration received |
| 3 | Auto-reconnect with backoff (1s, 2s, 4s, max 30s) | `scheduleReconnect()` — schedule-first-then-double, cap 30000 | Manual: stop brain, watch reconnect log timestamps |
| 4 | Settings: `brainHost` (localhost), `brainPort` (8770) | Added to `package.json` `contributes.configuration.properties` | Settings visible in VS Code Settings UI |
| 5 | Connection status logged to output channel | All events logged with `[Brain]` prefix to `out` | Manual: check Cyrus Companion output channel |
| 6 | Persistent connection kept alive | Socket stays open; `handleBrainMessage` processes incoming `data` events | Manual: brain sends test message, extension logs receipt |
