"""
Acceptance-driven tests for Issue 004: Pin All Production Dependencies.

These tests verify every acceptance criterion from the issue:
  - cyrus2/requirements.txt exists with exactly 7 pinned packages
  - cyrus2/requirements-voice.txt exists with exactly 10 pinned packages
  - cyrus2/requirements-brain.txt exists with exactly 18 pinned packages (superset)
  - All packages use exact == pinning (not >= or ~=)
  - Shared packages (python-dotenv, websockets) have identical versions across files
  - Brain file is a superset of both base and voice files
  - Fragile GPU packages (torch, faster-whisper, onnxruntime-gpu, kokoro-onnx[gpu])
    are all present in the brain file
"""

import unittest
from pathlib import Path

# Resolve requirements files relative to this test file's parent directory (cyrus2/)
CYRUS2_DIR = Path(__file__).parent.parent
REQ_BASE = CYRUS2_DIR / "requirements.txt"
REQ_VOICE = CYRUS2_DIR / "requirements-voice.txt"
REQ_BRAIN = CYRUS2_DIR / "requirements-brain.txt"

# Expected package counts per file
EXPECTED_BASE_COUNT = 7
EXPECTED_VOICE_COUNT = 10
EXPECTED_BRAIN_COUNT = 18


def read_content_lines(path: Path) -> list[str]:
    """Return non-empty, non-comment lines from a requirements file."""
    with path.open() as fh:
        return [raw.strip() for raw in fh if raw.strip() and not raw.startswith("#")]


def parse_requirements(path: Path) -> dict[str, str]:
    """Parse a requirements file into {package_name: full_line} mapping.

    The key is the full package specifier before '==' (including extras,
    e.g. 'kokoro-onnx[gpu]'). The value is the full pinned line.
    """
    result = {}
    for line in read_content_lines(path):
        key = line.split("==")[0].strip()
        result[key] = line
    return result


class TestBaseRequirementsFileExists(unittest.TestCase):
    """AC1: cyrus2/requirements.txt must exist with pinned versions."""

    def test_file_exists(self):
        """AC1: requirements.txt must exist."""
        self.assertTrue(REQ_BASE.exists(), f"requirements.txt not found at {REQ_BASE}")

    def test_file_not_empty(self):
        """requirements.txt must not be empty."""
        self.assertGreater(REQ_BASE.stat().st_size, 0, "requirements.txt is empty")

    def test_exact_package_count(self):
        """AC1: Must contain exactly 7 packages (base UI-automation packages)."""
        packages = parse_requirements(REQ_BASE)
        self.assertEqual(
            len(packages),
            EXPECTED_BASE_COUNT,
            f"Expected {EXPECTED_BASE_COUNT} packages in requirements.txt, "
            f"got {len(packages)}: {list(packages.keys())}",
        )

    def test_all_packages_pinned_with_exact_version(self):
        """AC1: Every line must use == pinning, not >= or ~=."""
        for line in read_content_lines(REQ_BASE):
            self.assertIn(
                "==",
                line,
                f"requirements.txt line is not exactly pinned: '{line}'",
            )
            self.assertNotIn(
                ">=",
                line,
                f"requirements.txt has loose >= constraint: '{line}'",
            )


class TestVoiceRequirementsFileExists(unittest.TestCase):
    """AC2: cyrus2/requirements-voice.txt must exist with pinned versions."""

    def test_file_exists(self):
        """AC2: requirements-voice.txt must exist."""
        self.assertTrue(
            REQ_VOICE.exists(),
            f"requirements-voice.txt not found at {REQ_VOICE}",
        )

    def test_file_not_empty(self):
        """requirements-voice.txt must not be empty."""
        self.assertGreater(
            REQ_VOICE.stat().st_size, 0, "requirements-voice.txt is empty"
        )

    def test_exact_package_count(self):
        """AC2: Must contain exactly 10 packages (speech and audio packages)."""
        packages = parse_requirements(REQ_VOICE)
        self.assertEqual(
            len(packages),
            EXPECTED_VOICE_COUNT,
            f"Expected {EXPECTED_VOICE_COUNT} packages in requirements-voice.txt, "
            f"got {len(packages)}: {list(packages.keys())}",
        )

    def test_all_packages_pinned_with_exact_version(self):
        """AC2: Every line must use == pinning, not >= or ~=."""
        for line in read_content_lines(REQ_VOICE):
            self.assertIn(
                "==",
                line,
                f"requirements-voice.txt line is not exactly pinned: '{line}'",
            )
            self.assertNotIn(
                ">=",
                line,
                f"requirements-voice.txt has loose >= constraint: '{line}'",
            )


class TestBrainRequirementsFileExists(unittest.TestCase):
    """AC3: cyrus2/requirements-brain.txt must exist with 17 pinned packages."""

    def test_file_exists(self):
        """AC3: requirements-brain.txt must exist."""
        self.assertTrue(
            REQ_BRAIN.exists(),
            f"requirements-brain.txt not found at {REQ_BRAIN}",
        )

    def test_file_not_empty(self):
        """requirements-brain.txt must not be empty."""
        self.assertGreater(
            REQ_BRAIN.stat().st_size, 0, "requirements-brain.txt is empty"
        )

    def test_exact_package_count(self):
        """AC3: Must contain exactly 17 packages (full superset)."""
        packages = parse_requirements(REQ_BRAIN)
        self.assertEqual(
            len(packages),
            EXPECTED_BRAIN_COUNT,
            f"Expected {EXPECTED_BRAIN_COUNT} packages in requirements-brain.txt, "
            f"got {len(packages)}: {list(packages.keys())}",
        )

    def test_all_packages_pinned_with_exact_version(self):
        """AC3: Every line must use == pinning, not >= or ~=."""
        for line in read_content_lines(REQ_BRAIN):
            self.assertIn(
                "==",
                line,
                f"requirements-brain.txt line is not exactly pinned: '{line}'",
            )
            self.assertNotIn(
                ">=",
                line,
                f"requirements-brain.txt has loose >= constraint: '{line}'",
            )


class TestFragilePackagesInBrain(unittest.TestCase):
    """AC5: torch, faster-whisper, onnxruntime-gpu, kokoro-onnx[gpu] in brain."""

    @classmethod
    def setUpClass(cls):
        cls.brain = parse_requirements(REQ_BRAIN)

    def test_torch_present(self):
        """AC5: torch must be in requirements-brain.txt for GPU inference."""
        self.assertIn("torch", self.brain, "torch missing from requirements-brain.txt")

    def test_torch_pinned(self):
        """AC5: torch must be exactly pinned (CUDA 12 target)."""
        if "torch" in self.brain:
            self.assertIn("==", self.brain["torch"], "torch is not exactly pinned")

    def test_faster_whisper_present(self):
        """AC5: faster-whisper must be in requirements-brain.txt."""
        self.assertIn(
            "faster-whisper",
            self.brain,
            "faster-whisper missing from requirements-brain.txt",
        )

    def test_faster_whisper_pinned(self):
        """AC5: faster-whisper must be exactly pinned."""
        if "faster-whisper" in self.brain:
            self.assertIn(
                "==",
                self.brain["faster-whisper"],
                "faster-whisper is not exactly pinned",
            )

    def test_onnxruntime_gpu_present(self):
        """AC5: onnxruntime-gpu must be in brain file (CUDA 12 + cuDNN 9)."""
        self.assertIn(
            "onnxruntime-gpu",
            self.brain,
            "onnxruntime-gpu missing from requirements-brain.txt",
        )

    def test_onnxruntime_gpu_pinned(self):
        """AC5: onnxruntime-gpu must be exactly pinned."""
        if "onnxruntime-gpu" in self.brain:
            self.assertIn(
                "==",
                self.brain["onnxruntime-gpu"],
                "onnxruntime-gpu is not exactly pinned",
            )

    def test_kokoro_onnx_gpu_present(self):
        """AC5: kokoro-onnx[gpu] must be in requirements-brain.txt."""
        self.assertIn(
            "kokoro-onnx[gpu]",
            self.brain,
            "kokoro-onnx[gpu] missing from requirements-brain.txt",
        )

    def test_kokoro_onnx_gpu_pinned(self):
        """AC5: kokoro-onnx[gpu] must be exactly pinned."""
        if "kokoro-onnx[gpu]" in self.brain:
            self.assertIn(
                "==",
                self.brain["kokoro-onnx[gpu]"],
                "kokoro-onnx[gpu] is not exactly pinned",
            )


class TestCrossFileConsistency(unittest.TestCase):
    """Shared packages must have identical versions across all three files."""

    @classmethod
    def setUpClass(cls):
        cls.base = parse_requirements(REQ_BASE)
        cls.voice = parse_requirements(REQ_VOICE)
        cls.brain = parse_requirements(REQ_BRAIN)

    def _check_shared_version(self, pkg: str) -> None:
        """Assert a package has the same version in all files it appears in."""
        files = [
            ("base", self.base),
            ("voice", self.voice),
            ("brain", self.brain),
        ]
        versions = {name: reqs[pkg] for name, reqs in files if pkg in reqs}
        self.assertGreater(
            len(versions), 0, f"{pkg} not found in any requirements file"
        )
        unique = set(versions.values())
        self.assertEqual(
            len(unique),
            1,
            f"{pkg} version mismatch across files: {versions}",
        )

    def test_python_dotenv_consistent_across_files(self):
        """python-dotenv must have the same pinned version in all three files."""
        self._check_shared_version("python-dotenv")

    def test_websockets_consistent_across_files(self):
        """websockets must have the same pinned version in all three files."""
        self._check_shared_version("websockets")

    def test_brain_is_superset_of_base(self):
        """requirements-brain.txt must contain all packages from requirements.txt."""
        missing = [pkg for pkg in self.base if pkg not in self.brain]
        self.assertEqual(
            missing,
            [],
            f"Brain file missing these base packages: {missing}",
        )

    def test_brain_is_superset_of_voice(self):
        """Brain file must contain all packages from requirements-voice.txt."""
        missing = [pkg for pkg in self.voice if pkg not in self.brain]
        self.assertEqual(
            missing,
            [],
            f"Brain file missing these voice packages: {missing}",
        )

    def test_shared_packages_version_matches_between_base_and_brain(self):
        """When a package appears in both base and brain, versions must match."""
        for pkg in self.base:
            if pkg in self.brain:
                self.assertEqual(
                    self.base[pkg],
                    self.brain[pkg],
                    f"Version mismatch for '{pkg}' between base and brain: "
                    f"'{self.base[pkg]}' vs '{self.brain[pkg]}'",
                )

    def test_shared_packages_version_matches_between_voice_and_brain(self):
        """When a package appears in both voice and brain, versions must match."""
        for pkg in self.voice:
            if pkg in self.brain:
                self.assertEqual(
                    self.voice[pkg],
                    self.brain[pkg],
                    f"Version mismatch for '{pkg}' between voice and brain: "
                    f"'{self.voice[pkg]}' vs '{self.brain[pkg]}'",
                )


class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions for requirements files."""

    def _check_no_duplicates(self, path: Path) -> None:
        """Assert a requirements file has no duplicate package entries."""
        lines = read_content_lines(path)
        keys = [line.split("==")[0].strip() for line in lines]
        dupes = [k for k in keys if keys.count(k) > 1]
        self.assertEqual(
            len(keys),
            len(set(keys)),
            f"Duplicate packages in {path.name}: {dupes}",
        )

    def test_no_duplicate_packages_in_base(self):
        """requirements.txt must not list the same package twice."""
        self._check_no_duplicates(REQ_BASE)

    def test_no_duplicate_packages_in_voice(self):
        """requirements-voice.txt must not list the same package twice."""
        self._check_no_duplicates(REQ_VOICE)

    def test_no_duplicate_packages_in_brain(self):
        """requirements-brain.txt must not list the same package twice."""
        self._check_no_duplicates(REQ_BRAIN)

    def test_no_local_path_references_in_base(self):
        """requirements.txt must not contain local path references (e.g. ./pkg)."""
        for line in read_content_lines(REQ_BASE):
            self.assertFalse(
                line.startswith("./") or line.startswith("/"),
                f"Local path reference in requirements.txt: '{line}'",
            )

    def test_no_vcs_references_in_brain(self):
        """requirements-brain.txt must not contain VCS references."""
        for line in read_content_lines(REQ_BRAIN):
            for vcs_prefix in ("git+", "hg+", "svn+", "bzr+"):
                self.assertFalse(
                    line.startswith(vcs_prefix),
                    f"VCS reference in requirements-brain.txt: '{line}'",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
