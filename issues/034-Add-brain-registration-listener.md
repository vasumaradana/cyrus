# Issue 034: Add Brain Registration Listener

## Sprint
Sprint 5 — Docker & Extension

## Priority
Critical

## References
- docs/13-docker-containerization.md — Phase 3 (Brain-side Registration Listener)

## Description
Implement an async TCP server on port 8770 in `cyrus2/cyrus_brain.py` to accept and manage companion extension registrations. Maintain a `_registered_sessions` dict tracking active workspaces. Route `focus`/`blur` messages to update `_active_project`. Route `permission_respond` and `prompt_respond` messages back to the caller. Handle client disconnects gracefully.

## Blocked By
- Issue 030 (headless mode must exist to handle session discovery via registrations)

## Acceptance Criteria
- [ ] Async TCP server on 0.0.0.0:8770 in cyrus2/cyrus_brain.py (headless mode only)
- [ ] `_registered_sessions: dict[str, SessionInfo]` tracks workspace name, connection, listen port
- [ ] On `register` message, add session and create ChatWatcher (hooks-only) + PermissionWatcher (hooks-only)
- [ ] On `focus` message, set `_active_project` to workspace name
- [ ] On `blur` message, clear `_active_project` if it matches
- [ ] On `permission_respond`, forward to PermissionWatcher for action
- [ ] On `prompt_respond`, forward to waiting code (if any)
- [ ] On disconnect, remove session gracefully
- [ ] Handles multiple concurrent sessions
- [ ] Logs registration, focus changes, disconnects to output

## Implementation Steps
1. Add `_registered_sessions` dict at module level in `cyrus2/cyrus_brain.py`:
   ```python
   _registered_sessions: dict[str, dict] = {}
   _sessions_lock = threading.Lock()

   class SessionInfo:
       def __init__(self, workspace: str, safe: str, port: int, connection):
           self.workspace = workspace
           self.safe = safe
           self.port = port
           self.connection = connection
           self.created_at = time.time()
   ```
2. Create registration server handler:
   ```python
   async def _handle_registration_client(reader, writer):
       """Handle one companion extension connection"""
       peer = writer.get_extra_info('peername')
       addr = f"{peer[0]}:{peer[1]}"
       print(f"[REG] New connection from {addr}")

       session_workspace = None
       try:
           while True:
               # Read line-delimited JSON
               data = await reader.readline()
               if not data:
                   break

               try:
                   msg = json.loads(data.decode().strip())
               except json.JSONDecodeError:
                   continue

               msg_type = msg.get("type", "")

               if msg_type == "register":
                   workspace = msg.get("workspace", "unknown")
                   safe = msg.get("safe", "unknown")
                   port = msg.get("port", 8768)

                   with _sessions_lock:
                       _registered_sessions[workspace] = SessionInfo(
                           workspace, safe, port, writer
                       )
                   session_workspace = workspace
                   print(f"[REG] {workspace} registered (port {port})")

               elif msg_type == "focus":
                   workspace = msg.get("workspace")
                   if workspace:
                       global _active_project
                       _active_project = workspace
                       print(f"[REG] Active project: {workspace}")

               elif msg_type == "blur":
                   workspace = msg.get("workspace")
                   if workspace and _active_project == workspace:
                       _active_project = None
                       print(f"[REG] Blur: {workspace}")

               elif msg_type == "permission_respond":
                   action = msg.get("action")
                   # Wake PermissionWatcher if waiting
                   if session_workspace:
                       print(f"[REG] Permission respond: {action}")
                       # TODO: route to PermissionWatcher

               elif msg_type == "prompt_respond":
                   text = msg.get("text")
                   # Route to waiting prompt handler
                   if session_workspace:
                       print(f"[REG] Prompt respond: {text[:50]}")

       except Exception as e:
           print(f"[REG] Error: {e}")
       finally:
           if session_workspace:
               with _sessions_lock:
                   _registered_sessions.pop(session_workspace, None)
               print(f"[REG] {session_workspace} disconnected")
           writer.close()
   ```
3. Start server in `main()`:
   ```python
   async def _run_registration_server():
       if not HEADLESS:
           return  # Only in headless mode

       server = await asyncio.start_server(
           _handle_registration_client,
           "0.0.0.0",
           COMPANION_PORT  # 8770
       )
       addr = server.sockets[0].getsockname()
       print(f"[REG] Listener on {addr[0]}:{addr[1]}")
       async with server:
           await server.serve_forever()
   ```
4. In `main()`, create task:
   ```python
   if HEADLESS:
       asyncio.create_task(_run_registration_server())
   ```

## Files to Create/Modify
- Modify: `cyrus2/cyrus_brain.py` (add registration server, SessionInfo class, update main())

## Testing
1. Start brain with `CYRUS_HEADLESS=1 python cyrus2/cyrus_brain.py`
2. Verify "REG Listener on 0.0.0.0:8770" in logs
3. Start extension with mock connection to brain:8770
4. Send `{"type": "register", "workspace": "test-proj", "safe": "test_proj", "port": 8768}`
5. Verify brain logs "test-proj registered (port 8768)"
6. Send `{"type": "focus", "workspace": "test-proj"}`
7. Verify brain logs "Active project: test-proj"
8. Send `{"type": "blur", "workspace": "test-proj"}`
9. Verify brain logs "Blur: test-proj"
10. Disconnect client — verify brain logs "test-proj disconnected"
11. Multiple concurrent registrations — verify all tracked in _registered_sessions
