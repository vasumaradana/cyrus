/**
 * extension.ts — Cyrus Companion VS Code Extension
 *
 * Platform-adaptive IPC for submitting text to Claude Code's chat panel.
 *
 * Windows:    TCP on 127.0.0.1 (dynamic port). Port written to a discovery file
 *             at %LOCALAPPDATA%\cyrus\companion-{workspace}.port so the brain
 *             can find the right port per workspace. No AF_UNIX needed.
 *
 * macOS/Linux: Unix domain socket at /tmp/cyrus-companion-{workspace}.sock
 *
 * Protocol (same on both transports): line-delimited JSON
 *   Brain  → ext:  {"text": "message"}\n
 *   Ext → brain:   {"ok": true, "method": "..."}\n
 *
 * Zero runtime npm dependencies — Node.js built-ins + VS Code API only.
 */

import * as vscode from 'vscode';
import * as net from 'net';
import * as os from 'os';
import * as path from 'path';
import * as fs from 'fs';
import * as child_process from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(child_process.exec);

// ── Focus command candidates ──────────────────────────────────────────────────

const FOCUS_CANDIDATES: readonly string[] = [
    'workbench.view.extension.claude-code',
    'workbench.view.claude',
    'claude.focus',
    'workbench.action.chat.open',
];

// ── Module-level state ────────────────────────────────────────────────────────

let server: net.Server | undefined;
let cleanupPath: string | undefined;   // discovery file (Windows) or socket file (Unix)
let out: vscode.OutputChannel;

// ── Activation / deactivation ─────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext): void {
    out = vscode.window.createOutputChannel('Cyrus Companion');

    const workspaceName = vscode.workspace.workspaceFolders?.[0]?.name ?? 'default';
    const safe = workspaceName.replace(/[^\w\-]/g, '_').slice(0, 40);

    out.appendLine(`[Cyrus] Workspace: ${workspaceName}  (safe: ${safe})`);

    startServer(safe)
        .then(() => out.appendLine('[Cyrus] Ready.'))
        .catch(err => {
            const msg = err instanceof Error ? err.message : String(err);
            out.appendLine(`[Cyrus] FAILED to start: ${msg}`);
            vscode.window.showWarningMessage(`Cyrus Companion: ${msg}`);
        });

    context.subscriptions.push({
        dispose: () => {
            server?.close();
            tryUnlink(cleanupPath);
        },
    });
}

export function deactivate(): void {
    server?.close();
    tryUnlink(cleanupPath);
}

// ── Platform-adaptive server start ────────────────────────────────────────────

async function startServer(safe: string): Promise<void> {
    server = net.createServer(handleConnection);

    if (os.platform() === 'win32') {
        await startTcp(server, safe);
    } else {
        await startUnixSocket(server, safe);
    }
}

async function startTcp(srv: net.Server, safe: string): Promise<void> {
    const dir = discoveryDir();
    const discoveryFile = path.join(dir, `companion-${safe}.port`);

    const port = await listenOnFreePort(srv, 8768, 8778);

    fs.writeFileSync(discoveryFile, String(port), 'utf-8');
    cleanupPath = discoveryFile;

    out.appendLine(`[Cyrus] TCP 127.0.0.1:${port}`);
    out.appendLine(`[Cyrus] Discovery: ${discoveryFile}`);
}

async function startUnixSocket(srv: net.Server, safe: string): Promise<void> {
    const sockPath = path.join(os.tmpdir(), `cyrus-companion-${safe}.sock`);
    tryUnlink(sockPath);

    await new Promise<void>((resolve, reject) => {
        srv.once('error', reject);
        srv.listen(sockPath, () => {
            srv.removeListener('error', reject);
            resolve();
        });
    });

    cleanupPath = sockPath;
    out.appendLine(`[Cyrus] Socket: ${sockPath}`);
}

// ── TCP port scan ─────────────────────────────────────────────────────────────

function listenOnFreePort(srv: net.Server, start: number, end: number): Promise<number> {
    return new Promise((resolve, reject) => {
        let port = start;

        function attempt(): void {
            if (port > end) {
                reject(new Error(`No free port in range ${start}–${end}`));
                return;
            }

            // Remove any listeners from previous attempt
            srv.removeAllListeners('error');
            srv.removeAllListeners('listening');

            srv.once('error', (err: NodeJS.ErrnoException) => {
                if (err.code === 'EADDRINUSE' && port < end) {
                    port++;
                    // Must close before retrying listen
                    srv.close(() => attempt());
                } else {
                    reject(err);
                }
            });

            srv.listen(port, '127.0.0.1', () => {
                srv.removeAllListeners('error');
                resolve(port);
            });
        }

        attempt();
    });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function discoveryDir(): string {
    const base = process.env.LOCALAPPDATA ?? os.homedir();
    const dir = path.join(base, 'cyrus');
    try { fs.mkdirSync(dir, { recursive: true }); } catch { /* exists */ }
    return dir;
}

function tryUnlink(p: string | undefined): void {
    if (p) {
        try { fs.unlinkSync(p); } catch { /* already gone */ }
    }
}

// ── Connection handler (shared by TCP and Unix socket) ────────────────────────

function handleConnection(socket: net.Socket): void {
    let buf = '';

    socket.on('data', (chunk: Buffer) => {
        buf += chunk.toString();

        const nl = buf.indexOf('\n');
        if (nl === -1) return;

        const line = buf.slice(0, nl);
        buf = '';

        let text: string;
        try {
            const msg = JSON.parse(line) as { text?: unknown };
            if (typeof msg.text !== 'string' || !msg.text.trim()) {
                end(socket, { ok: false, error: 'Missing or empty text field' });
                return;
            }
            text = msg.text;
        } catch {
            end(socket, { ok: false, error: 'Invalid JSON' });
            return;
        }

        const preview = text.length > 80 ? text.slice(0, 80) + '…' : text;
        out.appendLine(`[Cyrus] Submitting: ${preview}`);

        submitText(text)
            .then(result => end(socket, result))
            .catch(err => end(socket, { ok: false, error: String(err) }));
    });

    socket.on('error', () => { /* client disconnected early */ });
}

function end(socket: net.Socket, result: object): void {
    try {
        socket.end(JSON.stringify(result) + '\n');
    } catch { /* socket already closed */ }
}

// ── Submit pipeline ───────────────────────────────────────────────────────────

interface Result { ok: boolean; method?: string; error?: string; }

async function submitText(text: string): Promise<Result> {
    await focusChatPanel();

    await vscode.env.clipboard.writeText(text);
    await sleep(50);

    const vscResult = await tryVscodeSubmit();
    if (vscResult.ok) {
        return vscResult;
    }
    out.appendLine(`[Cyrus] VS Code commands failed (${vscResult.error}) — trying keyboard sim`);

    return tryKeyboardSim();
}

// ── Focus chat panel ──────────────────────────────────────────────────────────

async function focusChatPanel(): Promise<void> {
    const configured = vscode.workspace
        .getConfiguration('cyrusCompanion')
        .get<string>('focusCommand', '')
        .trim();

    const candidates = configured
        ? [configured, ...FOCUS_CANDIDATES.filter(c => c !== configured)]
        : [...FOCUS_CANDIDATES];

    for (const cmd of candidates) {
        try {
            await vscode.commands.executeCommand(cmd);
            out.appendLine(`[Cyrus] Focused via: ${cmd}`);
            await sleep(150);
            return;
        } catch {
            // Not registered — try next
        }
    }

    out.appendLine('[Cyrus] Could not focus chat panel — proceeding anyway');
}

// ── VS Code command submit ────────────────────────────────────────────────────

async function tryVscodeSubmit(): Promise<Result> {
    try {
        await vscode.commands.executeCommand('editor.action.clipboardPasteAction');
        await sleep(50);
    } catch {
        // Chat input may not be an editor widget — acceptable
    }

    try {
        await vscode.commands.executeCommand('workbench.action.chat.submit');
        out.appendLine('[Cyrus] Submitted via workbench.action.chat.submit');
        return { ok: true, method: 'vscode-commands' };
    } catch (err) {
        return { ok: false, error: `chat.submit unavailable: ${err}` };
    }
}

// ── Platform keyboard simulation fallback ─────────────────────────────────────

async function tryKeyboardSim(): Promise<Result> {
    const platform = os.platform();

    try {
        if (platform === 'win32') {
            const ps = [
                '$s = New-Object -ComObject WScript.Shell',
                '$s.SendKeys("^v")',
                'Start-Sleep -Milliseconds 80',
                '$s.SendKeys("{ENTER}")',
            ].join('; ');
            await execAsync(
                `powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "${ps}"`,
                { timeout: 5000 }
            );
        } else if (platform === 'darwin') {
            await execAsync(
                `osascript -e 'tell application "System Events" to keystroke "v" using {command down}'`,
                { timeout: 3000 }
            );
            await sleep(80);
            await execAsync(
                `osascript -e 'tell application "System Events" to key code 36'`,
                { timeout: 3000 }
            );
        } else {
            await execAsync('xdotool key ctrl+v Return', { timeout: 3000 });
        }

        out.appendLine(`[Cyrus] Submitted via keyboard sim (${platform})`);
        return { ok: true, method: `keyboard-sim-${platform}` };
    } catch (err) {
        return { ok: false, error: `keyboard sim failed: ${err}` };
    }
}

// ── Utility ───────────────────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}
