# Issue 031: Add Companion Extension Registration

## Sprint
Sprint 5 — Docker & Extension

## Priority
Critical

## References
- docs/13-docker-containerization.md — Phase 2 (Companion Extension Registration Protocol)

## Description
Enhance the companion extension to initiate outbound connection to the brain on port 8770. On activation, send a registration message with workspace name and listening port. Implement auto-reconnect with exponential backoff. Add VS Code settings for configurable brain host and port.

## Blocked By
- Issue 034 (brain registration listener must exist to accept registration)

## Acceptance Criteria
- [ ] Extension connects to `brainHost:8770` on activation
- [ ] Sends `{"type": "register", "workspace": "...", "safe": "...", "port": ...}` message
- [ ] Auto-reconnect on disconnect with exponential backoff (1s, 2s, 4s, max 30s)
- [ ] New settings in package.json: `cyrusCompanion.brainHost` (default: localhost), `cyrusCompanion.brainPort` (default: 8770)
- [ ] Connection status logged to output channel
- [ ] Persistent connection kept alive (for receiving brain messages)

## Implementation Steps
1. Modify `cyrus-companion/package.json` — add settings:
   ```json
   "cyrusCompanion.brainHost": {
       "type": "string",
       "default": "localhost",
       "description": "Hostname/IP of Cyrus Brain (for registration and receiving responses)"
   },
   "cyrusCompanion.brainPort": {
       "type": "integer",
       "default": 8770,
       "description": "Port Cyrus Brain listens on for extension registration (8770)"
   }
   ```
2. In `cyrus-companion/src/extension.ts`, add a brain connection manager:
   ```typescript
   let brainConnection: net.Socket | undefined;
   let brainReconnectBackoff = 1000;  // Start at 1s

   async function connectToBrain(workspace: string, safe: string, listenPort: number): Promise<void> {
       const brainHost = vscode.workspace
           .getConfiguration('cyrusCompanion')
           .get<string>('brainHost', 'localhost');
       const brainPort = vscode.workspace
           .getConfiguration('cyrusCompanion')
           .get<number>('brainPort', 8770);

       brainConnection = net.createConnection(brainPort, brainHost, () => {
           out.appendLine(`[Brain] Connected to ${brainHost}:${brainPort}`);
           brainReconnectBackoff = 1000;  // Reset backoff on success

           // Send registration
           const regMsg = {
               type: "register",
               workspace: workspace,
               safe: safe,
               port: listenPort
           };
           brainConnection!.write(JSON.stringify(regMsg) + '\n');
           out.appendLine(`[Brain] Registered: ${workspace} (port ${listenPort})`);
       });

       brainConnection.on('error', (err) => {
           out.appendLine(`[Brain] Connection error: ${err.message}`);
           scheduleReconnect(workspace, safe, listenPort);
       });

       brainConnection.on('close', () => {
           out.appendLine(`[Brain] Disconnected`);
           scheduleReconnect(workspace, safe, listenPort);
       });

       // Handle incoming messages from brain
       let buffer = '';
       brainConnection.on('data', (chunk: Buffer) => {
           buffer += chunk.toString();
           const nl = buffer.indexOf('\n');
           if (nl !== -1) {
               const line = buffer.slice(0, nl);
               buffer = buffer.slice(nl + 1);
               try {
                   const msg = JSON.parse(line);
                   handleBrainMessage(msg);
               } catch (e) {
                   out.appendLine(`[Brain] Invalid JSON: ${e}`);
               }
           }
       });
   }

   function scheduleReconnect(workspace: string, safe: string, listenPort: number): void {
       brainReconnectBackoff = Math.min(brainReconnectBackoff * 2, 30000);  // Cap at 30s
       out.appendLine(`[Brain] Reconnecting in ${brainReconnectBackoff}ms`);
       setTimeout(() => connectToBrain(workspace, safe, listenPort), brainReconnectBackoff);
   }
   ```
3. Call `connectToBrain()` from `activate()` after server starts:
   ```typescript
   const port = await listenOnFreePort(srv, 8768, 8778);  // or whatever port is assigned
   await connectToBrain(workspaceName, safe, port);
   ```
4. Add stub handler for brain messages:
   ```typescript
   function handleBrainMessage(msg: any): void {
       const type = msg.type;
       out.appendLine(`[Brain] Received: ${type}`);
       // Will be implemented in Issue 032, 033
   }
   ```

## Files to Create/Modify
- Modify: `cyrus-companion/package.json` (add brainHost, brainPort settings)
- Modify: `cyrus-companion/src/extension.ts` (add brain connection, registration, reconnect logic)

## Testing
1. Compile extension with `npm run compile`
2. Start brain with `CYRUS_HEADLESS=1 python cyrus2/cyrus_brain.py`
3. Open VS Code with extension — check output channel shows "[Brain] Connected to localhost:8770"
4. Check brain logs show registration message received
5. Stop brain — verify extension logs reconnect attempts
6. Restart brain — verify extension reconnects automatically
7. Change brainHost/brainPort in settings — verify uses new values
