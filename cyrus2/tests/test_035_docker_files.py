"""Tests for Issue 035: Dockerfile and Docker Compose acceptance criteria.

Validates that the Docker infrastructure files exist and contain all required
configuration per the issue acceptance criteria.
"""

import os
import re

import pytest

CYRUS2_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKERFILE_PATH = os.path.join(CYRUS2_DIR, "Dockerfile")
COMPOSE_PATH = os.path.join(CYRUS2_DIR, "docker-compose.yml")
REQUIREMENTS_HEADLESS_PATH = os.path.join(CYRUS2_DIR, "requirements-brain-headless.txt")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dockerfile_content():
    """Read Dockerfile contents once for all tests."""
    with open(DOCKERFILE_PATH) as f:
        return f.read()


@pytest.fixture(scope="module")
def compose_content():
    """Read docker-compose.yml contents once for all tests."""
    with open(COMPOSE_PATH) as f:
        return f.read()


@pytest.fixture(scope="module")
def requirements_headless_content():
    """Read requirements-brain-headless.txt contents once for all tests."""
    with open(REQUIREMENTS_HEADLESS_PATH) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Acceptance tests — file existence
# ---------------------------------------------------------------------------


class TestFilesExist:
    """Verify required Docker files are present."""

    def test_dockerfile_exists(self):
        """Dockerfile must exist at cyrus2/Dockerfile."""
        assert os.path.isfile(DOCKERFILE_PATH), (
            f"Dockerfile not found at {DOCKERFILE_PATH}"
        )

    def test_compose_exists(self):
        """docker-compose.yml must exist at cyrus2/docker-compose.yml."""
        assert os.path.isfile(COMPOSE_PATH), (
            f"docker-compose.yml not found at {COMPOSE_PATH}"
        )

    def test_requirements_headless_exists(self):
        """requirements-brain-headless.txt must exist at cyrus2/."""
        assert os.path.isfile(REQUIREMENTS_HEADLESS_PATH), (
            f"requirements-brain-headless.txt not found at {REQUIREMENTS_HEADLESS_PATH}"
        )


# ---------------------------------------------------------------------------
# Acceptance tests — Dockerfile content
# ---------------------------------------------------------------------------


class TestDockerfileContent:
    """Verify Dockerfile contains all required configuration."""

    def test_uses_python_312_slim_base(self, dockerfile_content):
        """Dockerfile must use python:3.12-slim as base image."""
        assert "FROM python:3.12-slim" in dockerfile_content

    def test_workdir_is_app(self, dockerfile_content):
        """WORKDIR must be set to /app."""
        assert "WORKDIR /app" in dockerfile_content

    def test_env_cyrus_headless(self, dockerfile_content):
        """ENV CYRUS_HEADLESS=1 must be set in Dockerfile."""
        assert "ENV CYRUS_HEADLESS=1" in dockerfile_content

    def test_env_pythonunbuffered(self, dockerfile_content):
        """PYTHONUNBUFFERED=1 must be set for proper log streaming."""
        assert "PYTHONUNBUFFERED=1" in dockerfile_content

    def test_exposes_brain_port_8766(self, dockerfile_content):
        """Port 8766 (brain control) must be exposed."""
        assert "8766" in dockerfile_content

    def test_exposes_hook_port_8767(self, dockerfile_content):
        """Port 8767 (hook events) must be exposed."""
        assert "8767" in dockerfile_content

    def test_exposes_mobile_port_8769(self, dockerfile_content):
        """Port 8769 (mobile client) must be exposed."""
        assert "8769" in dockerfile_content

    def test_exposes_companion_port_8770(self, dockerfile_content):
        """Port 8770 (extension registration) must be exposed."""
        assert "8770" in dockerfile_content

    def test_expose_all_four_ports(self, dockerfile_content):
        """All four ports must appear in a single EXPOSE instruction."""
        assert re.search(r"EXPOSE.*8766.*8767.*8769.*8770", dockerfile_content)

    def test_cmd_runs_cyrus_brain(self, dockerfile_content):
        """CMD must start cyrus_brain.py."""
        assert 'CMD ["python", "cyrus_brain.py"]' in dockerfile_content

    def test_copies_requirements_headless(self, dockerfile_content):
        """COPY must include requirements-brain-headless.txt."""
        assert "requirements-brain-headless.txt" in dockerfile_content

    def test_pip_install_requirements(self, dockerfile_content):
        """RUN must install from requirements-brain-headless.txt."""
        assert "pip install" in dockerfile_content
        assert "requirements-brain-headless.txt" in dockerfile_content

    def test_copies_env_files(self, dockerfile_content):
        """COPY must include .env files for default configuration."""
        assert ".env" in dockerfile_content

    def test_healthcheck_present(self, dockerfile_content):
        """HEALTHCHECK instruction must be present."""
        assert "HEALTHCHECK" in dockerfile_content

    def test_healthcheck_targets_health_endpoint(self, dockerfile_content):
        """HEALTHCHECK must target the /health endpoint."""
        assert "/health" in dockerfile_content

    def test_copies_brain_source_files(self, dockerfile_content):
        """Core Python source files must be copied into the image."""
        required_files = [
            "cyrus_brain.py",
            "cyrus_hook.py",
            "cyrus_config.py",
            "cyrus_server.py",
        ]
        for fname in required_files:
            assert fname in dockerfile_content, (
                f"{fname} not found in Dockerfile COPY instructions"
            )

    def test_copies_common_and_log_modules(self, dockerfile_content):
        """cyrus_common.py and cyrus_log.py must be copied (brain imports them)."""
        assert "cyrus_common.py" in dockerfile_content
        assert "cyrus_log.py" in dockerfile_content


# ---------------------------------------------------------------------------
# Acceptance tests — docker-compose.yml content
# ---------------------------------------------------------------------------


class TestComposeContent:
    """Verify docker-compose.yml contains all required configuration."""

    def test_brain_service_defined(self, compose_content):
        """Brain service must be defined in compose."""
        assert "brain:" in compose_content

    def test_build_context_set(self, compose_content):
        """Build context must reference the local Dockerfile."""
        assert "build:" in compose_content

    def test_container_name_cyrus_brain(self, compose_content):
        """Container must be named cyrus-brain."""
        assert "cyrus-brain" in compose_content

    def test_port_8766_mapped(self, compose_content):
        """Port 8766 must be mapped."""
        assert "8766:8766" in compose_content

    def test_port_8767_mapped(self, compose_content):
        """Port 8767 must be mapped."""
        assert "8767:8767" in compose_content

    def test_port_8769_mapped(self, compose_content):
        """Port 8769 must be mapped."""
        assert "8769:8769" in compose_content

    def test_port_8770_mapped(self, compose_content):
        """Port 8770 must be mapped."""
        assert "8770:8770" in compose_content

    def test_cyrus_headless_env_in_compose(self, compose_content):
        """CYRUS_HEADLESS must be set in compose environment."""
        assert "CYRUS_HEADLESS" in compose_content

    def test_cyrus_auth_token_env_in_compose(self, compose_content):
        """CYRUS_AUTH_TOKEN must be configurable from environment."""
        assert "CYRUS_AUTH_TOKEN" in compose_content

    def test_cyrus_brain_host_in_compose(self, compose_content):
        """CYRUS_BRAIN_HOST must be set to 0.0.0.0 for container networking."""
        assert "CYRUS_BRAIN_HOST" in compose_content
        assert "0.0.0.0" in compose_content

    def test_env_volume_mounted(self, compose_content):
        """The .env file must be mounted as a read-only volume."""
        assert ".env" in compose_content
        assert "volumes:" in compose_content

    def test_healthcheck_in_compose(self, compose_content):
        """Compose must include a healthcheck configuration."""
        assert "healthcheck:" in compose_content

    def test_extra_hosts_for_linux_docker(self, compose_content):
        """extra_hosts must include host.docker.internal for Linux compatibility."""
        assert "extra_hosts:" in compose_content
        assert "host.docker.internal" in compose_content
        assert "host-gateway" in compose_content

    def test_restart_policy(self, compose_content):
        """Restart policy must be unless-stopped."""
        assert "unless-stopped" in compose_content

    def test_has_quickstart_comments(self, compose_content):
        """Compose file must include quick-start documentation comments."""
        content_lower = compose_content.lower()
        assert "Quick start" in compose_content or "quick start" in content_lower


# ---------------------------------------------------------------------------
# Acceptance tests — requirements-brain-headless.txt content
# ---------------------------------------------------------------------------


class TestRequirementsHeadless:
    """Verify headless requirements file pins correct dependencies."""

    def test_python_dotenv_pinned(self, requirements_headless_content):
        """python-dotenv must be pinned to an exact version."""
        assert re.search(r"python-dotenv==\d+\.\d+\.\d+", requirements_headless_content)

    def test_websockets_pinned(self, requirements_headless_content):
        """websockets must be pinned to an exact version."""
        assert re.search(r"websockets==\d+\.\d+", requirements_headless_content)

    def test_no_windows_only_packages(self, requirements_headless_content):
        """Windows-only packages must not be in the headless requirements."""
        windows_packages = [
            "pyautogui",
            "pygetwindow",
            "uiautomation",
            "keyboard",
            "comtypes",
        ]
        for pkg in windows_packages:
            assert pkg not in requirements_headless_content, (
                f"Windows-only package '{pkg}' found in headless requirements"
            )

    def test_no_gpu_packages(self, requirements_headless_content):
        """GPU/ML packages must not be in the minimal headless requirements."""
        gpu_packages = ["torch", "onnxruntime", "faster-whisper", "kokoro"]
        for pkg in gpu_packages:
            assert pkg not in requirements_headless_content, (
                f"GPU/ML package '{pkg}' found in headless requirements"
            )

    def test_only_minimal_packages(self, requirements_headless_content):
        """Headless requirements should only contain essential packages."""
        lines = [
            line.strip()
            for line in requirements_headless_content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        # Should have exactly 2 packages: python-dotenv and websockets
        assert len(lines) == 2, f"Expected 2 packages, got {len(lines)}: {lines}"

    def test_versions_match_codebase(self, requirements_headless_content):
        """Pinned versions must match the versions used in requirements-brain.txt."""
        # python-dotenv==1.2.2 and websockets==16.0 per the main requirements
        assert "python-dotenv==1.2.2" in requirements_headless_content
        assert "websockets==16.0" in requirements_headless_content
