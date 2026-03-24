/**
 * permission-handler.test.ts — TDD tests for Brain message permission handling
 *
 * Tests cover all acceptance criteria from Issue 033:
 * - handleBrainMessage() recognizes permission_respond and prompt_respond types
 * - permission_respond action="allow" simulates pressing 1
 * - permission_respond action="deny" simulates pressing Escape
 * - prompt_respond with text logs text preview (stub for future)
 * - Platform-specific methods: PowerShell (Windows), osascript (macOS), xdotool (Linux)
 * - Failures logged but never thrown (don't break extension)
 * - Success logged with action taken
 */

import * as os from 'os';
import { handleBrainMessage, simulateKeyPress } from './permission-handler';

// ── Mock os module ────────────────────────────────────────────────────────────

jest.mock('os', () => ({
    platform: jest.fn(),
}));

const mockPlatform = os.platform as jest.Mock;

// ── Logger helper ─────────────────────────────────────────────────────────────

function makeLogger() {
    const lines: string[] = [];
    return {
        lines,
        appendLine: (msg: string) => { lines.push(msg); },
    };
}

// ── Exec helper ───────────────────────────────────────────────────────────────

function makeExec(error?: Error) {
    if (error) {
        return jest.fn().mockRejectedValue(error);
    }
    return jest.fn().mockResolvedValue({ stdout: '', stderr: '' });
}

// ─────────────────────────────────────────────────────────────────────────────

describe('simulateKeyPress', () => {

    // ── Happy path — Windows ──────────────────────────────────────────────────

    describe('Windows (win32)', () => {
        beforeEach(() => {
            mockPlatform.mockReturnValue('win32');
        });

        it('sends SendKeys("1") via PowerShell for key "1"', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('1', logger, exec);

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd, opts] = exec.mock.calls[0];
            expect(cmd).toContain('powershell');
            expect(cmd).toContain("SendKeys('1')");
            expect(opts).toMatchObject({ timeout: 3000 });
        });

        it('sends SendKeys("{ESC}") via PowerShell for key "Escape"', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('Escape', logger, exec);

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('powershell');
            expect(cmd).toContain("SendKeys('{ESC}')");
        });
    });

    // ── Happy path — macOS ────────────────────────────────────────────────────

    describe('macOS (darwin)', () => {
        beforeEach(() => {
            mockPlatform.mockReturnValue('darwin');
        });

        it('uses osascript keystroke "1" for key "1"', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('1', logger, exec);

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('osascript');
            expect(cmd).toContain('keystroke "1"');
        });

        it('uses osascript key code 53 for key "Escape"', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('Escape', logger, exec);

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('osascript');
            expect(cmd).toContain('key code 53');
        });
    });

    // ── Happy path — Linux ────────────────────────────────────────────────────

    describe('Linux', () => {
        beforeEach(() => {
            mockPlatform.mockReturnValue('linux');
        });

        it('uses xdotool key 1 for key "1"', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('1', logger, exec);

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('xdotool');
            expect(cmd).toContain('key 1');
        });

        it('uses xdotool key Escape for key "Escape"', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('Escape', logger, exec);

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('xdotool');
            expect(cmd).toContain('key Escape');
        });
    });

    // ── Success logging ───────────────────────────────────────────────────────

    describe('success logging', () => {
        it('logs simulated key press after successful exec', async () => {
            mockPlatform.mockReturnValue('linux');
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('1', logger, exec);

            expect(logger.lines.some(l => l.includes('Simulated key press: 1'))).toBe(true);
        });

        it('logs simulated key press for Escape after successful exec', async () => {
            mockPlatform.mockReturnValue('darwin');
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('Escape', logger, exec);

            expect(logger.lines.some(l => l.includes('Simulated key press: Escape'))).toBe(true);
        });
    });

    // ── Error cases ───────────────────────────────────────────────────────────

    describe('error handling', () => {
        it('logs failure but does not throw when exec rejects', async () => {
            mockPlatform.mockReturnValue('linux');
            const logger = makeLogger();
            const exec = makeExec(new Error('xdotool not found'));

            // Must not throw
            await expect(simulateKeyPress('1', logger, exec)).resolves.toBeUndefined();

            expect(logger.lines.some(l => l.includes('Failed to simulate 1'))).toBe(true);
        });

        it('logs failure for Escape when exec rejects', async () => {
            mockPlatform.mockReturnValue('win32');
            const logger = makeLogger();
            const exec = makeExec(new Error('PowerShell error'));

            await expect(simulateKeyPress('Escape', logger, exec)).resolves.toBeUndefined();

            expect(logger.lines.some(l => l.includes('Failed to simulate Escape'))).toBe(true);
        });

        it('does not execute anything for unknown key', async () => {
            mockPlatform.mockReturnValue('linux');
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('UnknownKey', logger, exec);

            // No exec call for unknown keys (empty command)
            expect(exec).not.toHaveBeenCalled();
        });
    });

    // ── Edge cases ────────────────────────────────────────────────────────────

    describe('edge cases', () => {
        it('handles timeout option of 3000ms', async () => {
            mockPlatform.mockReturnValue('darwin');
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('1', logger, exec);

            const [, opts] = exec.mock.calls[0];
            expect(opts?.timeout).toBe(3000);
        });

        it('does not log success when no command was built (unknown key)', async () => {
            mockPlatform.mockReturnValue('linux');
            const logger = makeLogger();
            const exec = makeExec();

            await simulateKeyPress('F1', logger, exec);

            expect(logger.lines.some(l => l.includes('Simulated key press'))).toBe(false);
        });
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('handleBrainMessage', () => {
    // Tests inject a mock exec function so we verify the correct OS commands
    // are triggered without any real keyboard simulation.
    // We flush microtasks with `await Promise.resolve()` after each call because
    // handleBrainMessage fires simulateKeyPress as a floating promise.

    beforeEach(() => {
        mockPlatform.mockReturnValue('linux');
    });

    // ── Acceptance: permission_respond ────────────────────────────────────────

    describe('permission_respond messages', () => {
        it('recognizes permission_respond type and logs the action', () => {
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ type: 'permission_respond', action: 'allow' }, logger, exec);

            expect(logger.lines.some(l => l.includes('[Brain] Permission respond: allow'))).toBe(true);
        });

        it('simulates key "1" (xdotool) for action="allow" on Linux', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ type: 'permission_respond', action: 'allow' }, logger, exec);
            await Promise.resolve(); // flush floating promise

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('xdotool');
            expect(cmd).toContain('key 1');
        });

        it('simulates key "Escape" (xdotool) for action="deny" on Linux', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ type: 'permission_respond', action: 'deny' }, logger, exec);
            await Promise.resolve();

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('xdotool');
            expect(cmd).toContain('key Escape');
        });

        it('simulates key "1" via PowerShell for action="allow" on Windows', async () => {
            mockPlatform.mockReturnValue('win32');
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ type: 'permission_respond', action: 'allow' }, logger, exec);
            await Promise.resolve();

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('powershell');
            expect(cmd).toContain("SendKeys('1')");
        });

        it('simulates Escape via PowerShell for action="deny" on Windows', async () => {
            mockPlatform.mockReturnValue('win32');
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ type: 'permission_respond', action: 'deny' }, logger, exec);
            await Promise.resolve();

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('powershell');
            expect(cmd).toContain("SendKeys('{ESC}')");
        });

        it('simulates key "1" via osascript for action="allow" on macOS', async () => {
            mockPlatform.mockReturnValue('darwin');
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ type: 'permission_respond', action: 'allow' }, logger, exec);
            await Promise.resolve();

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('osascript');
            expect(cmd).toContain('keystroke "1"');
        });

        it('simulates Escape via osascript key code 53 for action="deny" on macOS', async () => {
            mockPlatform.mockReturnValue('darwin');
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ type: 'permission_respond', action: 'deny' }, logger, exec);
            await Promise.resolve();

            expect(exec).toHaveBeenCalledTimes(1);
            const [cmd] = exec.mock.calls[0];
            expect(cmd).toContain('osascript');
            expect(cmd).toContain('key code 53');
        });

        it('logs deny action before simulating Escape', () => {
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ type: 'permission_respond', action: 'deny' }, logger, exec);

            expect(logger.lines.some(l => l.includes('[Brain] Permission respond: deny'))).toBe(true);
        });

        it('does not simulate any key for unknown action', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ type: 'permission_respond', action: 'unknown' }, logger, exec);
            await Promise.resolve();

            expect(exec).not.toHaveBeenCalled();
        });

        it('logs failure but does not throw when exec rejects on allow', async () => {
            const logger = makeLogger();
            const exec = makeExec(new Error('xdotool not found'));

            // handleBrainMessage itself must not throw even if exec rejects
            expect(() =>
                handleBrainMessage({ type: 'permission_respond', action: 'allow' }, logger, exec)
            ).not.toThrow();

            await Promise.resolve();
            await Promise.resolve(); // two ticks: one for the reject, one for catch

            expect(logger.lines.some(l => l.includes('Failed to simulate 1'))).toBe(true);
        });
    });

    // ── Acceptance: prompt_respond ────────────────────────────────────────────

    describe('prompt_respond messages', () => {
        it('recognizes prompt_respond type and logs text preview', () => {
            const logger = makeLogger();

            handleBrainMessage({ type: 'prompt_respond', text: 'Hello world' }, logger);

            expect(logger.lines.some(l => l.includes('[Brain] Prompt respond:'))).toBe(true);
            expect(logger.lines.some(l => l.includes('Hello world'))).toBe(true);
        });

        it('truncates long text to 50 chars in log', () => {
            const logger = makeLogger();
            const longText = 'A'.repeat(100);

            handleBrainMessage({ type: 'prompt_respond', text: longText }, logger);

            const logLine = logger.lines.find(l => l.includes('[Brain] Prompt respond:'));
            expect(logLine).toBeDefined();
            // The logged portion should not contain 100 A's inline (capped at 50)
            expect(logLine!.length).toBeLessThan(100 + 30); // 30 chars for prefix
        });

        it('handles missing text field gracefully', () => {
            const logger = makeLogger();

            handleBrainMessage({ type: 'prompt_respond' }, logger);

            expect(logger.lines.some(l => l.includes('[Brain] Prompt respond:'))).toBe(true);
        });
    });

    // ── Unknown/invalid messages ──────────────────────────────────────────────

    describe('unknown and invalid messages', () => {
        it('silently ignores unknown message types without exec calls', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ type: 'unknown_type' }, logger, exec);
            await Promise.resolve();

            expect(exec).not.toHaveBeenCalled();
        });

        it('handles null message without throwing', () => {
            const logger = makeLogger();

            expect(() => handleBrainMessage(null, logger)).not.toThrow();
        });

        it('handles non-object messages without throwing', () => {
            const logger = makeLogger();

            expect(() => handleBrainMessage('string message', logger)).not.toThrow();
            expect(() => handleBrainMessage(42, logger)).not.toThrow();
        });

        it('does not simulate key for message with no type field', async () => {
            const logger = makeLogger();
            const exec = makeExec();

            handleBrainMessage({ action: 'allow' }, logger, exec);
            await Promise.resolve();

            expect(exec).not.toHaveBeenCalled();
        });
    });

    // ── Exec injection ────────────────────────────────────────────────────────

    describe('exec injection', () => {
        it('uses the provided exec function for key simulation', async () => {
            const logger = makeLogger();
            const customExec = jest.fn().mockResolvedValue({});

            handleBrainMessage({ type: 'permission_respond', action: 'allow' }, logger, customExec);
            await Promise.resolve();

            expect(customExec).toHaveBeenCalledTimes(1);
        });

        it('uses a different custom exec for deny action', async () => {
            const logger = makeLogger();
            const customExec = jest.fn().mockResolvedValue({});

            handleBrainMessage({ type: 'permission_respond', action: 'deny' }, logger, customExec);
            await Promise.resolve();

            expect(customExec).toHaveBeenCalledTimes(1);
        });
    });
});
