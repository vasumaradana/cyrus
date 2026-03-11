# Issue 035: Create Dockerfile and Docker Compose

## Sprint
Sprint 5 — Docker & Extension

## Priority
Critical

## References
- docs/13-docker-containerization.md — Phase 4 (Docker Files)

## Description
Create a `Dockerfile` for containerizing the Cyrus brain, a `docker-compose.yml` for orchestration, and `requirements-brain-headless.txt` for minimal dependencies. Image uses `python:3.12-slim` base with only essential packages (python-dotenv, websockets). Exposes all communication ports (8766, 8767, 8769, 8770). Health check endpoint (from Issue 036) included.

## Blocked By
- Issue 030 (HEADLESS mode)
- Issue 034 (registration listener)
- Issue 036 (health endpoint)

## Acceptance Criteria
- [ ] `cyrus2/Dockerfile` created with python:3.12-slim base
- [ ] `cyrus2/docker-compose.yml` includes brain service
- [ ] `cyrus2/requirements-brain-headless.txt` pins dependencies
- [ ] ENV CYRUS_HEADLESS=1 in Dockerfile
- [ ] All ports exposed: 8766, 8767, 8769, 8770
- [ ] .env.example copied/mounted
- [ ] WORKDIR set to /app
- [ ] CMD runs `python cyrus_brain.py`
- [ ] Compose includes health check
- [ ] Compose has extra_hosts for Linux Docker

## Implementation Steps
1. Create `cyrus2/Dockerfile`:
   ```dockerfile
   FROM python:3.12-slim

   WORKDIR /app

   # Copy requirements and install
   COPY requirements-brain-headless.txt .
   RUN pip install --no-cache-dir -r requirements-brain-headless.txt

   # Copy code
   COPY cyrus_brain.py cyrus_hook.py cyrus_config.py cyrus_server.py ./
   COPY .env* ./

   # Headless mode
   ENV CYRUS_HEADLESS=1
   ENV PYTHONUNBUFFERED=1

   # Ports: brain(8766), hook(8767), mobile(8769), companion(8770)
   EXPOSE 8766 8767 8769 8770

   # Health check
   HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
       CMD curl -f http://localhost:8766/health || exit 1

   CMD ["python", "cyrus_brain.py"]
   ```
2. Create `cyrus2/requirements-brain-headless.txt`:
   ```
   python-dotenv==1.0.0
   websockets==12.0
   ```
3. Create `cyrus2/docker-compose.yml`:
   ```yaml
   version: '3.9'

   services:
     brain:
       build:
         context: .
         dockerfile: Dockerfile
       container_name: cyrus-brain
       ports:
         - "8766:8766"   # Brain control
         - "8767:8767"   # Hook events
         - "8769:8769"   # Mobile client
         - "8770:8770"   # Extension registration
       environment:
         CYRUS_HEADLESS: "1"
         CYRUS_AUTH_TOKEN: ${CYRUS_AUTH_TOKEN:-change-me}
         CYRUS_BRAIN_HOST: "0.0.0.0"
       volumes:
         - ./.env:/app/.env:ro  # Read-only config
       extra_hosts:
         - "host.docker.internal:host-gateway"  # Linux Docker compat
       restart: unless-stopped
   ```
4. Document in comments:
   ```
   # Quick start:
   # 1. cp .env.example .env && edit for your tokens
   # 2. docker compose up
   # 3. Hook and voice clients connect to localhost:8767 / localhost:8766
   # 4. Extension connects to localhost:8770
   ```

## Files to Create/Modify
- Create: `cyrus2/Dockerfile`
- Create: `cyrus2/docker-compose.yml`
- Create: `cyrus2/requirements-brain-headless.txt`

## Testing
1. Build image: `cd cyrus2 && docker build -t cyrus-brain:latest .`
2. Verify build succeeds without Windows import errors
3. Run container: `docker run -it cyrus-brain:latest`
4. Verify brain starts and logs "HEADLESS mode"
5. Verify ports 8766-8770 are exposed
6. Run compose: `docker compose up`
7. Verify brain container starts
8. Test health endpoint: `curl http://localhost:8766/health`
9. Test hook connection: `echo '{"event":"stop","text":"test"}' | nc localhost 8767`
10. Test from host machine: `telnet localhost 8766` (should accept connection)
