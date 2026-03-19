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
import { BrainConnectionManager } from './brain-connection';
import { createFocusHandler } from './focus-tracker';
import { handleBrainMessage as dispatchBrainMessage } from './permission-handler';

const execAsync = promisify(child_process.exec);

// ── Focus command candidates ──────────────────────────────────────────────────

const FOCUS_CANDIDATES: readonly string[] = [
    'claude-vscode.focus',              // Claude Code: Focus input
    'claude-vscode.sidebar.open',       // Claude Code: Open in Side Bar
    'workbench.view.extension.claude-sidebar',
];

// ── Module-level state ────────────────────────────────────────────────────────

let server: net.Server | undefined;
let cleanupPath: string | undefined;   // discovery file (Windows) or socket file (Unix)
let out: vscode.OutputChannel;
let brainManager: BrainConnectionManager | undefined;

// ── Activation / deactivation ─────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext): void {
    out = vscode.window.createOutputChannel('Cyrus Companion');

    const workspaceName = vscode.workspace.workspaceFolders?.[0]?.name ?? 'default';
    const safe = workspaceName.replace(/[^\w\-]/g, '_').slice(0, 40);

    out.appendLine(`[Cyrus] Workspace: ${workspaceName}  (safe: ${safe})`);

    startServer(safe)
        .then(listenPort => {
            out.appendLine('[Cyrus] Ready.');
            // Connect to brain after the inbound server is up so we can include our port.
            brainManager = new BrainConnectionManager(
                workspaceName, safe, listenPort, out,
                () => ({
                    brainHost: vscode.workspace
                        .getConfiguration('cyrusCompanion')
                        .get<string>('brainHost', 'localhost'),
                    brainPort: vscode.workspace
                        .getConfiguration('cyrusCompanion')
                        .get<number>('brainPort', 8770),
                }),
                handleBrainMessage,
            );
            brainManager.connect();
        })
        .catch(err => {
            const msg = err instanceof Error ? err.message : String(err);
            out.appendLine(`[Cyrus] FAILED to start: ${msg}`);
            vscode.window.showWarningMessage(`Cyrus Companion: ${msg}`);
        });

    // Register focus/blur tracking so the brain knows which workspace window is active.
    // The handler guards against a null brainManager (safe to register before connect()).
    const focusDisposable = vscode.window.onDidChangeWindowState(
        createFocusHandler(
            () => brainManager,
            () => vscode.workspace.workspaceFolders?.[0]?.name ?? 'default',
            out,
        ),
    );

    context.subscriptions.push(focusDisposable);
    context.subscriptions.push({
        dispose: () => {
            brainManager?.destroy();
            server?.close();
            tryUnlink(cleanupPath);
        },
    });
}

export function deactivate(): void {
    brainManager?.destroy();
    server?.close();
    tryUnlink(cleanupPath);
}

// ── Platform-adaptive server start ────────────────────────────────────────────

/** Start the inbound server and return the listen port (TCP port on Windows, 0 on Unix). */
async function startServer(safe: string): Promise<number> {
    server = net.createServer(handleConnection);

    if (os.platform() === 'win32') {
        return startTcp(server, safe);
    } else {
        return startUnixSocket(server, safe);
    }
}

/** Start TCP server, write discovery file, return bound port. */
async function startTcp(srv: net.Server, safe: string): Promise<number> {
    const dir = discoveryDir();
    const discoveryFile = path.join(dir, `companion-${safe}.port`);

    const port = await listenOnFreePort(srv, 8768, 8778);

    fs.writeFileSync(discoveryFile, String(port), 'utf-8');
    cleanupPath = discoveryFile;

    out.appendLine(`[Cyrus] TCP 127.0.0.1:${port}`);
    out.appendLine(`[Cyrus] Discovery: ${discoveryFile}`);
    return port;
}

/** Start Unix socket server; returns 0 (port not meaningful for socket transport). */
async function startUnixSocket(srv: net.Server, safe: string): Promise<number> {
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
    return 0;   // Port not meaningful for Unix socket transport
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
    // 1. Bring VS Code to foreground (OS-level) + focus Claude Code input
    await bringVscodeToFront();
    await focusChatPanel();

    // 2. Write text to clipboard
    await vscode.env.clipboard.writeText(text);
    await sleep(100);

    // 3. Paste via VS Code's own command (runs in-process, always targets focused editor/webview)
    try {
        await vscode.commands.executeCommand('editor.action.clipboardPasteAction');
        out.appendLine('[Cyrus] Pasted via editor.action.clipboardPasteAction');
    } catch {
        out.appendLine('[Cyrus] Paste command failed, falling back to keyboard sim');
        return tryKeyboardSim();
    }
    await sleep(300);

    // 4. Submit with Enter via SendKeys (VS Code is already foreground)
    return tryEnterKey();
}

// ── Bring VS Code window to OS foreground ────────────────────────────────────

async function bringVscodeToFront(): Promise<void> {
    if (os.platform() !== 'win32') { return; }
    try {
        // Alt-key trick bypasses Windows' SetForegroundWindow restriction
        // keybd_event(Alt down/up) lets a background process steal focus
        const ps = `
Add-Type @'
using System; using System.Runtime.InteropServices;
public class WinFocus {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern void keybd_event(byte k, byte s, uint f, UIntPtr e);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    public static void Activate(IntPtr h) {
        ShowWindow(h, 9);
        keybd_event(0x12, 0, 0, UIntPtr.Zero);
        keybd_event(0x12, 0, 2, UIntPtr.Zero);
        SetForegroundWindow(h);
    }
}
'@
$h = (Get-Process -Name Code | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowHandle
if ($h) { [WinFocus]::Activate($h) }
`;
        const encoded = Buffer.from(ps, 'utf16le').toString('base64');
        await execAsync(
            `powershell -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ${encoded}`,
            { timeout: 5000 }
        );
        await sleep(200);
        out.appendLine('[Cyrus] Brought VS Code to foreground via SetForegroundWindow');
    } catch (err) {
        out.appendLine(`[Cyrus] Could not bring VS Code to foreground: ${err}`);
    }
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

// ── Platform keyboard simulation ──────────────────────────────────────────────

async function tryEnterKey(): Promise<Result> {
    const platform = os.platform();
    try {
        if (platform === 'win32') {
            const ps = "$s = New-Object -ComObject WScript.Shell; $s.SendKeys('{ENTER}')";
            await execAsync(
                `powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "${ps}"`,
                { timeout: 5000 }
            );
        } else if (platform === 'darwin') {
            await execAsync(
                `osascript -e 'tell application "System Events" to key code 36'`,
                { timeout: 3000 }
            );
        } else {
            await execAsync('xdotool key Return', { timeout: 3000 });
        }
        out.appendLine(`[Cyrus] Submitted via Enter key (${platform})`);
        return { ok: true, method: `enter-key-${platform}` };
    } catch (err) {
        return { ok: false, error: `Enter key failed: ${err}` };
    }
}

async function tryKeyboardSim(): Promise<Result> {
    const platform = os.platform();

    try {
        if (platform === 'win32') {
            const ps = "$s = New-Object -ComObject WScript.Shell; $s.SendKeys('^v'); Start-Sleep -Milliseconds 80; $s.SendKeys('{ENTER}')";
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

// ── Brain message handler ─────────────────────────────────────────────────────

/**
 * Handle an incoming message from the Cyrus Brain.
 * Delegates to permission-handler.ts which handles permission_respond and
 * prompt_respond message types via platform-adaptive keyboard simulation.
 *
 * @param msg Parsed JSON message from the brain.
 */
function handleBrainMessage(msg: unknown): void {
    dispatchBrainMessage(msg, out);
}

// ── Utility ───────────────────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}
