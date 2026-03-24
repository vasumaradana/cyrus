/**
 * focus-tracking.test.ts — TDD tests for extension focus tracking (Issue 032)
 *
 * Tests cover all acceptance criteria:
 * - Event listener handler created and callable
 * - On focus gain, sends {"type":"focus","workspace":"...","timestamp":...}
 * - On focus loss, sends {"type":"blur","workspace":"...","timestamp":...}
 * - Messages sent only if brain connection active (brainManager exists and send() works)
 * - Focus/blur events logged to output channel
 * - Handles rapid focus changes gracefully (100ms debounce)
 */

import { createFocusHandler, FocusSender, FocusLogger } from './focus-tracker';

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Create a minimal mock sender that tracks calls */
function makeMockSender(sendReturnValue = true): FocusSender & { sendCalls: object[] } {
    const sendCalls: object[] = [];
    return {
        sendCalls,
        send: jest.fn().mockImplementation((msg: object) => {
            sendCalls.push(msg);
            return sendReturnValue;
        }),
    };
}

/** Create a minimal mock logger that tracks log lines */
function makeMockLogger(): FocusLogger & { lines: string[] } {
    const lines: string[] = [];
    return {
        lines,
        appendLine: jest.fn().mockImplementation((msg: string) => {
            lines.push(msg);
        }),
    };
}

// ─────────────────────────────────────────────────────────────────────────────

describe('createFocusHandler', () => {

    // ── Acceptance test: handler creation ─────────────────────────────────────

    it('returns a callable function that accepts a WindowState-like object', () => {
        const handler = createFocusHandler(
            () => makeMockSender(),
            () => 'my-workspace',
            makeMockLogger(),
        );
        expect(typeof handler).toBe('function');
        // calling it should not throw
        expect(() => handler({ focused: true })).not.toThrow();
    });

    // ── Acceptance test: focus message format ─────────────────────────────────

    it('sends correct focus message when window gains focus', () => {
        const sender = makeMockSender();
        const logger = makeMockLogger();
        const handler = createFocusHandler(
            () => sender,
            () => 'my-workspace',
            logger,
        );

        const beforeMs = Date.now();
        handler({ focused: true });
        const afterMs = Date.now();

        expect(sender.send).toHaveBeenCalledTimes(1);
        const sentMsg = sender.sendCalls[0] as { type: string; workspace: string; timestamp: number };
        expect(sentMsg.type).toBe('focus');
        expect(sentMsg.workspace).toBe('my-workspace');
        expect(sentMsg.timestamp).toBeGreaterThanOrEqual(beforeMs);
        expect(sentMsg.timestamp).toBeLessThanOrEqual(afterMs);
    });

    // ── Acceptance test: blur message format ──────────────────────────────────

    it('sends correct blur message when window loses focus', () => {
        const sender = makeMockSender();
        const logger = makeMockLogger();
        const handler = createFocusHandler(
            () => sender,
            () => 'blur-workspace',
            logger,
        );

        const beforeMs = Date.now();
        handler({ focused: false });
        const afterMs = Date.now();

        expect(sender.send).toHaveBeenCalledTimes(1);
        const sentMsg = sender.sendCalls[0] as { type: string; workspace: string; timestamp: number };
        expect(sentMsg.type).toBe('blur');
        expect(sentMsg.workspace).toBe('blur-workspace');
        expect(sentMsg.timestamp).toBeGreaterThanOrEqual(beforeMs);
        expect(sentMsg.timestamp).toBeLessThanOrEqual(afterMs);
    });

    // ── Acceptance test: no-send when disconnected ────────────────────────────

    it('does not send when brainManager getter returns undefined', () => {
        const logger = makeMockLogger();
        const handler = createFocusHandler(
            () => undefined,  // no active connection
            () => 'ws',
            logger,
        );

        handler({ focused: true });

        // No send attempted, no log entry
        expect(logger.lines).toHaveLength(0);
    });

    it('does not send when brainManager is explicitly null (typed as undefined)', () => {
        // Simulates the moment between extension activation and brain connection
        let manager: FocusSender | undefined = undefined;
        const logger = makeMockLogger();
        const handler = createFocusHandler(
            () => manager,
            () => 'ws',
            logger,
        );

        // Before connection
        handler({ focused: true });
        expect(logger.lines).toHaveLength(0);

        // After connection established
        manager = makeMockSender();
        handler({ focused: false });
        expect(logger.lines).toHaveLength(1);
        expect(logger.lines[0]).toContain('blur');
    });

    // ── Acceptance test: logging ───────────────────────────────────────────────

    it('logs "[Brain] Sent: focus" to output channel on focus event', () => {
        const sender = makeMockSender();
        const logger = makeMockLogger();
        const handler = createFocusHandler(
            () => sender,
            () => 'ws',
            logger,
        );

        handler({ focused: true });

        expect(logger.lines.some(l => l === '[Brain] Sent: focus')).toBe(true);
    });

    it('logs "[Brain] Sent: blur" to output channel on blur event', () => {
        const sender = makeMockSender();
        const logger = makeMockLogger();
        const handler = createFocusHandler(
            () => sender,
            () => 'ws',
            logger,
        );

        handler({ focused: false });

        expect(logger.lines.some(l => l === '[Brain] Sent: blur')).toBe(true);
    });

    // ── Acceptance test: rapid focus change debounce ──────────────────────────

    it('debounces rapid focus changes — only first event within 100ms window is sent', () => {
        // Mock Date.now to control time precisely
        let mockNow = 1000;
        const realNow = Date.now;
        Date.now = () => mockNow;

        try {
            const sender = makeMockSender();
            const logger = makeMockLogger();
            const handler = createFocusHandler(
                () => sender,
                () => 'ws',
                logger,
            );

            // First event at t=1000 — should send
            handler({ focused: true });
            expect(sender.send).toHaveBeenCalledTimes(1);

            // Second event at t=1050 (within 100ms) — should be debounced
            mockNow = 1050;
            handler({ focused: false });
            expect(sender.send).toHaveBeenCalledTimes(1);  // still only 1

            // Third event at t=1099 (still within 100ms of first) — debounced
            mockNow = 1099;
            handler({ focused: true });
            expect(sender.send).toHaveBeenCalledTimes(1);  // still only 1

            // Fourth event at t=1101 (100ms+ after first) — should send
            mockNow = 1101;
            handler({ focused: false });
            expect(sender.send).toHaveBeenCalledTimes(2);  // now 2

        } finally {
            Date.now = realNow;
        }
    });

    it('allows a new event to fire after the debounce window expires', () => {
        let mockNow = 5000;
        const realNow = Date.now;
        Date.now = () => mockNow;

        try {
            const sender = makeMockSender();
            const logger = makeMockLogger();
            const handler = createFocusHandler(
                () => sender,
                () => 'ws',
                logger,
            );

            handler({ focused: true });   // t=5000: sends
            mockNow = 5200;              // +200ms — well past debounce
            handler({ focused: false });  // t=5200: sends

            expect(sender.send).toHaveBeenCalledTimes(2);
            const msgs = sender.sendCalls as Array<{ type: string }>;
            expect(msgs[0].type).toBe('focus');
            expect(msgs[1].type).toBe('blur');
        } finally {
            Date.now = realNow;
        }
    });

    // ── Error handling ────────────────────────────────────────────────────────

    it('logs error message if send() throws an exception', () => {
        const throwingSender: FocusSender = {
            send: jest.fn().mockImplementation(() => {
                throw new Error('socket broken');
            }),
        };
        const logger = makeMockLogger();
        const handler = createFocusHandler(
            () => throwingSender,
            () => 'ws',
            logger,
        );

        // Should not propagate the error
        expect(() => handler({ focused: true })).not.toThrow();
        expect(logger.lines.some(l => l.includes('[Brain] Failed to send focus'))).toBe(true);
        expect(logger.lines.some(l => l.includes('socket broken'))).toBe(true);
    });

    it('logs error message if send() throws on blur', () => {
        const throwingSender: FocusSender = {
            send: jest.fn().mockImplementation(() => {
                throw new Error('connection reset');
            }),
        };
        const logger = makeMockLogger();
        const handler = createFocusHandler(
            () => throwingSender,
            () => 'ws',
            logger,
        );

        expect(() => handler({ focused: false })).not.toThrow();
        expect(logger.lines.some(l => l.includes('[Brain] Failed to send blur'))).toBe(true);
    });

    // ── Edge cases ────────────────────────────────────────────────────────────

    it('each handler instance has independent debounce state', () => {
        let mockNow = 1000;
        const realNow = Date.now;
        Date.now = () => mockNow;

        try {
            const sender1 = makeMockSender();
            const sender2 = makeMockSender();

            const handler1 = createFocusHandler(() => sender1, () => 'ws1', makeMockLogger());
            const handler2 = createFocusHandler(() => sender2, () => 'ws2', makeMockLogger());

            handler1({ focused: true });   // handler1 at t=1000
            handler2({ focused: true });   // handler2 at t=1000 — its own debounce, should also send

            expect(sender1.send).toHaveBeenCalledTimes(1);
            expect(sender2.send).toHaveBeenCalledTimes(1);
        } finally {
            Date.now = realNow;
        }
    });

    it('uses the workspace name returned by getWorkspace at call time (late binding)', () => {
        // Workspace name should be resolved when the event fires, not when handler is created
        let currentWorkspace = 'workspace-v1';
        const sender = makeMockSender();
        const logger = makeMockLogger();
        const handler = createFocusHandler(
            () => sender,
            () => currentWorkspace,
            logger,
        );

        currentWorkspace = 'workspace-v2';  // name changes before event fires
        handler({ focused: true });

        const sentMsg = sender.sendCalls[0] as { workspace: string };
        expect(sentMsg.workspace).toBe('workspace-v2');
    });
});

// ── BrainConnectionManager.send() tests ───────────────────────────────────────

describe('BrainConnectionManager.send()', () => {
    // These tests are co-located here since send() was added as part of Issue 032
    // See brain-connection.test.ts for full BrainConnectionManager tests

    const net = require('net');
    jest.mock('net', () => ({
        createConnection: jest.fn(),
    }));

    const { BrainConnectionManager } = require('./brain-connection');
    const mockCreateConnection = net.createConnection as jest.Mock;

    interface FakeSocket {
        on: jest.Mock;
        write: jest.Mock;
        destroy: jest.Mock;
        emit: (event: string, ...args: unknown[]) => void;
    }

    function makeFakeSocket(): FakeSocket {
        const listeners: Record<string, Array<(...args: unknown[]) => void>> = {};
        const socket: FakeSocket = {
            on: jest.fn((event: string, cb: (...args: unknown[]) => void) => {
                if (!listeners[event]) { listeners[event] = []; }
                listeners[event].push(cb);
                return socket;
            }),
            write: jest.fn(),
            destroy: jest.fn(),
            emit: (event: string, ...args: unknown[]) => {
                (listeners[event] ?? []).forEach(cb => cb(...args));
            },
        };
        return socket;
    }

    function makeLogger() {
        const lines: string[] = [];
        return { lines, appendLine: (msg: string) => { lines.push(msg); } };
    }

    beforeEach(() => {
        jest.useFakeTimers();
        mockCreateConnection.mockReset();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    it('send() writes JSON-serialized message with newline delimiter when connected', () => {
        const fakeSocket = makeFakeSocket();
        let connectCallback: (() => void) | undefined;
        mockCreateConnection.mockImplementation(
            (_port: number, _host: string, cb: () => void) => {
                connectCallback = cb;
                return fakeSocket;
            },
        );

        const logger = makeLogger();
        const mgr = new BrainConnectionManager(
            'ws', 'ws', 8768, logger,
            () => ({ brainHost: 'localhost', brainPort: 8770 }),
        );
        mgr.connect();
        connectCallback!();  // trigger connection

        // Reset write calls from registration message
        fakeSocket.write.mockClear();

        const result = mgr.send({ type: 'focus', workspace: 'ws', timestamp: 12345 });
        expect(result).toBe(true);
        expect(fakeSocket.write).toHaveBeenCalledTimes(1);
        const written = fakeSocket.write.mock.calls[0][0] as string;
        expect(written.endsWith('\n')).toBe(true);
        const parsed = JSON.parse(written.trim());
        expect(parsed).toMatchObject({ type: 'focus', workspace: 'ws', timestamp: 12345 });
    });

    it('send() returns false when not connected (socket undefined)', () => {
        mockCreateConnection.mockReturnValue(makeFakeSocket());

        const logger = makeLogger();
        const mgr = new BrainConnectionManager(
            'ws', 'ws', 8768, logger,
            () => ({ brainHost: 'localhost', brainPort: 8770 }),
        );
        // Not calling connect() — socket is undefined

        const result = mgr.send({ type: 'focus', workspace: 'ws', timestamp: 0 });
        expect(result).toBe(false);
    });

    it('send() returns false after destroy() is called', () => {
        const fakeSocket = makeFakeSocket();
        let connectCallback: (() => void) | undefined;
        mockCreateConnection.mockImplementation(
            (_port: number, _host: string, cb: () => void) => {
                connectCallback = cb;
                return fakeSocket;
            },
        );

        const logger = makeLogger();
        const mgr = new BrainConnectionManager(
            'ws', 'ws', 8768, logger,
            () => ({ brainHost: 'localhost', brainPort: 8770 }),
        );
        mgr.connect();
        connectCallback!();
        mgr.destroy();

        fakeSocket.write.mockClear();
        const result = mgr.send({ type: 'blur', workspace: 'ws', timestamp: 0 });
        expect(result).toBe(false);
        expect(fakeSocket.write).not.toHaveBeenCalled();
    });

    it('send() returns false and does not throw when socket.write() throws', () => {
        const fakeSocket = makeFakeSocket();
        let connectCallback: (() => void) | undefined;
        mockCreateConnection.mockImplementation(
            (_port: number, _host: string, cb: () => void) => {
                connectCallback = cb;
                return fakeSocket;
            },
        );

        const logger = makeLogger();
        const mgr = new BrainConnectionManager(
            'ws', 'ws', 8768, logger,
            () => ({ brainHost: 'localhost', brainPort: 8770 }),
        );
        mgr.connect();
        connectCallback!();

        // Make write() throw
        fakeSocket.write.mockImplementation(() => { throw new Error('EPIPE'); });

        let result: boolean | undefined;
        expect(() => { result = mgr.send({ type: 'focus' }); }).not.toThrow();
        expect(result).toBe(false);
    });
});
