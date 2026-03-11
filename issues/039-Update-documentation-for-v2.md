# Issue 039: Update Documentation for v2

## Sprint
Sprint 6 — Polish

## Priority
High

## References
- docs/README.md (all sections)
- docs/13-docker-containerization.md
- docs/15-recommendations.md

## Description
Update all documentation to reflect Cyrus 2.0 rewrite with new cyrus2/ directory structure, centralized config module, Docker containerization, and companion extension. Update README Quick Start section with setup instructions for both traditional and Docker modes. Document new features: auth tokens, health checks, configurable Whisper models, session persistence.

## Blocked By
- All Sprint 4-6 issues (features must be complete)

## Acceptance Criteria
- [ ] docs/README.md updated with new v2 structure
- [ ] Quick Start section includes standalone brain + voice modes
- [ ] Docker Quick Start section added (compose up, port mappings)
- [ ] Configuration section documents all env vars (from Issue 027)
- [ ] Authentication section explains TOKEN setup (from Issue 028)
- [ ] Extension setup guide included (Issues 031-033)
- [ ] Health check endpoint documented
- [ ] Session persistence explained
- [ ] Migration guide from v1 to v2
- [ ] All file paths updated to cyrus2/ directory

## Implementation Steps
1. Create new README sections:
   - Architecture Overview (monolithic → split brain + voice)
   - Cyrus 2.0 Structure (cyrus2/ directory layout)
   - Quick Start — Traditional Mode (run brain + voice on same machine)
   - Quick Start — Docker Mode (docker compose up)
   - Configuration (env vars reference from cyrus_config.py)
   - Authentication (CYRUS_AUTH_TOKEN setup)
   - VS Code Companion Extension Setup
   - Health Checks and Monitoring
   - Troubleshooting

2. Example Quick Start — Traditional:
   ```markdown
   ## Quick Start (Traditional)

   1. **Install dependencies**
      ```bash
      pip install -r requirements-brain.txt
      pip install -r requirements-voice.txt
      ```

   2. **Configure authentication**
      ```bash
      cp .env.example .env
      # Edit .env with your CYRUS_AUTH_TOKEN and other settings
      ```

   3. **Start brain (in Terminal 1)**
      ```bash
      python cyrus2/cyrus_brain.py
      ```

   4. **Start voice service (in Terminal 2)**
      ```bash
      python cyrus2/cyrus_voice.py
      ```

   5. **Install companion extension in VS Code**
      - Open cyrus-companion directory
      - Run `npm install && npm run compile`
      - Press F5 to start extension debug session

   6. **Configure Claude Code hook**
      - Edit ~/.claude/settings.json to add hook (see docs/README.md)
   ```

3. Example Quick Start — Docker:
   ```markdown
   ## Quick Start (Docker)

   1. **Prepare configuration**
      ```bash
      cd cyrus2
      cp ../.env.example .env
      # Edit .env with tokens
      ```

   2. **Start containers**
      ```bash
      docker compose up
      ```

   3. **Connect hook from host**
      - Set CYRUS_BRAIN_HOST=host.docker.internal
      - Configure Claude Code hook to use cyrus_hook.py

   4. **Install companion extension**
      - Same as traditional mode
      - Set cyrusCompanion.brainHost to host machine IP (if needed)
   ```

4. Configuration reference:
   ```markdown
   ## Environment Variables

   | Variable | Default | Description |
   |----------|---------|-------------|
   | CYRUS_BRAIN_PORT | 8766 | Brain control port |
   | CYRUS_HOOK_PORT | 8767 | Claude Code hook port |
   | CYRUS_MOBILE_PORT | 8769 | Mobile client port |
   | CYRUS_COMPANION_PORT | 8770 | Companion extension port |
   | CYRUS_AUTH_TOKEN | (required) | Shared secret for all ports |
   | CYRUS_BRAIN_HOST | localhost | For hook connections to remote brain |
   | CYRUS_HEADLESS | 0 | Set to 1 for Docker/headless mode |
   | CYRUS_WHISPER_MODEL | medium.en | Whisper model size |
   | CYRUS_STATE_FILE | ~/.cyrus/state.json | Session persistence file |
   | CYRUS_TTS_TIMEOUT | 25.0 | Text-to-speech timeout (seconds) |
   ```

5. Add troubleshooting section:
   ```markdown
   ## Troubleshooting

   **Brain won't start in Docker**
   - Verify CYRUS_HEADLESS=1
   - Check logs: `docker logs cyrus-brain`
   - Ensure auth token is set

   **Extension won't register**
   - Check extension output channel (Ctrl+Shift+U)
   - Verify brainHost/brainPort settings
   - Check brain registration listener: `curl http://localhost:8770`

   **Hook connection refused**
   - Verify CYRUS_AUTH_TOKEN matches brain setting
   - Check CYRUS_BRAIN_HOST points to correct machine
   - For Docker: use host.docker.internal on Linux/macOS
   ```

## Files to Create/Modify
- Modify: `docs/README.md` (sections: overview, quickstart, config, auth, extension, troubleshooting)
- Create: `docs/14-migration-guide.md` (optional: v1 to v2 upgrade path)

## Testing
1. Follow traditional Quick Start — verify all steps work
2. Follow Docker Quick Start — verify all steps work
3. Follow extension setup — verify registration
4. Verify all links in README are correct
5. Verify all file paths reference cyrus2/
6. Check configuration table against cyrus_config.py
7. Verify troubleshooting covers common issues
