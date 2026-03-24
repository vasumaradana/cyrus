/**
 * permission-handler.ts — Brain message permission handling for Cyrus Companion
 *
 * Handles `permission_respond` and `prompt_respond` messages received from the
 * Cyrus Brain over the persistent connection.
 *
 * For permission dialogs: simulates keyboard input to VS Code —
 *   - press `1` to allow
 *   - press `Escape` to deny
 *
 * Uses platform-specific keyboard simulation:
 *   - Windows:  PowerShell + WScript.Shell.SendKeys
 *   - macOS:    osascript (System Events keystroke/key code)
 *   - Linux:    xdotool
 *
 * Errors are always caught and logged — never thrown — so a failed keyboard
 * simulation cannot crash or freeze the extension.
 */

import * as os from 'os';
import * as child_process from 'child_process';
import { promisify } from 'util';

// Default exec implementation — overridable in tests via the exec parameter
const defaultExec = promisify(child_process.exec);

/** Minimal logger interface matching VS Code's OutputChannel */
export interface Logger {
    appendLine(msg: string): void;
}

/** Exec function type — allows test injection of a mock */
export type ExecFn = (cmd: string, opts?: { timeout?: number }) => Promise<unknown>;

/**
 * Simulate a keyboard key press using platform-specific methods.
 *
 * Supported keys: '1' (allow permission) and 'Escape' (deny permission).
 * Unknown keys produce no exec call and no success log.
 *
 * Failures are caught and logged via `logger` — the function always resolves.
 *
 * @param key    Key to simulate: '1' or 'Escape'
 * @param logger Output channel for logging
 * @param exec   Optional exec override for testing (defaults to child_process.exec)
 */
export async function simulateKeyPress(
    key: string,
    logger: Logger,
    exec: ExecFn = defaultExec,
): Promise<void> {
    const platform = os.platform();
    try {
        let command = '';

        if (platform === 'win32') {
            // PowerShell WScript.Shell.SendKeys — runs in hidden window
            if (key === '1') {
                command = `powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "$s = New-Object -ComObject WScript.Shell; $s.SendKeys('1')"`;
            } else if (key === 'Escape') {
                command = `powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "$s = New-Object -ComObject WScript.Shell; $s.SendKeys('{ESC}')"`;
            }
        } else if (platform === 'darwin') {
            // osascript System Events — simulates hardware keystrokes
            if (key === '1') {
                command = `osascript -e 'tell application "System Events" to keystroke "1"'`;
            } else if (key === 'Escape') {
                // Escape = key code 53 in macOS virtual key codes
                command = `osascript -e 'tell application "System Events" to key code 53'`;
            }
        } else {
            // Linux — xdotool sends X11 key events
            if (key === '1') {
                command = `xdotool key 1`;
            } else if (key === 'Escape') {
                command = `xdotool key Escape`;
            }
        }

        if (command) {
            await exec(command, { timeout: 3000 });
            logger.appendLine(`[Brain] Simulated key press: ${key}`);
        }
    } catch (err) {
        // Log the failure but never propagate — a failed key sim must not crash the extension
        logger.appendLine(`[Brain] Failed to simulate ${key}: ${err}`);
    }
}

/**
 * Handle an incoming message from the Cyrus Brain.
 *
 * Dispatches known message types to the appropriate handler:
 *   - `permission_respond`: simulates a key press (1 = allow, Escape = deny)
 *   - `prompt_respond`:     logs the text preview (paste + Enter is future work)
 *
 * Unknown or malformed messages are silently ignored.
 *
 * @param msg    Parsed JSON message from the brain (typed as unknown for safety)
 * @param logger Output channel for logging
 * @param exec   Optional exec override forwarded to simulateKeyPress (for testing)
 */
export function handleBrainMessage(msg: unknown, logger: Logger, exec?: ExecFn): void {
    // Guard: only process plain objects
    if (typeof msg !== 'object' || msg === null) {
        return;
    }

    const m = msg as Record<string, unknown>;
    const type = m.type;

    if (type === 'permission_respond') {
        const action = m.action;
        logger.appendLine(`[Brain] Permission respond: ${action}`);

        // Fire-and-forget keyboard simulation — errors are caught inside simulateKeyPress
        if (action === 'allow') {
            void simulateKeyPress('1', logger, exec);
        } else if (action === 'deny') {
            void simulateKeyPress('Escape', logger, exec);
        }
    } else if (type === 'prompt_respond') {
        const text = typeof m.text === 'string' ? m.text : '';
        // Truncate to 50 chars for the log preview
        logger.appendLine(`[Brain] Prompt respond: ${text.slice(0, 50)}...`);
        // TODO Issue 033 (future): paste text into Claude Code input and press Enter
    }
    // Unknown types are silently ignored — forward-compatible with new brain message types
}
