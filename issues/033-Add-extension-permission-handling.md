# Issue 033: Add Extension Permission Handling

## Sprint
Sprint 5 — Docker & Extension

## Priority
High

## References
- docs/13-docker-containerization.md — Phase 2 (Extension handles permission_respond messages)

## Description
Extension receives `permission_respond` and `prompt_respond` messages from the brain over the persistent connection. Simulate keyboard input to the VS Code window: press `1` for "allow" permission, `Escape` for "deny". Replace the unreliable UIA-based auto-clicking with deterministic keyboard simulation.

## Blocked By
- Issue 031 (brain connection must exist)

## Acceptance Criteria
- [ ] `handleBrainMessage()` recognizes `permission_respond` and `prompt_respond` types
- [ ] On `permission_respond` with action="allow", simulates pressing `1`
- [ ] On `permission_respond` with action="deny", simulates pressing `Escape`
- [ ] On `prompt_respond` with text field, pastes text and presses `Enter` (future)
- [ ] Keyboard simulation uses platform-specific methods (PowerShell on Windows, osascript on macOS, xdotool on Linux)
- [ ] Failures logged but never thrown (don't break extension)
- [ ] Success logged with action taken

## Implementation Steps
1. Expand `handleBrainMessage()` in `cyrus-companion/src/extension.ts`:
   ```typescript
   function handleBrainMessage(msg: any): void {
       const type = msg.type;

       if (type === 'permission_respond') {
           const action = msg.action;
           out.appendLine(`[Brain] Permission respond: ${action}`);

           if (action === 'allow') {
               simulateKeyPress('1');
           } else if (action === 'deny') {
               simulateKeyPress('Escape');
           }
       }
       else if (type === 'prompt_respond') {
           const text = msg.text || '';
           out.appendLine(`[Brain] Prompt respond: ${text.slice(0, 50)}...`);
           // Paste text and press Enter (reuse submitText logic)
       }
   }
   ```
2. Implement `simulateKeyPress()` helper:
   ```typescript
   async function simulateKeyPress(key: string): Promise<void> {
       const platform = os.platform();
       try {
           let command = '';
           if (platform === 'win32') {
               if (key === '1') {
                   command = `powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "\\$s = New-Object -ComObject WScript.Shell; \\$s.SendKeys('1')"`;
               } else if (key === 'Escape') {
                   command = `powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "\\$s = New-Object -ComObject WScript.Shell; \\$s.SendKeys('{ESC}')"`;
               }
           } else if (platform === 'darwin') {
               if (key === '1') {
                   command = `osascript -e 'tell application "System Events" to keystroke "1"'`;
               } else if (key === 'Escape') {
                   command = `osascript -e 'tell application "System Events" to key code 53'`;  // Escape key code
               }
           } else {
               if (key === '1') {
                   command = `xdotool key 1`;
               } else if (key === 'Escape') {
                   command = `xdotool key Escape`;
               }
           }

           if (command) {
               await execAsync(command, { timeout: 3000 });
               out.appendLine(`[Brain] Simulated key press: ${key}`);
           }
       } catch (err) {
           out.appendLine(`[Brain] Failed to simulate ${key}: ${err}`);
       }
   }
   ```

## Files to Create/Modify
- Modify: `cyrus-companion/src/extension.ts` (expand handleBrainMessage, add simulateKeyPress)

## Testing
1. Compile extension with `npm run compile`
2. Start brain; open VS Code with extension
3. Trigger a mock permission dialog (test by sending message directly to extension port)
4. Send `{"type": "permission_respond", "action": "allow"}` to extension
5. Verify extension logs key press and keyboard sends "1"
6. Send `{"type": "permission_respond", "action": "deny"}` to extension
7. Verify extension logs key press and keyboard sends "Escape"
8. Test with VS Code focused vs unfocused
