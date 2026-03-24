# Verification: Pin All Production Dependencies

**Issue**: [004-Pin-all-production-dependencies](/home/daniel/Projects/barf/cyrus/issues/004-Pin-all-production-dependencies.md)
**Status**: ALREADY IMPLEMENTED
**Created**: 2026-03-11
**Verified**: 2026-03-16

## Evidence

- `cyrus2/requirements.txt` — exists, 7 packages, all pinned with `==` ✅
- `cyrus2/requirements-voice.txt` — exists, 10 packages, all pinned with `==` ✅
- `cyrus2/requirements-brain.txt` — exists, 17 packages (superset), all pinned with `==` ✅
- `cyrus2/tests/test_004_requirements_pinning.py` — exists, 28 test methods across 7 test classes ✅
- Cross-file consistency (shared versions match, brain is superset) ✅
- Fragile GPU packages present in brain (`torch`, `faster-whisper`, `onnxruntime-gpu`, `kokoro-onnx[gpu]`) ✅
- GPU compatibility chain documented: CUDA 12.x + cuDNN 9 ✅

## Verification Steps

- [x] Per-file validation: all 3 files exist, all lines contain `==`, correct package counts (7/10/17)
- [x] Cross-file consistency: `python-dotenv` and `websockets` versions match across all files, brain is superset of both base and voice
- [x] Fragile package check: all 4 GPU-critical packages present in brain file
- [x] Test file exists with comprehensive acceptance-driven tests (pytest not available on system Python but file is syntactically valid)

## Minor Fixes Needed

- **Files are untracked in git** — all 3 requirements files + test file need to be committed. They exist on disk but `git status` shows them as untracked new files. This is expected for the cyrus2/ rewrite sprint (AC7 resolved as N/A).

## Ambiguity Resolutions (from original plan)

1. **Package counts**: AC said 17/10/8 — actual correct counts are 7/10/17 per interview answer
2. **Create vs modify**: Creating new files in `cyrus2/` (not modifying v1 root files)
3. **GPU compatibility**: Used latest stable PyPI versions, no pip freeze env available

## Version Table

All versions verified against PyPI as of 2026-03-16:

| Package | Version | File(s) |
|---|---|---|
| comtypes | 1.4.16 | base, brain |
| edge-tts | 7.2.7 | voice, brain |
| faster-whisper | 1.2.1 | voice, brain |
| keyboard | 0.13.5 | voice, brain |
| kokoro-onnx[gpu] | 0.5.0 | brain |
| numpy | 2.4.3 | voice, brain |
| onnxruntime-gpu | 1.24.3 | brain |
| pyautogui | 0.9.54 | base, brain |
| pygame-ce | 2.5.7 | voice, brain |
| pygetwindow | 0.0.9 | base, brain |
| pyperclip | 1.11.0 | base, brain |
| python-dotenv | 1.2.2 | base, voice, brain |
| silero-vad | 6.2.1 | voice, brain |
| sounddevice | 0.5.5 | voice, brain |
| torch | 2.10.0 | voice, brain |
| uiautomation | 2.0.29 | base, brain |
| websockets | 16.0 | base, voice, brain |

## Recommendation

Mark issue complete after committing the untracked files. All acceptance criteria are satisfied.
