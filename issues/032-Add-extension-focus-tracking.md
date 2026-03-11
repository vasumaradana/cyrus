# Issue 032: Add Extension Focus Tracking

## Sprint
Sprint 5 — Docker & Extension

## Priority
High

## References
- docs/13-docker-containerization.md — Phase 2 (Focus tracking via vscode.window.onDidChangeWindowState)

## Description
Hook `vscode.window.onDidChangeWindowState` event in the companion extension to detect when VS Code window gains or loses focus. Send `focus` or `blur` messages to the brain over the persistent registration connection (port 8770). Enables brain to track active project across multiple workspace windows.

## Blocked By
- Issue 031 (brain connection must exist)

## Acceptance Criteria
- [ ] Event listener added in extension activate()
- [ ] On focus gain, sends `{"type": "focus", "workspace": "...", "timestamp": ...}`
- [ ] On focus loss, sends `{"type": "blur", "workspace": "...", "timestamp": ...}`
- [ ] Messages sent only if brain connection active
- [ ] Focus/blur events logged to output channel
- [ ] Handles rapid focus changes gracefully

## Implementation Steps
1. In `cyrus-companion/src/extension.ts`, add listener in `activate()`:
   ```typescript
   vscode.window.onDidChangeWindowState((event: vscode.WindowState) => {
       if (!brainConnection) {
           return;
       }

       const workspace = vscode.workspace.workspaceFolders?.[0]?.name ?? 'default';
       const msgType = event.focused ? 'focus' : 'blur';
       const msg = {
           type: msgType,
           workspace: workspace,
           timestamp: Date.now()
       };

       try {
           brainConnection.write(JSON.stringify(msg) + '\n');
           out.appendLine(`[Brain] Sent: ${msgType}`);
       } catch (e) {
           out.appendLine(`[Brain] Failed to send ${msgType}: ${e}`);
       }
   });
   ```
2. Register in context.subscriptions:
   ```typescript
   context.subscriptions.push(
       vscode.window.onDidChangeWindowState(...)
   );
   ```
3. Optionally add debounce to prevent hammering brain with focus/blur on rapid switches:
   ```typescript
   let lastFocusTime = 0;
   vscode.window.onDidChangeWindowState((event: vscode.WindowState) => {
       const now = Date.now();
       if (now - lastFocusTime < 100) return;  // Debounce
       lastFocusTime = now;
       // ... send message
   });
   ```

## Files to Create/Modify
- Modify: `cyrus-companion/src/extension.ts` (add focus/blur event listener)

## Testing
1. Compile extension with `npm run compile`
2. Start brain with logging output
3. Open VS Code with extension
4. Click on another window then back to VS Code — verify brain receives `focus` and `blur` messages
5. Verify workspace name is correct in messages
6. Rapidly switch focus 10 times — verify no connection errors
7. Disconnect brain connection while switching focus — verify no exceptions in extension
