# Dockerize Cyrus Brain for Cross-Platform Support

## Context
The brain (`cyrus_brain.py`) currently requires Windows-specific dependencies (UIAutomation, comtypes, pyautogui, pygetwindow) for VS Code automation. This limits it to Windows. Containerizing the brain removes all OS-specific GUI dependencies, making it run identically on macOS, Linux, and Windows via Docker.

## Core Insight
The brain already has two paths for most operations:
1. **UIA path** (Windows-only): walks VS Code's UI tree directly
2. **Companion extension + hooks path** (cross-platform): uses TCP/socket IPC

The Docker strategy: run brain in **headless mode** using only path #2, and enhance the companion extension to cover the gaps.

---

## Phase 1: Add `HEADLESS` Mode to `cyrus_brain.py`

**File:** `cyrus_brain.py`

Add `HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1"` at top. Guard all Windows imports:

```python
HEADLESS = os.environ.get("CYRUS_HEADLESS") == "1"
if not HEADLESS:
    import comtypes, pyautogui, pyperclip, pygetwindow as gw
    # ... uiautomation import block
```

### Changes per component:

| Component | Current (UIA) | Headless replacement |
|-----------|--------------|---------------------|
| **Session discovery** (`_vs_code_windows`) | `pygetwindow.getAllWindows()` | Companion extensions register on connect (new port 8770) |
| **Active window tracking** (`_start_active_tracker`) | Polls `gw.getActiveWindow()` | Companion sends focus/blur events |
| **Chat response detection** (`ChatWatcher`) | UIA tree polling every 0.5s | Hooks-only (Stop event on :8767, already works) |
| **Permission detection** (`PermissionWatcher._scan`) | UIA tree polling every 0.3s | Hook pre-arm + companion handles UI clicks |
| **Permission response** (`PermissionWatcher.handle_response`) | `pyautogui.press("1")` / `btn.Click()` | Send `permission_respond` message to companion |
| **Text submission** (`_submit_to_vscode_impl`) | UIA fallback with pyautogui | Companion extension only (already primary path) |

---

## Phase 2: Companion Extension Registration Protocol

**File:** `cyrus-companion/src/extension.ts`

Add persistent outbound connection from extension to brain on port **8770**.

### New messages — Extension → Brain:
```json
{"type": "register", "workspace": "my-project", "safe": "my_project", "port": 8768}
{"type": "focus", "workspace": "my-project"}
{"type": "blur", "workspace": "my-project"}
```

### New messages — Brain → Extension (over same connection):
```json
{"type": "permission_respond", "action": "allow"}
{"type": "permission_respond", "action": "deny"}
{"type": "prompt_respond", "text": "user answer"}
```

### Extension changes:
1. **On activate**: Connect to `brainHost:8770`, send `register` with workspace + listen port. Auto-reconnect with backoff.
2. **Focus tracking**: Hook `vscode.window.onDidChangeWindowState` → send `focus`/`blur`
3. **Permission handling**: On receiving `permission_respond`, simulate keyboard press (`1` for allow, `Escape` for deny)
4. **New setting**: `cyrusCompanion.brainHost` (default: `localhost`) and `cyrusCompanion.brainPort` (default: `8770`)

**File:** `cyrus-companion/package.json` — add new settings

---

## Phase 3: Brain-side Registration Listener

**File:** `cyrus_brain.py`

Add async TCP server on port 8770 (headless mode only):

- Maintain `_registered_sessions: dict[str, SessionInfo]` with workspace name, connection, port
- On `register`: add session, create ChatWatcher (hooks-only) + PermissionWatcher (hooks-only)
- On `focus`: update `_active_project`
- On `blur`: clear active if it was this project
- On disconnect: remove session
- Route `permission_respond` / `prompt_respond` back over the persistent connection

---

## Phase 4: Docker Files

**New file:** `Dockerfile`
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements-brain-headless.txt .
RUN pip install --no-cache-dir -r requirements-brain-headless.txt
COPY cyrus_brain.py cyrus_hook.py cyrus_server.py .env* ./
ENV CYRUS_HEADLESS=1
EXPOSE 8766 8767 8769 8770
CMD ["python", "cyrus_brain.py"]
```

**New file:** `requirements-brain-headless.txt`
```
python-dotenv
websockets
```

**New file:** `docker-compose.yml`
```yaml
services:
  brain:
    build: .
    ports:
      - "8766:8766"
      - "8767:8767"
      - "8769:8769"
      - "8770:8770"
    environment:
      - CYRUS_HEADLESS=1
    extra_hosts:
      - "host.docker.internal:host-gateway"  # Linux compat
```

---

## Phase 5: Make `cyrus_hook.py` Host-Configurable

**File:** `cyrus_hook.py`

```python
BRAIN_HOST = os.environ.get("CYRUS_BRAIN_HOST", "localhost")
```

With Docker port mapping, `localhost:8767` still works — no change needed for most users.

---

## Phase 6: Documentation

Update `docs/` with Docker quickstart instructions.

---

## Files to Modify
- `cyrus_brain.py` — headless guards, registration server, remove UIA dependency in headless
- `cyrus-companion/src/extension.ts` — registration, focus events, permission handling
- `cyrus-companion/package.json` — new config settings
- `cyrus_hook.py` — configurable BRAIN_HOST

## New Files
- `Dockerfile`
- `docker-compose.yml`
- `requirements-brain-headless.txt`

## Verification
1. Run `docker compose up` — brain starts without Windows dependency errors
2. Open VS Code with companion extension — check it registers with brain (log output)
3. Run voice service on host connecting to `localhost:8766` — speak a command
4. Verify utterance routes through brain to companion → Claude Code
5. Verify Claude response arrives via hook → brain → voice TTS
6. Test permission flow: trigger a tool needing approval, say "yes", confirm it resolves
7. Test multi-session: open two VS Code windows, verify both register and focus switching works
8. Test on macOS and Linux with Docker Desktop / native Docker

---

*Implementation note: Save this as `docs/13-docker-containerization.md` in the project.*
