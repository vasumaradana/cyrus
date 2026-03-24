# Implementation Plan: Create Dockerfile and Docker Compose

**Issue**: [035-Create-dockerfile-and-compose](/home/daniel/Projects/barf/cyrus/cyrus/issues/035-Create-dockerfile-and-compose.md)
**Created**: 2026-03-18
**PROMPT**: `/home/daniel/Projects/barf/cyrus/prompts/PROMPT_plan.md`

## Gap Analysis

**Already exists**:
- `CYRUS_HEADLESS` flag fully integrated in `cyrus_config.py` (line 93) and `cyrus_brain.py` — guards Windows imports, enables headless mode
- `cyrus_brain.py` with `main()` entry point (CMD target)
- `cyrus_hook.py`, `cyrus_config.py`, `cyrus_server.py`, `cyrus_common.py`, `cyrus_log.py` — all source files referenced in Dockerfile COPY
- `.env.example` in `cyrus2/` — documents all CYRUS_* env vars including ports and auth token
- `requirements-brain.txt` with full deps (including Windows-only packages) — pins `python-dotenv==1.2.2` and `websockets==16.0`
- Four existing requirements files following naming convention: `requirements.txt`, `requirements-brain.txt`, `requirements-voice.txt`, `requirements-dev.txt`
- Ports already defined in `cyrus_config.py`: BRAIN_PORT=8766, HOOK_PORT=8767, MOBILE_PORT=8769, COMPANION_PORT=8770
- `docs/13-docker-containerization.md` — comprehensive Docker strategy document (Phase 4 = Docker Files)

**Needs building**:
1. `cyrus2/Dockerfile` — python:3.12-slim image for headless brain
2. `cyrus2/docker-compose.yml` — orchestration with ports, env, health check, extra_hosts
3. `cyrus2/requirements-brain-headless.txt` — minimal deps (python-dotenv, websockets only)

## Approach

**Strategy: Create three new files with no source code changes.** This is Phase 4 of the Docker containerization plan. All prerequisite code changes (headless mode, companion extension, registration listener) are already implemented per issues 030/034. The three files are straightforward infrastructure artifacts.

**Key design decisions**:
- **Pin to actual codebase versions** — The issue specifies `python-dotenv==1.0.0` and `websockets==12.0`, but the codebase actually uses `python-dotenv==1.2.2` and `websockets==16.0`. Use the actual versions to avoid compatibility issues.
- **HEALTHCHECK approach** — The issue shows `curl` in HEALTHCHECK, but `python:3.12-slim` doesn't include curl. Two options: (a) install curl in the image, or (b) use a Python one-liner. Option (a) is simpler and more conventional for Docker health checks. Since Issue 036 (health endpoint) is a blocker and should be implemented by the time this runs, we'll install curl and use the health check as specified. The health endpoint port needs to match Issue 036's implementation (8771 per its design, but the issue spec says 8766 — use 8766 as specified in this issue and adjust if needed when 036 is integrated).
- **Copy all needed Python files** — The Dockerfile COPY should include all files the brain imports: `cyrus_brain.py`, `cyrus_hook.py`, `cyrus_config.py`, `cyrus_server.py`, `cyrus_common.py`, `cyrus_log.py`, `main.py`. The issue only lists 4 files but imports indicate more are needed.
- **No .dockerignore needed yet** — The COPY is explicit file-by-file, not a directory copy
- **Compose version key** — `version: '3.9'` is deprecated in modern Docker Compose but included for broad compatibility as specified in the issue

## Rules to Follow

- `.claude/rules/` — currently empty, no custom rules
- Follow existing requirements file naming convention (`requirements-*.txt`)
- Pin exact versions matching the codebase
- Include quick-start documentation comments in docker-compose.yml
- Follow the implementation specified in `docs/13-docker-containerization.md` Phase 4

## Skills & Agents to Use

| Task | Skill/Agent | Purpose |
|------|-------------|---------|
| Create Dockerfile | `docker-expert` agent | Docker best practices, layer optimization |
| Create docker-compose.yml | `devops-engineer` agent | Compose configuration, health checks |
| Validate requirements | `python-expert` skill | Ensure minimal deps are correct and sufficient |
| Code quality check | `python-linting` skill | Lint any Python if modified |

## Prioritized Tasks

- [ ] **1. Create `cyrus2/requirements-brain-headless.txt`** — Pin `python-dotenv==1.2.2` and `websockets==16.0` (matching actual codebase versions). These are the only two packages needed for headless brain operation.
- [ ] **2. Create `cyrus2/Dockerfile`** — Based on `python:3.12-slim`:
  - WORKDIR /app
  - COPY and install requirements-brain-headless.txt
  - Install curl for health check (`apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*`)
  - COPY all needed Python source files: `cyrus_brain.py`, `cyrus_hook.py`, `cyrus_config.py`, `cyrus_server.py`, `cyrus_common.py`, `cyrus_log.py`, `main.py`
  - COPY `.env*` for defaults
  - ENV CYRUS_HEADLESS=1, PYTHONUNBUFFERED=1
  - EXPOSE 8766 8767 8769 8770
  - HEALTHCHECK using curl on localhost:8766/health
  - CMD `["python", "cyrus_brain.py"]`
- [ ] **3. Create `cyrus2/docker-compose.yml`** — Brain service with:
  - Build context and Dockerfile reference
  - Container name: cyrus-brain
  - Port mappings: 8766-8770 (4 ports)
  - Environment: CYRUS_HEADLESS=1, CYRUS_AUTH_TOKEN, CYRUS_BRAIN_HOST=0.0.0.0
  - Volume mount: .env read-only
  - extra_hosts for Linux Docker compatibility
  - Health check configuration
  - restart: unless-stopped
  - Quick-start documentation comments
- [ ] **4. Verify Dockerfile builds** — `cd cyrus2 && docker build -t cyrus-brain:latest .`
- [ ] **5. Verify compose starts** — `cd cyrus2 && docker compose up -d && docker compose ps`

## Acceptance-Driven Tests

| Acceptance Criterion | Required Test | Type |
|---------------------|---------------|------|
| `cyrus2/Dockerfile` created with python:3.12-slim base | Verify file exists and contains `FROM python:3.12-slim` | manual/build |
| `cyrus2/docker-compose.yml` includes brain service | Verify file exists and contains `services: brain:` | manual |
| `cyrus2/requirements-brain-headless.txt` pins dependencies | Verify file contains python-dotenv and websockets with pinned versions | manual |
| ENV CYRUS_HEADLESS=1 in Dockerfile | Verify Dockerfile contains `ENV CYRUS_HEADLESS=1` | manual |
| All ports exposed: 8766, 8767, 8769, 8770 | Verify `EXPOSE 8766 8767 8769 8770` in Dockerfile and port mappings in compose | manual |
| .env.example copied/mounted | Verify COPY .env* in Dockerfile and volume mount in compose | manual |
| WORKDIR set to /app | Verify `WORKDIR /app` in Dockerfile | manual |
| CMD runs `python cyrus_brain.py` | Verify `CMD ["python", "cyrus_brain.py"]` | manual |
| Compose includes health check | Verify healthcheck section in docker-compose.yml | manual |
| Compose has extra_hosts for Linux Docker | Verify `extra_hosts: - "host.docker.internal:host-gateway"` | manual |
| Docker build succeeds | `docker build -t cyrus-brain:latest .` exits 0 | build |
| Docker compose up works | `docker compose up` starts container | integration |

**No cheating** — cannot claim done without Docker build succeeding.

## Validation (Backpressure)

- **Build**: `cd cyrus2 && docker build -t cyrus-brain:latest .` must succeed
- **Compose**: `cd cyrus2 && docker compose config` must validate without errors
- **Lint**: No Python files modified, so no lint needed
- **Existing tests**: No source changes, so `pytest cyrus2/tests/` should remain unaffected

## Files to Create/Modify

- **Create**: `cyrus2/requirements-brain-headless.txt` — minimal headless dependencies (python-dotenv, websockets)
- **Create**: `cyrus2/Dockerfile` — python:3.12-slim container for headless brain
- **Create**: `cyrus2/docker-compose.yml` — orchestration with brain service, ports, health check, extra_hosts

## Risks & Open Questions

- **Health endpoint not yet implemented (Issue 036 is a blocker)**: The HEALTHCHECK in the Dockerfile calls `curl http://localhost:8766/health` but Issue 036 (which adds `/health`) may not be merged yet. The Dockerfile will build fine, but the health check will fail until 036 is implemented. This is acceptable — the container will start and run, just report unhealthy until the endpoint exists.
- **Health endpoint port mismatch**: Issue 036's design says port 8771, but this issue's spec says port 8766. Follow this issue's spec (8766) and reconcile when 036 is integrated.
- **Python-dotenv may not be needed**: The codebase uses `os.environ.get()` directly in `cyrus_config.py` — no `dotenv.load_dotenv()` calls found. However, it's in the existing `requirements-brain.txt` and specified by the issue, so include it for consistency and potential .env file loading.
- **Missing source files in COPY**: The issue's Dockerfile only copies 4 .py files (`cyrus_brain.py`, `cyrus_hook.py`, `cyrus_config.py`, `cyrus_server.py`), but `cyrus_brain.py` imports `cyrus_common.py` and `cyrus_log.py`. Must include all imported modules in the COPY instruction or the container will fail to start.
