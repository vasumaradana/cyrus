# Issue 036: Add Health Check Endpoint

## Sprint
Sprint 6 — Polish

## Priority
High

## References
- docs/15-recommendations.md — #6 (Health check endpoint)

## Description
Implement a simple HTTP `/health` endpoint on the brain that returns JSON status. Enables Docker health checks, Kubernetes liveness probes, and monitoring tools to verify the brain is alive and operational. Returns 200 with status details including port status, registered sessions, active project.

## Blocked By
- None

## Acceptance Criteria
- [ ] HTTP server on port 8766 (same as TCP brain port) or separate port
- [ ] `GET /health` endpoint returns 200 with JSON
- [ ] Response includes: `{"status": "ok", "sessions": 2, "active_project": "..."}` or similar
- [ ] Callable from `docker ps` health check
- [ ] Callable from monitoring tools (Prometheus, etc.)
- [ ] Never crashes/blocks brain main loop

## Implementation Steps
1. Add http.server listener in `cyrus2/cyrus_brain.py`:
   ```python
   import http.server
   import socketserver
   import json

   class HealthHandler(http.server.BaseHTTPRequestHandler):
       def do_GET(self):
           if self.path == '/health':
               status = {
                   "status": "ok",
                   "timestamp": time.time(),
                   "sessions": len(_registered_sessions),
                   "active_project": _active_project,
                   "headless": HEADLESS
               }
               self.send_response(200)
               self.send_header('Content-type', 'application/json')
               self.end_headers()
               self.wfile.write(json.dumps(status).encode())
           else:
               self.send_response(404)
               self.end_headers()

       def log_message(self, format, *args):
           pass  # Suppress logs

   def _run_health_server():
       handler = HealthHandler
       httpd = socketserver.TCPServer(("0.0.0.0", 8766), handler)
       httpd.serve_forever()
   ```
2. Start in separate thread in `main()`:
   ```python
   health_thread = threading.Thread(target=_run_health_server, daemon=True)
   health_thread.start()
   ```
3. OR use a more lightweight async approach with `aiohttp`:
   ```python
   async def _run_health_server():
       from aiohttp import web

       async def health_handler(request):
           return web.json_response({
               "status": "ok",
               "timestamp": time.time(),
               "sessions": len(_registered_sessions),
               "active_project": _active_project,
               "headless": HEADLESS
           })

       app = web.Application()
       app.router.add_get('/health', health_handler)
       runner = web.AppRunner(app)
       await runner.setup()
       site = web.TCPSite(runner, "0.0.0.0", 8766)
       await site.start()
       await asyncio.sleep(float('inf'))
   ```
4. Update Dockerfile health check (from Issue 035):
   ```dockerfile
   HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
       CMD curl -f http://localhost:8766/health || exit 1
   ```

## Files to Create/Modify
- Modify: `cyrus2/cyrus_brain.py` (add health endpoint)
- Modify: `cyrus2/Dockerfile` (add HEALTHCHECK if using issue 035)

## Testing
1. Start brain: `CYRUS_HEADLESS=1 python cyrus2/cyrus_brain.py`
2. Curl health endpoint: `curl http://localhost:8766/health`
3. Verify 200 response with JSON: `{"status":"ok",...}`
4. Verify sessions count increases when extension registers
5. Verify active_project reflects focus events
6. Run health check while brain is under load — verify <100ms response
7. Stop brain — verify health endpoint returns error
