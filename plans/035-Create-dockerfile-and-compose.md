# Plan: 035-Create-dockerfile-and-compose

## Summary

Create `Dockerfile`, `docker-compose.yml`, and `requirements-brain-headless.txt` for containerizing the Cyrus brain in headless mode. The image uses `python:3.12-slim` with only cross-platform dependencies (python-dotenv, websockets), exposes all communication ports (8766, 8767, 8769, 8770), sets `CYRUS_HEADLESS=1`, and includes a Docker health check targeting the `/health` endpoint from Issue 036. Also creates `.dockerignore` for clean, secure builds.

## File Path Correction

The issue specifies `cyrus2/` for all file paths, but `cyrus2/` is an empty staging directory. All Python source files (`cyrus_brain.py`, `cyrus_hook.py`, `cyrus_server.py`) live at the project root. The master spec (`docs/13-docker-containerization.md`) places Docker files at the root with `build: .` context. **All files are created at the project root**, not in `cyrus2/`.

## Gap Analysis

| Requirement | Current State | Action |
|-------------|--------------|--------|
| Dockerfile | Does not exist | Create at root |
| docker-compose.yml | Does not exist | Create at root |
| requirements-brain-headless.txt | Does not exist; `requirements-brain.txt` has 7 packages (5 Windows-only) | Create with 2 cross-platform packages |
| .dockerignore | Does not exist | Create at root |
| ENV CYRUS_HEADLESS=1 | HEADLESS mode planned by Issue 030 (currently PLANNED, not built) | Set in Dockerfile; depends on 030 completing first |
| Health check endpoint | Planned by Issue 036 (currently GROOMED, no plan yet) | HEALTHCHECK in Dockerfile references `/health`; depends on 036 |
| .env.example | Exists with only `ANTHROPIC_API_KEY=` | Not in scope — other issues should extend it |

## Key Design Decisions

### D1: File placement — root, not cyrus2/

The issue says `cyrus2/` but:
- `cyrus2/` is empty — no Python files exist there
- Plan 030 explicitly corrected this: "The issue references `cyrus2/cyrus_brain.py` but the actual file is at the project root"
- `docs/13-docker-containerization.md` (master spec) puts Dockerfile at root with `build: .`
- Docker `COPY` needs the Python files in the build context

**Decision**: create all files at project root. The build context is `.` (root).

### D2: Health check port — 8766 initially, will become 8771

The issue spec's HEALTHCHECK uses `localhost:8766/health`. However, Issue 036's interview Q&A reveals a definitive owner decision:

> **Q:** Port 8766 is already in use by the voice TCP server. Should the health endpoint use a different port (e.g., 8771)?
> **A:** 8771

Port 8766 is the voice TCP server — it cannot also serve HTTP. Issue 036 will put the health endpoint on **port 8771** using **aiohttp** (async, new dependency).

**Decision**: use port 8766 in the HEALTHCHECK per this issue's AC (which specifies `localhost:8766/health`). When Issue 036 is built, the builder for 036 must:
1. Update the HEALTHCHECK port from 8766 → 8771
2. Add `EXPOSE 8771` to the Dockerfile
3. Add port mapping `"8771:8771"` to compose
4. Add `aiohttp` to `requirements-brain-headless.txt`

This avoids scope creep in 035 while documenting the known future change.

### D3: Health check command — Python, not curl

`python:3.12-slim` does not include `curl`. Options:
- (a) `apt-get install curl` — adds ~10MB to image, extra apt layer
- (b) `python -c "import urllib.request; urllib.request.urlopen(...)"` — zero extra deps

**Decision**: use Python urllib for the health check. Keeps the image minimal with no additional apt packages.

### D4: Omit deprecated `version` key in docker-compose.yml

The issue spec includes `version: '3.9'`. This key is deprecated in Docker Compose v2+ and produces a warning. The master spec (`docs/13`) already omits it.

**Decision**: omit `version` key. Follow Compose v2 standard.

### D5: Create .dockerignore

Not in the acceptance criteria, but essential for:
- Preventing `.env` secrets from being baked into the image
- Excluding `.git/`, `docs/`, `tests/`, `.barf/`, `.claude/`, voice dependencies, model files
- Reducing build context size

**Decision**: create `.dockerignore` as a bonus deliverable. No AC depends on it, but it's best practice.

### D6: COPY file list — match what exists

The issue spec copies `cyrus_brain.py cyrus_hook.py cyrus_config.py cyrus_server.py`. However:
- `cyrus_config.py` does not exist (may be created by Issue 027)
- The master spec copies `cyrus_brain.py cyrus_hook.py cyrus_server.py .env*`

**Decision**: COPY `cyrus_brain.py`, `cyrus_hook.py`, `cyrus_server.py`, and `.env*`. If `cyrus_config.py` exists at build time (created by Issue 027), add it to the COPY line.

### D7: requirements-brain-headless.txt — pin versions per issue spec

The issue spec pins `python-dotenv==1.0.0` and `websockets==12.0`. These are the only two cross-platform packages from `requirements-brain.txt` (the other 5 are Windows-only GUI automation libraries).

**Decision**: pin `python-dotenv==1.0.0` and `websockets==12.0` per the issue spec. Issue 036 will add `aiohttp` when it's built (see D2).

### D8: .env security — exclude secrets from image, keep .env.example

The Dockerfile does `COPY .env* ./` which would copy both `.env` (secrets) and `.env.example` (template) into the image. Secrets baked into images are a security risk — anyone with `docker pull` access gets the keys.

**Decision**: `.dockerignore` excludes `.env` so secrets are never baked into the image. `.env.example` is NOT excluded so the template is available in the image for reference. At runtime, compose mounts `.env` as a read-only volume (`- ./.env:/app/.env:ro`), which is the correct pattern for secrets.

## Acceptance Criteria → Verification Map

| Criterion | Verification |
|-----------|-------------|
| `Dockerfile` created with python:3.12-slim base | File exists; `FROM python:3.12-slim` is first instruction |
| `docker-compose.yml` includes brain service | File exists; `services.brain` key present |
| `requirements-brain-headless.txt` pins dependencies | File exists; contains pinned python-dotenv, websockets |
| ENV CYRUS_HEADLESS=1 in Dockerfile | `ENV CYRUS_HEADLESS=1` line present |
| All ports exposed: 8766, 8767, 8769, 8770 | `EXPOSE` line lists all four ports; compose maps all four |
| .env.example copied/mounted | `COPY .env* ./` in Dockerfile copies .env.example; compose `volumes` mounts `.env:/app/.env:ro` |
| WORKDIR set to /app | `WORKDIR /app` line present |
| CMD runs `python cyrus_brain.py` | `CMD ["python", "cyrus_brain.py"]` present |
| Compose includes health check | `healthcheck` block in compose service |
| Compose has extra_hosts for Linux Docker | `extra_hosts` with `host.docker.internal:host-gateway` |

## Implementation Steps

### Step 1: Create `requirements-brain-headless.txt`

**File:** `requirements-brain-headless.txt` (project root)

```
python-dotenv==1.0.0
websockets==12.0
```

**Note for builder**: When Issue 036 is built, `aiohttp` must be added to this file (036's interview confirmed aiohttp for the health endpoint).

**Verify:** file exists with 2 pinned dependencies.

────

### Step 2: Create `Dockerfile`

**File:** `Dockerfile` (project root)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install headless brain dependencies only
COPY requirements-brain-headless.txt .
RUN pip install --no-cache-dir -r requirements-brain-headless.txt

# Copy brain source files
# NOTE: If cyrus_config.py exists (from Issue 027), add it to this line
COPY cyrus_brain.py cyrus_hook.py cyrus_server.py ./
COPY .env* ./

# Run in headless mode — all Windows GUI paths disabled
ENV CYRUS_HEADLESS=1
ENV PYTHONUNBUFFERED=1

# Ports: brain(8766), hook(8767), mobile(8769), companion(8770)
EXPOSE 8766 8767 8769 8770

# Health check via Python urllib (curl not available in slim image)
# Targets /health endpoint from Issue 036 on brain port
# NOTE: Issue 036 interview confirmed health endpoint will be on port 8771.
# When 036 is built, update this to port 8771 and add EXPOSE 8771 above.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8766/health')"

CMD ["python", "cyrus_brain.py"]
```

**Design notes:**
- Two separate `COPY` instructions: source files first, `.env*` second — matches the issue spec's intent to copy env files
- `.dockerignore` excludes `.env` (secrets) so only `.env.example` is copied by `COPY .env* ./` (see D8)
- `PYTHONUNBUFFERED=1` ensures log output appears immediately (critical for `docker logs`)
- Health check uses Python stdlib urllib instead of curl (D3)
- Health check targets port 8766 per issue spec (D2); 036 will change this to 8771
- Python's urllib raises on non-200 → Docker sees non-zero exit → marks unhealthy

**Verify:** `docker build -t cyrus-brain:latest .` succeeds (requires Issues 030/036 for runtime, but the image builds regardless since it only pip-installs python-dotenv and websockets).

────

### Step 3: Create `docker-compose.yml`

**File:** `docker-compose.yml` (project root)

```yaml
# Quick start:
# 1. cp .env.example .env && edit for your tokens
# 2. docker compose up
# 3. Hook and voice clients connect to localhost:8767 / localhost:8766
# 4. Extension connects to localhost:8770

services:
  brain:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: cyrus-brain
    ports:
      - "8766:8766"   # Brain control (voice TCP)
      - "8767:8767"   # Hook events (Claude Code)
      - "8769:8769"   # Mobile client
      - "8770:8770"   # Extension registration
    environment:
      CYRUS_HEADLESS: "1"
      CYRUS_AUTH_TOKEN: ${CYRUS_AUTH_TOKEN:-change-me}
      CYRUS_BRAIN_HOST: "0.0.0.0"
    volumes:
      - ./.env:/app/.env:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8766/health')"]
      interval: 30s
      timeout: 10s
      start_period: 5s
      retries: 3
    restart: unless-stopped
```

**Design notes:**
- No `version` key (D4) — Compose v2 standard
- Quick-start comments at top per issue spec
- Health check in compose uses exec form `["CMD", ...]` — cleaner than shell form for compose
- `CYRUS_BRAIN_HOST: "0.0.0.0"` — binds to all interfaces inside container so ports are reachable from host
- `extra_hosts` — enables `host.docker.internal` DNS on Linux (native on Docker Desktop)
- `restart: unless-stopped` — container recovers from crashes
- When Issue 036 is built, add `"8771:8771"` port mapping and update healthcheck port

**Verify:** `docker compose config` validates the YAML without errors.

────

### Step 4: Create `.dockerignore`

**File:** `.dockerignore` (project root)

```
# Version control
.git/
.gitignore

# Barf orchestration
.barf/
.claude/
issues/
plans/
docs/

# Secrets — never bake into image (mounted at runtime via compose volume)
.env

# Voice service (not needed in headless brain)
cyrus_voice.py
requirements-voice.txt
requirements.txt
requirements-brain.txt

# Legacy
main.py

# Companion extension (runs on host, not in container)
cyrus-companion/

# Test / utility files
probe_uia.py
test_permission_scan.py
tests/

# Build scripts
*.ps1
*.bat
install-brain.sh
build-release.ps1

# Model files (large binaries)
*.onnx
*.bin

# Python cache
__pycache__/
*.pyc
*.pyo

# Runtime
*.tmp
*.log
@AutomationLog.txt

# Local overrides
.local/
.env.local
```

**Design notes:**
- **`.env` is excluded** — secrets must never be baked into the image. At runtime, compose mounts `.env` as a read-only volume (D8)
- **`.env.example` is NOT excluded** — it's a template file that gets copied into the image by `COPY .env* ./`, useful for reference
- Excludes everything not needed for the headless brain container
- Keeps only: `Dockerfile`, `docker-compose.yml`, `requirements-brain-headless.txt`, `cyrus_brain.py`, `cyrus_hook.py`, `cyrus_server.py`, `.env.example`
- Dramatically reduces build context (excludes .git, model files, docs, companion extension, etc.)

**Verify:** `docker build` only sends relevant files to the daemon (visible in build output size).

────

### Step 5: Verify the build

Run the full verification sequence:

1. **Build image:**
   ```bash
   docker build -t cyrus-brain:latest .
   ```
   Expect: clean build, no errors. Image should be ~150-200MB (python:3.12-slim + 2 pip packages).

2. **Validate compose:**
   ```bash
   docker compose config
   ```
   Expect: valid YAML, all services rendered.

3. **Check image layers:**
   ```bash
   docker history cyrus-brain:latest
   ```
   Expect: WORKDIR, COPY, RUN pip, ENV, EXPOSE, HEALTHCHECK, CMD layers all present.

4. **Inspect exposed ports:**
   ```bash
   docker inspect cyrus-brain:latest --format='{{json .Config.ExposedPorts}}'
   ```
   Expect: 8766, 8767, 8769, 8770 all listed.

5. **Inspect environment:**
   ```bash
   docker inspect cyrus-brain:latest --format='{{json .Config.Env}}'
   ```
   Expect: `CYRUS_HEADLESS=1` and `PYTHONUNBUFFERED=1` present.

6. **Inspect health check:**
   ```bash
   docker inspect cyrus-brain:latest --format='{{json .Config.Healthcheck}}'
   ```
   Expect: interval=30s, timeout=10s, start_period=5s, retries=3, test uses urllib on port 8766.

**Note:** Runtime testing (starting the brain, connecting clients, health checks) requires Issues 030 and 036 to be complete. The builder should verify the image builds cleanly; full integration testing is deferred until dependencies are met.

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `requirements-brain-headless.txt` | Create | Pinned deps: python-dotenv==1.0.0, websockets==12.0 |
| `Dockerfile` | Create | python:3.12-slim, headless brain, all ports exposed |
| `docker-compose.yml` | Create | Brain service with ports, env, volumes, health check |
| `.dockerignore` | Create | Exclude non-essential files and secrets from build context |

## Dependency Notes

This issue is blocked by:
- **Issue 030** (HEADLESS mode, currently PLANNED) — `CYRUS_HEADLESS=1` must be implemented in `cyrus_brain.py` for the container to start without Windows import errors
- **Issue 034** (registration listener, currently PLANNED) — port 8770 server must exist for companion extension connections
- **Issue 036** (health endpoint, currently GROOMED) — `/health` endpoint must exist for HEALTHCHECK to pass; interview confirmed port 8771 + aiohttp

The Docker files can be **created and the image built** before these issues are complete (pip install succeeds, files copy fine). But the container will fail at **runtime** if Issues 030/036 aren't done. The builder should:
1. Create the files per this plan
2. Verify the image builds
3. If dependencies are met, run the container and test; if not, note it in the issue

## Deltas from Issue Spec

| Issue spec says | Plan changes to | Rationale |
|----------------|----------------|-----------|
| Files in `cyrus2/` | Files at project root | cyrus2/ is empty; all source files are at root; master spec uses root |
| `version: '3.9'` in compose | Omitted | Deprecated in Compose v2+; produces warning |
| `curl -f http://localhost:8766/health` | `python -c "import urllib.request; ..."` on port 8766 | curl not in slim image; Python urllib is zero-cost alternative |
| COPY includes `cyrus_config.py` | Omit (doesn't exist yet) | May be added by Issue 027 later |
| No .dockerignore | Create .dockerignore | Best practice; excludes secrets and reduces build context |
| `.env` baked into image | `.env` excluded via .dockerignore | Secrets must never be in images; compose mounts at runtime |

## Known Follow-Up Changes (Issue 036)

When Issue 036 is built, the following changes to 035's files are required:
1. `requirements-brain-headless.txt` — add `aiohttp` (pinned version TBD by 036)
2. `Dockerfile` — add `EXPOSE 8771`; update HEALTHCHECK port from 8766 → 8771
3. `docker-compose.yml` — add port mapping `"8771:8771"`; update healthcheck port from 8766 → 8771
