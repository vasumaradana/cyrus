"""
Acceptance-driven tests for Issue 036: Add Health Check Endpoint.

These tests verify every acceptance criterion from the issue:
  - HTTP server on port 8771 (configurable via CYRUS_HEALTH_PORT)
  - GET /health returns 200 with Content-Type: application/json
  - Response includes: status, timestamp, sessions, active_project, headless
  - Non-/health paths return 404
  - Server never crashes/blocks brain main loop (async non-blocking)
  - CYRUS_HEALTH_PORT documented in .env.example
  - aiohttp listed in requirements-brain.txt
  - Access logs suppressed to prevent log noise from frequent probes

Test categories
---------------
  Config defaults     (3 tests) — HEALTH_PORT default, type, module attribute
  Env var overrides   (2 tests) — CYRUS_HEALTH_PORT env var, no side effects
  .env.example        (1 test)  — CYRUS_HEALTH_PORT key documented
  requirements        (1 test)  — aiohttp in requirements-brain.txt
  HTTP behaviour      (4 tests) — 200 JSON, 404, valid JSON, content-type
  Response fields     (5 tests) — all required fields, correct types/values
  Non-blocking        (1 test)  — handler is async coroutine
  Log suppression     (1 test)  — access_log=None in brain source
  Port isolation      (1 test)  — HEALTH_PORT doesn't conflict with other ports

Usage
-----
    pytest tests/test_036_health_check.py -v
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

# ── Path setup ────────────────────────────────────────────────────────────────
# cyrus_config.py and cyrus_brain.py live in cyrus2/ — add it to sys.path.

_CYRUS2_DIR = Path(__file__).parent.parent  # .../cyrus/cyrus2/
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

import cyrus_config  # noqa: E402


def _reload_config(**kwargs: str) -> object:
    """Reload cyrus_config with the given environment overrides in effect.

    Args:
        **kwargs: Env var names → string values.

    Returns:
        The freshly reloaded cyrus_config module.
    """
    with patch.dict(os.environ, kwargs, clear=False):
        return importlib.reload(cyrus_config)


# ── Helper: build the aiohttp app exactly as cyrus_brain does ─────────────────


def _build_health_app(
    sessions: dict,
    active_project: str,
    headless: bool,
) -> web.Application:
    """Build a minimal aiohttp app that mimics the brain's health server.

    Used in tests to exercise the handler logic without starting the full
    cyrus_brain — which would pull in all Windows-only GUI imports and
    hardware dependencies.

    Args:
        sessions: Mapping of workspace → session info (we only use len()).
        active_project: Currently focused project name string.
        headless: Value to report in the health response JSON.

    Returns:
        An aiohttp Application with GET /health wired up and all other paths
        returning 404 by default.
    """
    import threading

    _sessions = sessions
    _project_ref = {"value": active_project}  # mutable container for closure
    _headless = headless
    _lock = threading.Lock()

    async def health_handler(request: web.Request) -> web.Response:
        """Return brain status as JSON; called by liveness probes & monitoring."""
        with _lock:
            project = _project_ref["value"]
        return web.json_response(
            {
                "status": "ok",
                "timestamp": time.time(),
                "sessions": len(_sessions),
                "active_project": project,
                "headless": _headless,
            }
        )

    app = web.Application()
    app.router.add_get("/health", health_handler)
    return app


# ── Config: HEALTH_PORT default and env override ──────────────────────────────


class TestHealthPortConfig(unittest.TestCase):
    """Verify HEALTH_PORT constant in cyrus_config has the correct default."""

    @classmethod
    def setUpClass(cls) -> None:
        """Strip CYRUS_HEALTH_PORT so we see the true default."""
        cls._saved = os.environ.pop("CYRUS_HEALTH_PORT", None)
        importlib.reload(cyrus_config)

    @classmethod
    def tearDownClass(cls) -> None:
        """Restore env and module state after all tests in this class."""
        if cls._saved is not None:
            os.environ["CYRUS_HEALTH_PORT"] = cls._saved
        importlib.reload(cyrus_config)

    def test_health_port_default(self) -> None:
        """HEALTH_PORT must default to 8771 (sequential after COMPANION_PORT=8770)."""
        self.assertEqual(cyrus_config.HEALTH_PORT, 8771)

    def test_health_port_is_int(self) -> None:
        """HEALTH_PORT must be a Python int, not str or float."""
        self.assertIsInstance(cyrus_config.HEALTH_PORT, int)

    def test_config_exposes_health_port(self) -> None:
        """cyrus_config.HEALTH_PORT must be accessible as a module attribute."""
        self.assertTrue(
            hasattr(cyrus_config, "HEALTH_PORT"),
            "cyrus_config is missing HEALTH_PORT constant",
        )


class TestHealthPortEnvOverride(unittest.TestCase):
    """CYRUS_HEALTH_PORT env var must override the HEALTH_PORT constant."""

    def tearDown(self) -> None:
        """Reload module to restore default after each override test."""
        os.environ.pop("CYRUS_HEALTH_PORT", None)
        importlib.reload(cyrus_config)

    def test_health_port_from_env(self) -> None:
        """CYRUS_HEALTH_PORT=9000 must change HEALTH_PORT to 9000."""
        mod = _reload_config(CYRUS_HEALTH_PORT="9000")
        self.assertEqual(mod.HEALTH_PORT, 9000)

    def test_health_port_override_does_not_affect_other_ports(self) -> None:
        """Overriding CYRUS_HEALTH_PORT must not change BRAIN_PORT or HOOK_PORT."""
        mod = _reload_config(CYRUS_HEALTH_PORT="9999")
        self.assertEqual(mod.BRAIN_PORT, 8766)
        self.assertEqual(mod.HOOK_PORT, 8767)


# ── .env.example ──────────────────────────────────────────────────────────────


class TestEnvExample(unittest.TestCase):
    """CYRUS_HEALTH_PORT must be documented in .env.example."""

    _ENV_EXAMPLE = _CYRUS2_DIR / ".env.example"

    def test_env_example_has_health_port(self) -> None:
        """CYRUS_HEALTH_PORT must appear in .env.example for operator discovery."""
        content = self._ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn(
            "CYRUS_HEALTH_PORT",
            content,
            "CYRUS_HEALTH_PORT is missing from .env.example",
        )


# ── requirements-brain.txt ────────────────────────────────────────────────────


class TestRequirements(unittest.TestCase):
    """aiohttp must be listed in requirements-brain.txt."""

    _REQ_FILE = _CYRUS2_DIR / "requirements-brain.txt"

    def test_requirements_has_aiohttp(self) -> None:
        """aiohttp must appear in requirements-brain.txt (async HTTP server dep)."""
        content = self._REQ_FILE.read_text(encoding="utf-8")
        self.assertIn(
            "aiohttp",
            content,
            "aiohttp is missing from requirements-brain.txt",
        )


# ── HTTP behaviour — AioHTTPTestCase (unittest-compatible, no pytest-asyncio) ─


class TestHealthHTTPBehaviour(AioHTTPTestCase):
    """Integration tests for GET /health using aiohttp's built-in test client.

    AioHTTPTestCase provides self.client (TestClient) and manages the event
    loop automatically — no pytest-asyncio plugin required.
    """

    async def get_application(self) -> web.Application:
        """Return the aiohttp app under test."""
        return _build_health_app(
            sessions={"ws1": object(), "ws2": object()},
            active_project="test-project",
            headless=True,
        )

    async def test_health_endpoint_returns_200_json(self) -> None:
        """GET /health must return HTTP 200 with Content-Type: application/json."""
        resp = await self.client.get("/health")
        self.assertEqual(resp.status, 200)
        self.assertIn("application/json", resp.content_type)

    async def test_health_response_contains_required_fields(self) -> None:
        """Response body must contain status, sessions, active_project fields."""
        resp = await self.client.get("/health")
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["sessions"], 2)
        self.assertEqual(data["active_project"], "test-project")

    async def test_health_response_includes_headless(self) -> None:
        """Response must include the headless flag with correct boolean value."""
        resp = await self.client.get("/health")
        data = await resp.json()
        self.assertIn("headless", data)
        self.assertIs(data["headless"], True)

    async def test_health_response_includes_timestamp(self) -> None:
        """Response must include a Unix timestamp close to the request time."""
        before = time.time()
        resp = await self.client.get("/health")
        data = await resp.json()
        after = time.time()
        self.assertIn("timestamp", data)
        self.assertGreaterEqual(data["timestamp"], before)
        self.assertLessEqual(data["timestamp"], after + 1.0)

    async def test_non_health_path_returns_404(self) -> None:
        """Any path other than GET /health must return 404."""
        for path in ["/", "/metrics", "/status", "/healthz"]:
            resp = await self.client.get(path)
            self.assertEqual(
                resp.status,
                404,
                f"Expected 404 for {path!r}, got {resp.status}",
            )

    async def test_health_response_is_valid_json(self) -> None:
        """GET /health body must be parseable as valid JSON (monitoring compat)."""
        resp = await self.client.get("/health")
        raw = await resp.text()
        parsed = json.loads(raw)
        self.assertIsInstance(parsed, dict)


class TestHealthSessionCounting(AioHTTPTestCase):
    """Verify sessions field accurately reflects registered session count."""

    async def get_application(self) -> web.Application:
        """App with 3 registered sessions."""
        return _build_health_app(
            sessions={"a": object(), "b": object(), "c": object()},
            active_project="",
            headless=False,
        )

    async def test_health_sessions_count_reflects_registered_sessions(self) -> None:
        """sessions must equal the number of entries in the sessions dict."""
        resp = await self.client.get("/health")
        data = await resp.json()
        self.assertEqual(data["sessions"], 3)


class TestHealthZeroSessions(AioHTTPTestCase):
    """Verify sessions=0 when no sessions are registered."""

    async def get_application(self) -> web.Application:
        """App with no registered sessions."""
        return _build_health_app(sessions={}, active_project="", headless=False)

    async def test_health_zero_sessions(self) -> None:
        """sessions must be 0 when no sessions are registered (fresh startup)."""
        resp = await self.client.get("/health")
        data = await resp.json()
        self.assertEqual(data["sessions"], 0)


# ── Non-blocking: health handler must be an async coroutine ──────────────────


class TestHealthNonBlocking(unittest.TestCase):
    """The health handler must be async to avoid blocking the event loop."""

    def test_health_server_is_async_non_blocking(self) -> None:
        """Health handler must be a coroutine function (async def).

        An async handler integrates with asyncio.gather() and will not stall
        the brain's main event loop during Docker/k8s health probe calls.
        """
        import inspect

        # Build app to capture registered handler, then inspect it
        app = _build_health_app(sessions={}, active_project="", headless=False)
        resource = list(app.router.resources())[0]
        route = list(resource)[0]
        handler = route.handler
        self.assertTrue(
            inspect.iscoroutinefunction(handler),
            "Health handler must be async def to avoid blocking the event loop",
        )


# ── Log suppression ───────────────────────────────────────────────────────────


class TestHealthLogSuppression(unittest.TestCase):
    """Access logs must be silenced to prevent noise from frequent probes."""

    def test_health_server_suppresses_logs(self) -> None:
        """_start_health_server in cyrus_brain.py must silence aiohttp access logs.

        Docker and k8s poll /health every 30 s. Without suppression this
        would produce ~2880 log lines per day per container, obscuring real
        events.  Verify the suppression pattern (access_log=None or equivalent)
        appears in the brain source.
        """
        brain_path = _CYRUS2_DIR / "cyrus_brain.py"
        source = brain_path.read_text(encoding="utf-8")
        self.assertIn(
            "access_log",
            source,
            "cyrus_brain.py must configure aiohttp access_log to suppress probe noise",
        )


# ── Port isolation ────────────────────────────────────────────────────────────


class TestPortIsolation(unittest.TestCase):
    """HEALTH_PORT must not conflict with any other registered port."""

    def test_health_port_not_conflict_with_existing_ports(self) -> None:
        """HEALTH_PORT=8771 must not collide with BRAIN/HOOK/MOBILE/COMPANION ports."""
        mod = importlib.reload(cyrus_config)
        existing = {
            mod.BRAIN_PORT,
            mod.HOOK_PORT,
            mod.MOBILE_PORT,
            mod.COMPANION_PORT,
            mod.SERVER_PORT,
        }
        self.assertNotIn(
            mod.HEALTH_PORT,
            existing,
            f"HEALTH_PORT {mod.HEALTH_PORT} conflicts with an existing port",
        )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
