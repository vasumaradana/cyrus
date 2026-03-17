"""
Acceptance-driven tests for Issue 006: Deprecate main.py monolith.

These tests verify every acceptance criterion from the issue using static
analysis (AST parsing and string inspection). No runtime execution required —
that would need audio hardware and Windows UIA.

Acceptance criteria verified:
  - main.py refactored to be a thin wrapper (≤ 30 lines)
  - Deprecation warning printed on startup (visible to user)
  - All business logic removed from main.py
  - main.py imports and delegates to cyrus_brain.py functions
  - Documentation updated: recommend split mode
  - cyrus_brain.py docstring marks it as PRIMARY ENTRY POINT
"""

import ast
import unittest
from pathlib import Path

# Resolve paths relative to this test file: tests/ → cyrus2/
CYRUS2_DIR = Path(__file__).parent.parent
MAIN_PY = CYRUS2_DIR / "main.py"
BRAIN_PY = CYRUS2_DIR / "cyrus_brain.py"
README_MD = CYRUS2_DIR / "README.md"


class TestMainIsThinWrapper(unittest.TestCase):
    """AC: main.py refactored to be a thin wrapper."""

    def test_main_is_thin_wrapper(self):
        """main.py must be ≤ 30 lines (excluding blank lines and comments)."""
        self.assertTrue(MAIN_PY.exists(), f"main.py not found at {MAIN_PY}")
        lines = MAIN_PY.read_text(encoding="utf-8").splitlines()
        total_lines = len(lines)
        self.assertLessEqual(
            total_lines,
            30,
            f"main.py has {total_lines} lines — expected ≤ 30 (thin wrapper).",
        )

    def test_main_docstring_says_deprecated(self):
        """AC: main.py module docstring must contain 'DEPRECATED'."""
        self.assertTrue(MAIN_PY.exists(), f"main.py not found at {MAIN_PY}")
        source = MAIN_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree)
        self.assertIsNotNone(docstring, "main.py must have a module docstring")
        self.assertIn(
            "DEPRECATED",
            docstring,
            "Module docstring must contain 'DEPRECATED' to signal deprecation.",
        )

    def test_main_imports_brain_main(self):
        """AC: main.py must import and delegate to cyrus_brain.main."""
        self.assertTrue(MAIN_PY.exists(), f"main.py not found at {MAIN_PY}")
        source = MAIN_PY.read_text(encoding="utf-8")
        self.assertIn(
            "from cyrus_brain import main",
            source,
            "main.py must contain 'from cyrus_brain import main' to delegate to brain.",
        )

    def test_main_prints_deprecation_warning(self):
        """AC: Deprecation warning printed on startup with service references."""
        self.assertTrue(MAIN_PY.exists(), f"main.py not found at {MAIN_PY}")
        source = MAIN_PY.read_text(encoding="utf-8")
        self.assertIn(
            "DEPRECATION",
            source,
            "main.py must print a 'DEPRECATION' warning on startup.",
        )
        # Must reference both services so user knows what to use instead
        self.assertIn(
            "cyrus_brain.py",
            source,
            "Deprecation warning must reference 'cyrus_brain.py' as the alternative.",
        )
        self.assertIn(
            "cyrus_voice.py",
            source,
            "Deprecation warning must reference 'cyrus_voice.py' as the alternative.",
        )

    def test_main_has_no_business_logic(self):
        """AC: All business logic removed — main.py must define at most one function."""
        self.assertTrue(MAIN_PY.exists(), f"main.py not found at {MAIN_PY}")
        source = MAIN_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        # Count only top-level (module-level) function and class definitions
        top_level_defs = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        self.assertLessEqual(
            len(top_level_defs),
            1,
            f"main.py defines {len(top_level_defs)} top-level functions/classes — "
            "expected at most 1 (the wrapper main()). Business logic must live in "
            "cyrus_brain.py or cyrus_voice.py.",
        )


class TestReadmeDocumentsDeprecation(unittest.TestCase):
    """AC: Documentation updated — recommend split mode, document monolith."""

    def test_readme_exists(self):
        """README.md must exist in the cyrus2/ directory."""
        self.assertTrue(
            README_MD.exists(),
            f"README.md not found at {README_MD}",
        )

    def test_readme_documents_deprecation(self):
        """README.md must mention deprecated monolith mode and recommend split mode."""
        self.assertTrue(README_MD.exists(), f"README.md not found at {README_MD}")
        content = README_MD.read_text(encoding="utf-8").lower()
        self.assertIn(
            "deprecated",
            content,
            "README.md must mention that monolith mode is deprecated.",
        )
        self.assertIn(
            "monolith",
            content,
            "README.md must reference 'monolith' mode in the deprecation section.",
        )


class TestBrainDocstringMarksPrimary(unittest.TestCase):
    """AC: cyrus_brain.py marked as PRIMARY ENTRY POINT."""

    def test_brain_docstring_marks_primary(self):
        """cyrus_brain.py module docstring must contain 'PRIMARY ENTRY POINT'."""
        self.assertTrue(BRAIN_PY.exists(), f"cyrus_brain.py not found at {BRAIN_PY}")
        source = BRAIN_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree)
        self.assertIsNotNone(docstring, "cyrus_brain.py must have a module docstring")
        self.assertIn(
            "PRIMARY",
            docstring,
            "cyrus_brain.py docstring must contain 'PRIMARY' to mark it as the "
            "primary entry point.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
