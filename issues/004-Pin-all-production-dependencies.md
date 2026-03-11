---
id=004-Pin-all-production-dependencies
title=Issue 004: Pin All Production Dependencies
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=38121
total_output_tokens=3
total_duration_seconds=80
total_iterations=1
run_count=1
---

# Issue 004: Pin All Production Dependencies

## Sprint
Cyrus 2.0 Rewrite — Foundation (Week 1)

## Priority
High

## References
- docs/12-code-audit.md — Section H5 "All Dependencies Unpinned"
- /home/daniel/Projects/barf/cyrus/requirements.txt (v1 unpinned base)
- /home/daniel/Projects/barf/cyrus/requirements-voice.txt (v1 unpinned voice)
- /home/daniel/Projects/barf/cyrus/requirements-brain.txt (v1 unpinned brain)

## Description
Pinning all production dependencies to exact versions ensures reproducible builds, prevents silent breakage from upstream changes, and is especially critical for fragile packages (torch, faster-whisper, onnxruntime-gpu). Currently all three requirements files are unpinned, leading to non-deterministic installs and version conflicts.

## Blocked By
- None (but Issue 002 should be complete for consistency)

## Acceptance Criteria
- [ ] `cyrus2/requirements.txt` exists with exact pinned versions (all 17 packages)
- [ ] `cyrus2/requirements-voice.txt` exists with exact pinned versions (all 10 packages)
- [ ] `cyrus2/requirements-brain.txt` exists with exact pinned versions (all 8 packages)
- [ ] All versions obtained from active/working Python environment via `pip freeze`
- [ ] torch, faster-whisper, onnxruntime-gpu have confirmed compatible versions
- [ ] Each file can be installed with `pip install -r [file]` without version conflicts
- [ ] Git shows changed files (not new files) — tracking version updates over time

## Implementation Steps
1. Identify a working Python environment with all current dependencies installed
2. From that environment, run `pip freeze > /tmp/freeze.txt` to capture all installed versions
3. Extract pinned versions for base requirements:
   - pyautogui
   - pyperclip
   - pygetwindow
   - uiautomation
   - comtypes
   - python-dotenv
   - websockets
   Create `cyrus2/requirements.txt` with format: `package==X.Y.Z`
4. Extract pinned versions for voice requirements:
   - faster-whisper
   - sounddevice
   - numpy
   - torch
   - silero-vad
   - edge-tts
   - keyboard
   - pygame-ce
   - python-dotenv (already in base, but verify version match)
   - websockets (already in base, but verify version match)
   Create `cyrus2/requirements-voice.txt` with format: `package==X.Y.Z`
5. Extract pinned versions for brain requirements:
   - faster-whisper
   - sounddevice
   - numpy
   - torch
   - silero-vad
   - edge-tts
   - kokoro-onnx[gpu]
   - onnxruntime-gpu
   - keyboard
   - pygame-ce
   - pyautogui
   - pyperclip
   - pygetwindow
   - uiautomation
   - python-dotenv
   - websockets
   Create `cyrus2/requirements-brain.txt` with format: `package==X.Y.Z`
6. Cross-verify torch/onnxruntime-gpu/faster-whisper compatibility by checking changelog/issues
7. Test install (if possible):
   ```bash
   pip install -r cyrus2/requirements.txt
   pip install -r cyrus2/requirements-voice.txt
   pip install -r cyrus2/requirements-brain.txt
   ```

## Files to Create/Modify
- `cyrus2/requirements.txt` (create, pinned versions)
- `cyrus2/requirements-voice.txt` (create, pinned versions)
- `cyrus2/requirements-brain.txt` (create, pinned versions)

## Testing
```bash
# Verify files exist and contain pinned versions
cat cyrus2/requirements.txt | head -5
cat cyrus2/requirements-voice.txt | head -5
cat cyrus2/requirements-brain.txt | head -5

# Test syntax (Python can parse requirement files)
python -c "from pip._internal.req import parse_requirements; list(parse_requirements('cyrus2/requirements.txt', session=None))"

# If environment available: test install
pip install -r cyrus2/requirements.txt --dry-run

# Verify key fragile packages are pinned
grep torch cyrus2/requirements-*.txt
grep faster-whisper cyrus2/requirements-*.txt
grep onnxruntime cyrus2/requirements-brain.txt
```

## Notes
- **Fragile packages**: torch, faster-whisper, onnxruntime-gpu frequently have breaking changes. Pin exact versions.
- **Shared packages**: python-dotenv and websockets appear in multiple files. Ensure consistent versions across all three files.
- **GPU support**: kokoro-onnx[gpu] and onnxruntime-gpu are only in brain requirements. Ensure CUDA/cuDNN compatibility with pinned versions.
- **Version sourcing**: Use `pip freeze` from the current working environment. If this environment is known-good, capturing versions ensures reproducibility.
- **Future updates**: Consider `pip-compile` or `uv` for lockfile management if dependency updates become frequent.
- **Documentation**: Add a note in the project README about the three requirement files and when each is used (base, voice-only setup, brain-only setup).

## Fragile Package Guidance
When pinning these versions, verify compatibility:
- **torch**: Check CUDA version compatibility if using GPU (e.g., torch 2.x requires CUDA 11.8+)
- **faster-whisper**: Ensure compatible with the pinned numpy version
- **onnxruntime-gpu**: Must match GPU hardware and CUDA version
- **silero-vad**: Generally stable, but verify with pinned torch version
- **edge-tts**: Usually stable, minimal dependencies
- **kokoro-onnx**: GPU variant; ensure CUDA/ONNXRuntime compatibility

## Interview Questions

1. The acceptance criteria claim base=17, voice=10, brain=8 packages, but implementation steps describe base=7, voice=10, brain=16 packages. The actual v1 files have requirements.txt=16, requirements-voice.txt=10, requirements-brain.txt=7. Which structure is correct?
   - Follow implementation steps (7, 10, 16) — AC numbers are errors
   - Follow AC (17, 10, 8) — implementation steps are outdated
   - Follow actual v1 files (16, 10, 7) — both AC and implementation steps need fixes
2. The AC states 'Git shows changed files (not new files)' but Files to Create/Modify says 'create'. Should we update the v1 requirements files in the root directory, or create new pinned files in cyrus2/?
   - Update v1 files in root (main.py, cyrus_voice.py, cyrus_brain.py directory level)
   - Create new pinned files in cyrus2/ directory (for the rewrite)
   - Do both — pin v1 files AND create copies in cyrus2/
3. GPU compatibility verification (torch, onnxruntime-gpu, kokoro-onnx) requires checking CUDA version compatibility. Should the implementation research compatible versions from package docs, or is there a known-good GPU environment to test against?
   - Research compatible versions from package changelog/docs/GitHub issues
   - There is a test environment available with GPU hardware to validate
   - Skip GPU compatibility testing — just use pip freeze from current environment

## Stage Log

### NEW — 2026-03-11 18:00:46Z

- **From:** NEW
- **Duration in stage:** 80s
- **Input tokens:** 38,121 (final context: 38,121)
- **Output tokens:** 3
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
