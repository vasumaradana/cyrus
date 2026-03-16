# Plan: 033-Add-extension-permission-handling

## Summary

Add `handleBrainMessage()`, `simulateKeyPress()`, and `simulateTextInput()` functions to the companion extension. When the brain sends `permission_respond` messages over the persistent connection (established by Issue 031), the extension simulates keyboard input: `1` for "allow", `Escape` for "deny". For `prompt_respond` messages, it pastes the provided text and presses Enter. All keyboard simulation is platform-specific (PowerShell on Windows, osascript on macOS, xdotool on Linux). Failures are logged but never thrown — the extension must never crash from a brain message.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `handleBrainMessage()` function | Does not exist | Create in extension.ts |
| `simulateKeyPress()` helper | Does not exist (but `tryEnterKey()` exists with same pattern) | Create new function |
| permission_respond → allow → press `1` | No handling | Add dispatch in handleBrainMessage |
| permission_respond → deny → press `Escape` | No handling | Add dispatch in handleBrainMessage |
| prompt_respond → paste text + Enter | No handling | Add simulateTextInput + dispatch |
| Platform-specific commands | Pattern exists in tryEnterKey/tryKeyboardSim | Follow same pattern |
| Failures logged not thrown | Pattern exists throughout extension | Follow same try/catch pattern |
| Brain message type definitions | No types — messages are untyped `any` | Create TypeScript interfaces |
| Tests | No test framework or test files in project | Add vitest + test file |

## Key Codebase Findings

### Existing keyboard simulation (extension.ts)

The extension already has platform-specific keyboard simulation in two functions:

1. **`tryEnterKey()`** (line 321): Simulates Enter key
   - Windows: `powershell ... SendKeys('{ENTER}')`
   - macOS: `osascript -e 'tell application "System Events" to key code 36'`
   - Linux: `xdotool key Return`

2. **`tryKeyboardSim()`** (line 345): Simulates Ctrl+V + Enter
   - Windows: `powershell ... SendKeys('^v'); SendKeys('{ENTER}')`
   - macOS: `osascript keystroke "v" using {command down}` + `key code 36`
   - Linux: `xdotool key ctrl+v Return`

Both use `execAsync` (line 27: `const execAsync = promisify(child_process.exec)`) with 3000–5000ms timeouts.

### Module-level state

- `out: vscode.OutputChannel` — logging channel (line 41, set during `activate()`)
- `execAsync` — promisified `child_process.exec` (line 27)
- `os` import — `os.platform()` for platform detection (line 21)

### No brain connection yet

Issue 031 will establish the persistent TCP connection to the brain on port 8770. This issue creates the message handler function that 031 will wire into the connection's data handler. The handler must be module-scoped (accessible within extension.ts).

### No tests

Zero test files, no test framework, no test script in package.json. The extension has only `compile` and `watch` scripts.

## Design Decisions

### D1. Separate pure logic into `src/brain-handler.ts`

Create a new module containing:
- Brain message TypeScript interfaces
- `buildKeyPressCommand(key, platform)` — pure function returning shell command string
- `buildPasteCommand(platform)` — pure function returning paste command string
- `parseBrainMessage(raw)` — validates and narrows raw message to typed BrainMessage

**Rationale**: Pure functions are testable without mocking `execAsync`, `vscode`, or `os.platform()`. Side-effectful wrappers (`simulateKeyPress`, `simulateTextInput`, `handleBrainMessage`) stay in extension.ts with access to module-level state (`out`, `execAsync`).

### D2. Define TypeScript interfaces for brain messages

```typescript
interface PermissionRespondMessage {
    type: 'permission_respond';
    action: 'allow' | 'deny';
}

interface PromptRespondMessage {
    type: 'prompt_respond';
    text: string;
}

type BrainMessage = PermissionRespondMessage | PromptRespondMessage;
```

Provides compile-time safety and documents the brain→extension protocol from docs/13-docker-containerization.md Phase 2.

### D3. `buildKeyPressCommand` supports `1`, `Escape`, and `Enter`

Although the acceptance criteria only require `1` and `Escape`, adding `Enter` support completes the key set needed for `simulateTextInput()` (prompt_respond → paste + Enter). The Enter commands match exactly what `tryEnterKey()` already uses — this creates a path for future refactoring of `tryEnterKey()` to use the shared builder.

### D4. Fire-and-forget dispatch with `void` prefix

`handleBrainMessage()` is synchronous (`void`, not `Promise<void>`). It dispatches to async `simulateKeyPress`/`simulateTextInput` without awaiting — fire-and-forget. Each async function has internal try/catch so unhandled rejections cannot occur. The `void` prefix (`void simulateKeyPress('1')`) signals intentional promise discard to TypeScript.

**Rationale**: The brain connection handler should not block on keyboard simulation. The brain doesn't expect a response to these messages.

### D5. Add vitest for unit testing

Add `vitest` as a devDependency. Tests cover the pure functions in `brain-handler.ts` — no VS Code mocks needed. Exclude test files from `tsconfig.json` so `tsc` compilation doesn't include them.

**Rationale**: Zero-config TypeScript support, fast execution, standard test runner. The extension already has devDependencies (types, typescript), so adding vitest is consistent.

## Acceptance Criteria → Test Mapping

| AC | Test(s) |
|---|---|
| `handleBrainMessage()` recognizes `permission_respond` | `parseBrainMessage returns PermissionRespondMessage for valid allow/deny` |
| `handleBrainMessage()` recognizes `prompt_respond` | `parseBrainMessage returns PromptRespondMessage for valid message` |
| permission_respond allow → simulates `1` | `buildKeyPressCommand('1', 'win32/darwin/linux')` returns correct command |
| permission_respond deny → simulates `Escape` | `buildKeyPressCommand('Escape', 'win32/darwin/linux')` returns correct command |
| prompt_respond → pastes text + Enter | `buildPasteCommand('win32/darwin/linux')` returns correct command + `buildKeyPressCommand('Enter', ...)` |
| Platform-specific methods | All 3 platforms tested for each key in buildKeyPressCommand/buildPasteCommand |
| Failures logged but never thrown | `simulateKeyPress` try/catch pattern (verified by code review; integration test would need VS Code runtime) |
| Success logged with action taken | `simulateKeyPress` logs on success (same — verified by code review) |
| Rejects invalid messages | `parseBrainMessage returns null for unknown type / missing fields / non-object` |

## Implementation Steps

### Step 1: Set up test infrastructure

**Files**: `cyrus-companion/package.json`, `cyrus-companion/tsconfig.json`

**package.json changes**:
- Add `"test": "vitest run"` to scripts
- Add `"vitest": "^3.0.0"` to devDependencies

**tsconfig.json changes**:
- Add `"**/*.test.ts"` to exclude array (prevent test files from being compiled into `out/`)

**Run**: `cd cyrus-companion && npm install` — vitest installed

### Step 2 — RED: Write tests for buildKeyPressCommand

**File**: `cyrus-companion/src/brain-handler.test.ts`

Write tests for all key × platform combinations:

| Key | win32 | darwin | linux |
|---|---|---|---|
| `'1'` | `SendKeys('1')` | `keystroke "1"` | `xdotool key 1` |
| `'Escape'` | `SendKeys('{ESC}')` | `key code 53` | `xdotool key Escape` |
| `'Enter'` | `SendKeys('{ENTER}')` | `key code 36` | `xdotool key Return` |

Plus edge cases:
- Unknown key → returns `null`
- Unknown platform → returns `null`

**Run**: `cd cyrus-companion && npm test` → expect import failure (brain-handler.ts doesn't exist)

### Step 3 — GREEN: Create brain-handler.ts with types + buildKeyPressCommand

**File**: `cyrus-companion/src/brain-handler.ts`

Contents:
- `PermissionRespondMessage`, `PromptRespondMessage`, `BrainMessage` type exports
- `buildKeyPressCommand(key: string, platform: NodeJS.Platform): string | null`

Key-to-command mapping:

```
'1':
  win32:  powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "$s = New-Object -ComObject WScript.Shell; $s.SendKeys('1')"
  darwin: osascript -e 'tell application "System Events" to keystroke "1"'
  linux:  xdotool key 1

'Escape':
  win32:  powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "$s = New-Object -ComObject WScript.Shell; $s.SendKeys('{ESC}')"
  darwin: osascript -e 'tell application "System Events" to key code 53'
  linux:  xdotool key Escape

'Enter':
  win32:  powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "$s = New-Object -ComObject WScript.Shell; $s.SendKeys('{ENTER}')"
  darwin: osascript -e 'tell application "System Events" to key code 36'
  linux:  xdotool key Return
```

**Run**: `npm test` → buildKeyPressCommand tests pass

### Step 4 — RED: Write tests for buildPasteCommand

Add to `brain-handler.test.ts`:
- win32 → PowerShell `SendKeys('^v')`
- darwin → `osascript keystroke "v" using {command down}`
- linux → `xdotool key ctrl+v`
- Unknown platform → `null`

**Run**: `npm test` → expect failure (function doesn't exist)

### Step 5 — GREEN: Add buildPasteCommand

Add to `brain-handler.ts`:

```
buildPasteCommand(platform: NodeJS.Platform): string | null

win32:  powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command "$s = New-Object -ComObject WScript.Shell; $s.SendKeys('^v')"
darwin: osascript -e 'tell application "System Events" to keystroke "v" using {command down}'
linux:  xdotool key ctrl+v
```

**Run**: `npm test` → all command builder tests pass

### Step 6 — RED: Write tests for parseBrainMessage

Add to `brain-handler.test.ts`:
1. Valid `permission_respond` with `action: 'allow'` → returns typed message
2. Valid `permission_respond` with `action: 'deny'` → returns typed message
3. Valid `prompt_respond` with `text: 'hello'` → returns typed message
4. `prompt_respond` with missing text → returns message with `text: ''`
5. Unknown message type → returns `null`
6. Missing `type` field → returns `null`
7. Non-object input (string, null, number) → returns `null`
8. `permission_respond` with invalid action (not allow/deny) → returns `null`

**Run**: `npm test` → expect failure

### Step 7 — GREEN: Add parseBrainMessage

Add to `brain-handler.ts`:

```typescript
export function parseBrainMessage(raw: unknown): BrainMessage | null
```

Validates shape and narrows to typed `BrainMessage`. Returns `null` for anything invalid.

**Run**: `npm test` → all tests pass

### Step 8: Add simulateKeyPress, simulateTextInput, handleBrainMessage to extension.ts

**File**: `cyrus-companion/src/extension.ts`

**8a.** Add import at top (after existing imports):
```typescript
import { buildKeyPressCommand, buildPasteCommand, parseBrainMessage } from './brain-handler';
```

**8b.** Add `simulateKeyPress()` after the existing keyboard simulation section (~line 374):
```typescript
async function simulateKeyPress(key: string): Promise<void> {
    const command = buildKeyPressCommand(key, os.platform());
    if (!command) {
        out.appendLine(`[Brain] Unsupported key press: ${key} on ${os.platform()}`);
        return;
    }
    try {
        await execAsync(command, { timeout: 3000 });
        out.appendLine(`[Brain] Simulated key press: ${key}`);
    } catch (err) {
        out.appendLine(`[Brain] Failed to simulate ${key}: ${err}`);
    }
}
```

**8c.** Add `simulateTextInput()`:
```typescript
async function simulateTextInput(text: string): Promise<void> {
    try {
        await vscode.env.clipboard.writeText(text);
        await sleep(100);

        const pasteCmd = buildPasteCommand(os.platform());
        if (!pasteCmd) {
            out.appendLine(`[Brain] Unsupported paste on ${os.platform()}`);
            return;
        }
        await execAsync(pasteCmd, { timeout: 3000 });
        await sleep(100);

        const enterCmd = buildKeyPressCommand('Enter', os.platform());
        if (!enterCmd) {
            out.appendLine(`[Brain] Unsupported Enter on ${os.platform()}`);
            return;
        }
        await execAsync(enterCmd, { timeout: 3000 });
        out.appendLine(`[Brain] Simulated text input: ${text.slice(0, 50)}${text.length > 50 ? '…' : ''}`);
    } catch (err) {
        out.appendLine(`[Brain] Failed to simulate text input: ${err}`);
    }
}
```

**8d.** Add `handleBrainMessage()`:
```typescript
function handleBrainMessage(msg: unknown): void {
    const parsed = parseBrainMessage(msg);
    if (!parsed) {
        out.appendLine(`[Brain] Unknown or invalid message: ${JSON.stringify(msg).slice(0, 100)}`);
        return;
    }

    if (parsed.type === 'permission_respond') {
        out.appendLine(`[Brain] Permission respond: ${parsed.action}`);
        if (parsed.action === 'allow') {
            void simulateKeyPress('1');
        } else {
            void simulateKeyPress('Escape');
        }
    } else if (parsed.type === 'prompt_respond') {
        out.appendLine(`[Brain] Prompt respond: ${parsed.text.slice(0, 50)}${parsed.text.length > 50 ? '…' : ''}`);
        void simulateTextInput(parsed.text);
    }
}
```

**Design notes**:
- `void` prefix signals intentional fire-and-forget to TypeScript
- Each async function has internal try/catch — failures logged, never thrown
- `handleBrainMessage` is module-scoped — Issue 031 will call it from the brain connection data handler

### Step 9: Compile and verify

**Run**:
```bash
cd cyrus-companion && npm run compile
```

Verify:
1. TypeScript compiles without errors
2. `out/brain-handler.js` and `out/extension.js` are generated
3. No test files in `out/` directory (excluded by tsconfig)

**Run**:
```bash
cd cyrus-companion && npm test
```

Verify all tests pass.

## Files to Create/Modify

| File | Action | What Changes |
|---|---|---|
| `cyrus-companion/src/brain-handler.ts` | **Create** | Brain message types, pure command builder functions, message parser |
| `cyrus-companion/src/brain-handler.test.ts` | **Create** | Unit tests for all pure functions (27+ test cases) |
| `cyrus-companion/src/extension.ts` | **Modify** | Import brain-handler, add simulateKeyPress, simulateTextInput, handleBrainMessage |
| `cyrus-companion/package.json` | **Modify** | Add vitest devDependency, add test script |
| `cyrus-companion/tsconfig.json` | **Modify** | Exclude test files from compilation |

## Notes for Future Work

- **Issue 031 wiring**: When the brain connection is established, the data handler should call `handleBrainMessage(JSON.parse(line))` for each received message. The function is ready to be called.
- **Refactor `tryEnterKey()`**: Could be refactored to use `buildKeyPressCommand('Enter', ...)` + `execAsync`. Out of scope for this issue but would reduce duplication.
- **Refactor `tryKeyboardSim()`**: Similarly could use `buildPasteCommand` + `buildKeyPressCommand`. Out of scope.
- **Additional key support**: `buildKeyPressCommand` currently supports `1`, `Escape`, and `Enter`. A data-driven approach (key→command mapping object) would scale better if more keys are needed.
