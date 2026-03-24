/**
 * focus-tracker.ts — Window focus/blur tracking for Cyrus Companion extension.
 *
 * Extracted into its own module so the handler logic is unit-testable without
 * a live VS Code host — callers pass in getter functions and a logger rather
 * than importing vscode directly (same pattern as brain-connection.ts).
 *
 * Usage in extension.ts:
 *   const handler = createFocusHandler(() => brainManager, () => workspaceName, out);
 *   context.subscriptions.push(vscode.window.onDidChangeWindowState(handler));
 */

// ── Interfaces ────────────────────────────────────────────────────────────────

/** Minimal interface for sending messages to the brain (subset of BrainConnectionManager). */
export interface FocusSender {
    /** Serialize and send a JSON object to the brain. Returns false if not connected. */
    send(msg: object): boolean;
}

/** Compatible with VS Code OutputChannel — allows injecting a plain logger in tests. */
export interface FocusLogger {
    appendLine(msg: string): void;
}

/** Minimal window state type — mirrors vscode.WindowState without importing vscode. */
export interface WindowState {
    focused: boolean;
}

// ── Focus handler factory ─────────────────────────────────────────────────────

/**
 * Creates an event handler for vscode.window.onDidChangeWindowState that sends
 * focus/blur messages to the Cyrus Brain over the persistent registration connection.
 *
 * The returned handler:
 * - Guards against a null/undefined brain connection (safe to use before connect())
 * - Applies a 100ms debounce to avoid hammering the brain on rapid OS focus switches
 * - Logs sent messages and errors to the provided output channel
 *
 * @param getBrainManager  Returns the active BrainConnectionManager, or undefined if not connected.
 * @param getWorkspace     Returns the current workspace name (resolved at event-fire time).
 * @param logger           Output channel for status/error logging.
 */
export function createFocusHandler(
    getBrainManager: () => FocusSender | undefined,
    getWorkspace: () => string,
    logger: FocusLogger,
): (state: WindowState) => void {
    // Debounce state: last timestamp a message was successfully dispatched.
    // Module-level closure so each handler instance has independent state.
    let lastFocusTime = 0;

    return (state: WindowState): void => {
        // Guard: only send if brain connection is active
        const manager = getBrainManager();
        if (!manager) {
            return;
        }

        // Debounce: ignore events within 100ms of the last dispatched event.
        // This prevents hammering the brain on rapid OS focus switches (e.g.
        // Alt-Tab back-and-forth) without adding external debounce dependencies.
        const now = Date.now();
        if (now - lastFocusTime < 100) {
            return;
        }
        lastFocusTime = now;

        const msgType = state.focused ? 'focus' : 'blur';
        const msg = {
            type: msgType,
            workspace: getWorkspace(),
            timestamp: now,
        };

        try {
            manager.send(msg);
            logger.appendLine(`[Brain] Sent: ${msgType}`);
        } catch (e) {
            // Log send failures without crashing the extension — the brain may
            // have disconnected between the guard check and the write attempt.
            logger.appendLine(`[Brain] Failed to send ${msgType}: ${e}`);
        }
    };
}
