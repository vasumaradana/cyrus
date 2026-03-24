/**
 * brain-connection.ts — Outbound connection from companion extension to Cyrus Brain.
 *
 * On activation the companion initiates a TCP connection to the brain's registration
 * port (default 8770).  Once connected it sends a registration message so the brain
 * knows the workspace name, safe-name, and the local port the companion is listening on.
 *
 * The connection is kept open so the brain can push messages back (implemented in
 * issues 032 / 033).  On disconnect the manager auto-reconnects with exponential
 * backoff starting at 1 s and capped at 30 s.
 */

import * as net from 'net';

// ── Constants ─────────────────────────────────────────────────────────────────

const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;

// ── Interfaces ────────────────────────────────────────────────────────────────

/** Compatible with VS Code's OutputChannel — allows injecting a plain logger in tests. */
export interface Logger {
    appendLine(msg: string): void;
}

/** Brain connection config — read lazily from VS Code settings on each connect attempt. */
export interface BrainConfig {
    brainHost: string;
    brainPort: number;
    authToken: string;
}

// ── BrainConnectionManager ────────────────────────────────────────────────────

/**
 * Manages a persistent outbound TCP connection to the Cyrus Brain.
 *
 * Extracted into its own module so it can be unit-tested without a live VS Code
 * host — callers pass in a logger and a config-getter rather than importing
 * vscode directly.
 */
export class BrainConnectionManager {
    /** Current reconnect delay in milliseconds; doubles on each failure up to MAX. */
    private reconnectBackoffMs: number = INITIAL_BACKOFF_MS;

    /** When true, no further reconnect attempts will be made. */
    private destroyed: boolean = false;

    /** The active TCP socket, if connected. */
    private socket: net.Socket | undefined;

    /** Handle for a pending reconnect setTimeout, so it can be cancelled on destroy. */
    private reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    /**
     * @param workspace   Human-readable workspace name (e.g. folder name).
     * @param safe        URL-safe workspace name (alphanumeric + hyphen/underscore).
     * @param listenPort  Port the companion's inbound server is listening on.
     * @param logger      Output channel (or any {appendLine} compatible logger).
     * @param getConfig   Returns current brainHost/brainPort from VS Code config.
     * @param onMessage   Optional callback for incoming brain messages (stub for now).
     */
    constructor(
        private readonly workspace: string,
        private readonly safe: string,
        private readonly listenPort: number,
        private readonly logger: Logger,
        private readonly getConfig: () => BrainConfig,
        private readonly onMessage?: (msg: unknown) => void,
    ) {}

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Send a JSON message to the brain over the active socket.
     *
     * Returns `true` if the message was written to the socket, `false` if there
     * is no active connection (socket undefined or manager destroyed) or if the
     * write throws (e.g. EPIPE on a half-closed socket).
     */
    send(msg: object): boolean {
        if (!this.socket || this.destroyed) {
            return false;
        }
        try {
            this.socket.write(JSON.stringify(msg) + '\n');
            return true;
        } catch {
            // Socket may have closed between the guard check and the write;
            // return false so callers can decide whether to retry.
            return false;
        }
    }

    /** Initiate the outbound connection to the brain. Safe to call multiple times. */
    connect(): void {
        if (this.destroyed) {
            return;
        }

        const { brainHost, brainPort } = this.getConfig();

        // createConnection accepts (port, host, connectListener) — the listener fires
        // once the TCP handshake completes (equivalent to the 'connect' event).
        this.socket = net.createConnection(brainPort, brainHost, () => {
            this.onConnected(brainHost, brainPort);
        });

        this.socket.on('error', (err) => {
            this.logger.appendLine(`[Brain] Connection error: ${err.message}`);
            this.scheduleReconnect();
        });

        this.socket.on('close', () => {
            this.logger.appendLine('[Brain] Disconnected');
            this.scheduleReconnect();
        });

        // Buffer incoming data and dispatch complete newline-delimited JSON lines.
        let buffer = '';
        this.socket.on('data', (chunk: Buffer) => {
            buffer += chunk.toString();
            let nl = buffer.indexOf('\n');
            while (nl !== -1) {
                const line = buffer.slice(0, nl);
                buffer = buffer.slice(nl + 1);
                this.dispatchLine(line);
                nl = buffer.indexOf('\n');
            }
        });
    }

    /**
     * Permanently shut down the connection manager.
     * Cancels any pending reconnect timer and destroys the active socket.
     */
    destroy(): void {
        this.destroyed = true;
        if (this.reconnectTimer !== undefined) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = undefined;
        }
        if (this.socket) {
            this.socket.destroy();
            this.socket = undefined;
        }
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    /** Called once the TCP connection is established. */
    private onConnected(brainHost: string, brainPort: number): void {
        this.logger.appendLine(`[Brain] Connected to ${brainHost}:${brainPort}`);
        // Reset backoff so the next disconnect starts from 1 s again.
        this.reconnectBackoffMs = INITIAL_BACKOFF_MS;

        // Send workspace registration so the brain can route future messages back.
        // Token is read fresh from config on each connect so settings changes take effect.
        const { authToken } = this.getConfig();
        const regMsg = {
            type: 'register',
            workspace: this.workspace,
            safe: this.safe,
            port: this.listenPort,
            token: authToken,
        };
        this.socket!.write(JSON.stringify(regMsg) + '\n');
        this.logger.appendLine(`[Brain] Registered: ${this.workspace} (port ${this.listenPort})`);
    }

    /** Schedules a reconnect attempt using the current backoff delay, then doubles it. */
    private scheduleReconnect(): void {
        if (this.destroyed) {
            return;
        }
        const delay = this.reconnectBackoffMs;
        this.logger.appendLine(`[Brain] Reconnecting in ${delay}ms`);
        // Double backoff for the next failure, capped at MAX_BACKOFF_MS.
        this.reconnectBackoffMs = Math.min(this.reconnectBackoffMs * 2, MAX_BACKOFF_MS);
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = undefined;
            this.connect();
        }, delay);
    }

    /** Parses a single newline-terminated JSON line from the brain. */
    private dispatchLine(line: string): void {
        let msg: unknown;
        try {
            msg = JSON.parse(line);
        } catch (e) {
            this.logger.appendLine(`[Brain] Invalid JSON: ${e}`);
            return;
        }
        const type = (msg as Record<string, unknown>).type ?? '(unknown)';
        this.logger.appendLine(`[Brain] Received: ${type}`);
        // Delegate to caller-supplied handler (to be implemented in issues 032/033).
        if (this.onMessage) {
            this.onMessage(msg);
        }
    }
}
