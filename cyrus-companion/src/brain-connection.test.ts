/**
 * brain-connection.test.ts — TDD tests for BrainConnectionManager
 *
 * Tests cover all acceptance criteria from Issue 031:
 * - Connects to configured brainHost:brainPort
 * - Sends registration message on connect
 * - Auto-reconnect with exponential backoff (1s, 2s, 4s, max 30s)
 * - Backoff resets to 1s on successful connection
 * - Connection status logged to output channel
 * - Persistent connection (no reconnect after destroy)
 * - Incoming brain messages dispatched to handler
 */

import * as net from 'net';
import { BrainConnectionManager } from './brain-connection';

// ── Mocking net module ────────────────────────────────────────────────────────
// Use a factory so jest replaces the module with a plain writable mock object,
// avoiding the "Cannot redefine property" error from Node's non-configurable exports.

jest.mock('net', () => ({
    createConnection: jest.fn(),
}));

// Typed handle to the mocked createConnection function.
const mockCreateConnection = net.createConnection as jest.Mock;

// ── Fake socket type ──────────────────────────────────────────────────────────

/** Build a fake socket with controllable EventEmitter-style event triggering */
interface FakeSocket {
    on: jest.Mock;
    write: jest.Mock;
    destroy: jest.Mock;
    end: jest.Mock;
    emit: (event: string, ...args: unknown[]) => void;
}

function makeFakeSocket(): FakeSocket {
    const listeners: Record<string, Array<(...args: unknown[]) => void>> = {};
    const socket: FakeSocket = {
        on: jest.fn((event: string, cb: (...args: unknown[]) => void) => {
            if (!listeners[event]) {
                listeners[event] = [];
            }
            listeners[event].push(cb);
            return socket;
        }),
        write: jest.fn(),
        destroy: jest.fn(),
        end: jest.fn(),
        // helpers to fire events in tests
        emit: (event: string, ...args: unknown[]) => {
            (listeners[event] ?? []).forEach(cb => cb(...args));
        },
    };
    return socket;
}

// ── Logger mock ───────────────────────────────────────────────────────────────

function makeLogger() {
    const lines: string[] = [];
    return {
        lines,
        appendLine: (msg: string) => { lines.push(msg); },
    };
}

// ── Config helper ─────────────────────────────────────────────────────────────

function makeConfigGetter(host = 'localhost', port = 8770, token = 'test-token') {
    return () => ({ brainHost: host, brainPort: port, authToken: token });
}

// ─────────────────────────────────────────────────────────────────────────────

describe('BrainConnectionManager', () => {
    beforeEach(() => {
        jest.useFakeTimers();
        mockCreateConnection.mockReset();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    // ── Happy path ────────────────────────────────────────────────────────────

    describe('connect — happy path', () => {
        it('connects to configured brainHost and brainPort', () => {
            const fakeSocket = makeFakeSocket();
            mockCreateConnection.mockReturnValue(fakeSocket);

            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'myWorkspace', 'myWorkspace', 8768, logger,
                makeConfigGetter('192.168.1.5', 9000),
            );
            mgr.connect();

            expect(mockCreateConnection).toHaveBeenCalledWith(
                9000, '192.168.1.5', expect.any(Function),
            );
        });

        it('sends registration message on successful connection', () => {
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
                'myWorkspace', 'my_safe', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();
            connectCallback!(); // trigger the connect callback

            expect(fakeSocket.write).toHaveBeenCalledTimes(1);
            const written = fakeSocket.write.mock.calls[0][0] as string;
            const msg = JSON.parse(written.replace('\n', ''));
            expect(msg).toMatchObject({
                type: 'register',
                workspace: 'myWorkspace',
                safe: 'my_safe',
                port: 8768,
            });
        });

        it('logs connected message to output channel', () => {
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
                'ws', 'ws', 8768, logger, makeConfigGetter('brain-host', 8770),
            );
            mgr.connect();
            connectCallback!();

            const connected = logger.lines.find(l => l.includes('[Brain] Connected'));
            expect(connected).toBeDefined();
            expect(connected).toContain('brain-host:8770');
        });
    });

    // ── Reconnect backoff ─────────────────────────────────────────────────────

    describe('auto-reconnect with exponential backoff', () => {
        it('schedules reconnect after disconnect with initial 1s backoff', () => {
            const fakeSocket = makeFakeSocket();
            mockCreateConnection.mockReturnValue(fakeSocket);

            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();

            // Trigger close event
            fakeSocket.emit('close');

            const reconnectLog = logger.lines.find(l => l.includes('Reconnecting in 1000'));
            expect(reconnectLog).toBeDefined();
        });

        it('doubles backoff on each subsequent disconnect (1s → 2s → 4s)', () => {
            const sockets: FakeSocket[] = [];
            mockCreateConnection.mockImplementation(() => {
                const s = makeFakeSocket();
                sockets.push(s);
                return s;
            });

            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();

            // First disconnect → schedules 1s reconnect
            sockets[0].emit('close');
            expect(logger.lines.some(l => l.includes('Reconnecting in 1000'))).toBe(true);

            // Advance timer 1s → reconnects; then disconnect again → 2s backoff
            jest.advanceTimersByTime(1000);
            sockets[1].emit('close');
            expect(logger.lines.some(l => l.includes('Reconnecting in 2000'))).toBe(true);

            // Advance timer 2s → reconnects; then disconnect again → 4s backoff
            jest.advanceTimersByTime(2000);
            sockets[2].emit('close');
            expect(logger.lines.some(l => l.includes('Reconnecting in 4000'))).toBe(true);
        });

        it('caps backoff at 30s maximum', () => {
            const sockets: FakeSocket[] = [];
            mockCreateConnection.mockImplementation(() => {
                const s = makeFakeSocket();
                sockets.push(s);
                return s;
            });

            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();

            // Simulate many disconnects to drive backoff above 30s ceiling
            // Sequence: 1s, 2s, 4s, 8s, 16s, 32s (capped to 30s)
            const backoffs = [1000, 2000, 4000, 8000, 16000];
            for (let i = 0; i < backoffs.length; i++) {
                sockets[i].emit('close');
                jest.advanceTimersByTime(backoffs[i]);
            }

            // 6th disconnect → would be 32s, must be capped at 30s
            sockets[5].emit('close');
            const cappedLog = logger.lines.find(l => l.includes('Reconnecting in 30000'));
            expect(cappedLog).toBeDefined();
        });

        it('resets backoff to 1s on successful reconnection', () => {
            const sockets: FakeSocket[] = [];
            const connectCallbacks: Array<() => void> = [];
            mockCreateConnection.mockImplementation(
                (_port: number, _host: string, cb: () => void) => {
                    connectCallbacks.push(cb);
                    const s = makeFakeSocket();
                    sockets.push(s);
                    return s;
                },
            );

            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();
            connectCallbacks[0](); // first connect succeeds

            // Disconnect → 1s backoff (already at base)
            sockets[0].emit('close');
            jest.advanceTimersByTime(1000);

            // Second attempt: disconnect → 2s backoff
            sockets[1].emit('close');
            jest.advanceTimersByTime(2000);

            // Third attempt: SUCCESS → backoff resets
            connectCallbacks[2]();
            logger.lines.length = 0; // clear log

            // Now disconnect again → should be back to 1s
            sockets[2].emit('close');
            const resetLog = logger.lines.find(l => l.includes('Reconnecting in 1000'));
            expect(resetLog).toBeDefined();
        });
    });

    // ── Error handling ────────────────────────────────────────────────────────

    describe('error cases', () => {
        it('schedules reconnect on connection error', () => {
            const fakeSocket = makeFakeSocket();
            mockCreateConnection.mockReturnValue(fakeSocket);

            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();
            fakeSocket.emit('error', new Error('ECONNREFUSED'));

            const errorLog = logger.lines.find(l => l.includes('[Brain] Connection error'));
            expect(errorLog).toBeDefined();
            const reconnectLog = logger.lines.find(l => l.includes('Reconnecting in'));
            expect(reconnectLog).toBeDefined();
        });

        it('logs disconnect message when connection closes', () => {
            const fakeSocket = makeFakeSocket();
            mockCreateConnection.mockReturnValue(fakeSocket);

            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();
            fakeSocket.emit('close');

            expect(logger.lines.some(l => l.includes('[Brain] Disconnected'))).toBe(true);
        });

        it('does not reconnect after destroy() is called', () => {
            const fakeSocket = makeFakeSocket();
            mockCreateConnection.mockReturnValue(fakeSocket);

            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();
            mgr.destroy();

            // Simulate close after destroy
            fakeSocket.emit('close');

            // Advance timers — no reconnect should have been scheduled
            jest.advanceTimersByTime(5000);
            expect(mockCreateConnection).toHaveBeenCalledTimes(1);
        });

        it('logs invalid JSON from brain without crashing', () => {
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
                'ws', 'ws', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();
            connectCallback!();

            // Send invalid JSON
            fakeSocket.emit('data', Buffer.from('not-json\n'));
            expect(logger.lines.some(l => l.includes('[Brain] Invalid JSON'))).toBe(true);
        });
    });

    // ── Incoming messages ─────────────────────────────────────────────────────

    describe('incoming brain messages', () => {
        it('dispatches valid JSON messages to the message handler', () => {
            const fakeSocket = makeFakeSocket();
            let connectCallback: (() => void) | undefined;
            mockCreateConnection.mockImplementation(
                (_port: number, _host: string, cb: () => void) => {
                    connectCallback = cb;
                    return fakeSocket;
                },
            );

            const received: unknown[] = [];
            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger, makeConfigGetter(),
                (msg) => { received.push(msg); },
            );
            mgr.connect();
            connectCallback!();
            fakeSocket.emit('data', Buffer.from('{"type":"ping"}\n'));

            expect(received).toHaveLength(1);
            expect(received[0]).toMatchObject({ type: 'ping' });
        });

        it('handles multi-chunk messages (buffering)', () => {
            const fakeSocket = makeFakeSocket();
            let connectCallback: (() => void) | undefined;
            mockCreateConnection.mockImplementation(
                (_port: number, _host: string, cb: () => void) => {
                    connectCallback = cb;
                    return fakeSocket;
                },
            );

            const received: unknown[] = [];
            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger, makeConfigGetter(),
                (msg) => { received.push(msg); },
            );
            mgr.connect();
            connectCallback!();

            // Send data in two chunks
            fakeSocket.emit('data', Buffer.from('{"type":"hel'));
            fakeSocket.emit('data', Buffer.from('lo"}\n'));

            expect(received).toHaveLength(1);
            expect(received[0]).toMatchObject({ type: 'hello' });
        });

        it('logs received message type', () => {
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
                'ws', 'ws', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();
            connectCallback!();
            fakeSocket.emit('data', Buffer.from('{"type":"ack"}\n'));

            expect(logger.lines.some(l => l.includes('[Brain] Received: ack'))).toBe(true);
        });
    });

    // ── Edge cases ────────────────────────────────────────────────────────────

    describe('edge cases', () => {
        it('destroy() cancels a pending reconnect timer', () => {
            const sockets: FakeSocket[] = [];
            mockCreateConnection.mockImplementation(() => {
                const s = makeFakeSocket();
                sockets.push(s);
                return s;
            });

            const logger = makeLogger();
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger, makeConfigGetter(),
            );
            mgr.connect();

            // Trigger disconnect — this schedules a 1s reconnect timer
            sockets[0].emit('close');
            const countBefore = mockCreateConnection.mock.calls.length;

            // Destroy before timer fires
            mgr.destroy();
            jest.advanceTimersByTime(5000);

            // createConnection must not have been called again
            expect(mockCreateConnection.mock.calls.length).toBe(countBefore);
        });

        it('uses defaults localhost:8770 when config returns undefined', () => {
            const fakeSocket = makeFakeSocket();
            mockCreateConnection.mockReturnValue(fakeSocket);

            const logger = makeLogger();
            // getConfig returns defaults
            const mgr = new BrainConnectionManager(
                'ws', 'ws', 8768, logger,
                () => ({ brainHost: 'localhost', brainPort: 8770, authToken: 'test-token' }),
            );
            mgr.connect();

            expect(mockCreateConnection).toHaveBeenCalledWith(
                8770, 'localhost', expect.any(Function),
            );
        });
    });
});
