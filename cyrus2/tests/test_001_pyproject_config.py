"""
Acceptance-driven tests for Issue 001: Create pyproject.toml with Ruff Config.

These tests verify every acceptance criterion from the issue:
  - File exists with project metadata (name, version, requires-python)
  - Ruff rule sets include E, F, W, I, UP, B
  - target-version = py310, line-length = 88
  - Exclude patterns contain .venv and cyrus-companion
  - Both [tool.ruff.lint] and [tool.ruff.format] sections are present
"""

import unittest
from pathlib import Path

import tomllib

# Resolve pyproject.toml relative to this test file's parent directory (cyrus2/)
PYPROJECT_PATH = Path(__file__).parent.parent / "pyproject.toml"


def load_pyproject() -> dict:
    """Load and parse pyproject.toml using the stdlib tomllib (Python 3.11+)."""
    with PYPROJECT_PATH.open("rb") as fh:
        return tomllib.load(fh)


class TestPyprojectExists(unittest.TestCase):
    """Verify the file exists and is parseable TOML."""

    def test_file_exists(self):
        """AC: File cyrus2/pyproject.toml must exist."""
        self.assertTrue(
            PYPROJECT_PATH.exists(),
            f"pyproject.toml not found at {PYPROJECT_PATH}",
        )

    def test_file_is_valid_toml(self):
        """AC: File must be parseable as valid TOML."""
        try:
            data = load_pyproject()
        except tomllib.TOMLDecodeError as exc:
            self.fail(f"pyproject.toml is not valid TOML: {exc}")
        self.assertIsInstance(data, dict)


class TestProjectMetadata(unittest.TestCase):
    """Verify [project] metadata section."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_pyproject()

    def test_project_section_exists(self):
        """[project] table must be present."""
        self.assertIn("project", self.data)

    def test_project_name(self):
        """AC: name must be 'cyrus'."""
        self.assertEqual(self.data["project"].get("name"), "cyrus")

    def test_project_version(self):
        """AC: version must be '2.0.0'."""
        self.assertEqual(self.data["project"].get("version"), "2.0.0")

    def test_requires_python(self):
        """AC: requires-python must be '>=3.10'."""
        self.assertEqual(self.data["project"].get("requires-python"), ">=3.10")

    def test_description_present(self):
        """description field should be a non-empty string."""
        desc = self.data["project"].get("description", "")
        self.assertIsInstance(desc, str)
        self.assertGreater(len(desc), 0, "description should not be empty")


class TestRuffTopLevel(unittest.TestCase):
    """Verify [tool.ruff] top-level settings."""

    @classmethod
    def setUpClass(cls):
        cls.ruff = load_pyproject().get("tool", {}).get("ruff", {})

    def test_ruff_section_exists(self):
        """[tool.ruff] table must be present."""
        self.assertNotEqual(self.ruff, {}, "[tool.ruff] section is missing or empty")

    def test_target_version(self):
        """AC: target-version must be 'py310'."""
        self.assertEqual(
            self.ruff.get("target-version"),
            "py310",
            "target-version must be 'py310'",
        )

    def test_line_length(self):
        """AC: line-length must be 88."""
        self.assertEqual(
            self.ruff.get("line-length"),
            88,
            "line-length must be 88",
        )

    def test_exclude_contains_venv(self):
        """AC: exclude patterns must include '.venv'."""
        excludes = self.ruff.get("exclude", [])
        self.assertIn(".venv", excludes, "exclude must contain '.venv'")

    def test_exclude_contains_cyrus_companion(self):
        """AC: exclude patterns must include 'cyrus-companion'."""
        excludes = self.ruff.get("exclude", [])
        self.assertIn(
            "cyrus-companion",
            excludes,
            "exclude must contain 'cyrus-companion'",
        )


class TestRuffLintSection(unittest.TestCase):
    """Verify [tool.ruff.lint] section and rule sets."""

    @classmethod
    def setUpClass(cls):
        cls.lint = load_pyproject().get("tool", {}).get("ruff", {}).get("lint", {})

    def test_lint_section_exists(self):
        """AC: [tool.ruff.lint] section must be present."""
        data = load_pyproject()
        ruff = data.get("tool", {}).get("ruff", {})
        # The section must exist as a key (even if empty, but issue requires 'select')
        self.assertIn("lint", ruff, "[tool.ruff.lint] section is missing")

    def test_select_contains_E(self):
        """AC: rule set must include 'E' (pycodestyle errors)."""
        self.assertIn("E", self.lint.get("select", []))

    def test_select_contains_F(self):
        """AC: rule set must include 'F' (pyflakes)."""
        self.assertIn("F", self.lint.get("select", []))

    def test_select_contains_W(self):
        """AC: rule set must include 'W' (pycodestyle warnings)."""
        self.assertIn("W", self.lint.get("select", []))

    def test_select_contains_I(self):
        """AC: rule set must include 'I' (isort)."""
        self.assertIn("I", self.lint.get("select", []))

    def test_select_contains_UP(self):
        """AC: rule set must include 'UP' (pyupgrade)."""
        self.assertIn("UP", self.lint.get("select", []))

    def test_select_contains_B(self):
        """AC: rule set must include 'B' (flake8-bugbear)."""
        self.assertIn("B", self.lint.get("select", []))

    def test_select_exact_rules(self):
        """All six required rule sets must be present together."""
        required = {"E", "F", "W", "I", "UP", "B"}
        actual = set(self.lint.get("select", []))
        self.assertTrue(
            required.issubset(actual),
            f"Missing rule sets: {required - actual}",
        )


class TestRuffFormatSection(unittest.TestCase):
    """Verify [tool.ruff.format] section exists."""

    def test_format_section_exists(self):
        """AC: [tool.ruff.format] section must be present."""
        data = load_pyproject()
        ruff = data.get("tool", {}).get("ruff", {})
        self.assertIn(
            "format",
            ruff,
            "[tool.ruff.format] section is missing",
        )


class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_pyproject()

    def test_file_is_not_empty(self):
        """pyproject.toml must not be empty."""
        self.assertGreater(
            PYPROJECT_PATH.stat().st_size,
            0,
            "pyproject.toml must not be empty",
        )

    def test_tool_section_present(self):
        """[tool] parent section must exist to house ruff config."""
        self.assertIn("tool", self.data)

    def test_exclude_is_a_list(self):
        """exclude must be a list, not a string."""
        excludes = self.data.get("tool", {}).get("ruff", {}).get("exclude", None)
        self.assertIsInstance(excludes, list, "exclude must be a TOML array")

    def test_select_is_a_list(self):
        """select must be a list, not a string."""
        ruff = self.data.get("tool", {}).get("ruff", {})
        select = ruff.get("lint", {}).get("select", None)
        self.assertIsInstance(select, list, "select must be a TOML array")

    def test_no_extra_unexpected_keys_in_project(self):
        """[project] should have at least the 4 required keys."""
        project_keys = set(self.data.get("project", {}).keys())
        required_keys = {"name", "version", "description", "requires-python"}
        missing = required_keys - project_keys
        self.assertEqual(missing, set(), f"Missing keys in [project]: {missing}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
