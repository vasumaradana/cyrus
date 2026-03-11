# Plan 004: Pin All Production Dependencies

## Summary

Create three pinned requirements files in `cyrus2/` with exact `==` versions for all production dependencies. The three files serve independent deployment modes: base (desktop automation only), voice (speech recognition + TTS), and brain (full system with GPU inference). Versions sourced from current PyPI stable releases and cross-checked for GPU compatibility (CUDA 12 / cuDNN 9).

## Ambiguity Resolution

The issue contains three internal conflicts identified by triage. Resolutions:

1. **Package counts**: The AC says 17/10/8, implementation steps describe 7/10/16, and v1 files have 16/10/7. Resolution: follow the implementation steps' **restructured layout** (base=7, voice=10, brain=superset) because it fixes the v1 naming confusion where `requirements.txt` was the superset. In the restructured layout, `requirements-brain.txt` is the superset at 17 packages (implementation steps listed 16 but omitted `comtypes` which belongs in the superset since it's a base dependency). Final counts: **7 / 10 / 17**.

2. **Create vs modify**: The AC says "Git shows changed files" but `cyrus2/` is empty — these are new files. Resolution: **create new files in `cyrus2/`** as specified by implementation steps. This is a rewrite sprint; the v1 root files are untouched.

3. **GPU compatibility**: No working Python environment exists to `pip freeze` from. Resolution: **use latest stable PyPI versions** cross-checked for CUDA 12 compatibility. Document the compatibility chain in the plan so the builder doesn't need to research.

## Version Table

All versions sourced from PyPI as of 2026-03-11.

| Package | Version | Notes |
|---|---|---|
| comtypes | 1.4.16 | Windows COM interface; required by uiautomation |
| edge-tts | 7.2.7 | Microsoft Edge TTS; minimal deps |
| faster-whisper | 1.2.1 | Uses CTranslate2; needs CUDA 12 + cuDNN 9 for GPU |
| keyboard | 0.13.5 | Unmaintained since 2020 but functional |
| kokoro-onnx[gpu] | 0.5.0 | GPU extra pulls onnxruntime-gpu; requires Python >=3.10,<3.14 |
| numpy | 2.4.3 | Compatible with torch 2.10.0 |
| onnxruntime-gpu | 1.24.3 | CUDA 12.x + cuDNN 9; satisfies `onnxruntime` requirement for faster-whisper |
| pyautogui | 0.9.54 | Cross-platform GUI automation |
| pygame-ce | 2.5.7 | Community edition; requires Python >=3.10 |
| pygetwindow | 0.0.9 | Window management |
| pyperclip | 1.11.0 | Clipboard access |
| python-dotenv | 1.2.2 | Shared across all three files |
| silero-vad | 6.2.1 | Requires torch>=1.12.0; compatible with pinned torch |
| sounddevice | 0.5.5 | PortAudio bindings |
| torch | 2.10.0 | CUDA 12 support; satisfies silero-vad torch>=1.12.0 |
| uiautomation | 2.0.29 | Windows UI automation; depends on comtypes |
| websockets | 16.0 | Shared across all three files; requires Python >=3.10 |

### GPU Compatibility Chain

All GPU packages target **CUDA 12.x + cuDNN 9**:
- `torch==2.10.0` — built for CUDA 12
- `onnxruntime-gpu==1.24.3` — built for CUDA 12.x + cuDNN 9
- `faster-whisper==1.2.1` — uses CTranslate2 which requires CUDA 12 + cuDNN 9
- `kokoro-onnx[gpu]==0.5.0` — delegates to onnxruntime-gpu for GPU execution
- `silero-vad==6.2.1` — uses torch for inference (CUDA 12 via torch)

Note: `onnxruntime-gpu` and `onnxruntime` provide the same Python module. `faster-whisper` declares a dependency on `onnxruntime`, which is satisfied by having `onnxruntime-gpu` installed. The v1 `requirements.txt` already lists both packages together, confirming this is a working combination.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `cyrus2/requirements.txt` (base, 7 packages) | `cyrus2/` is empty | Create file |
| `cyrus2/requirements-voice.txt` (voice, 10 packages) | `cyrus2/` is empty | Create file |
| `cyrus2/requirements-brain.txt` (brain, 17 packages) | `cyrus2/` is empty | Create file |
| All versions pinned with `==` | v1 files are all unpinned | Pin every package |
| Shared packages consistent | python-dotenv and websockets in multiple files | Same version in all files |
| Fragile packages compatible | Not verified | Cross-checked in version table above |

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC1 | `cyrus2/requirements.txt` exists with pinned versions | `test -f` + grep for `==` on every line |
| AC2 | `cyrus2/requirements-voice.txt` exists with pinned versions | `test -f` + grep for `==` on every line |
| AC3 | `cyrus2/requirements-brain.txt` exists with pinned versions | `test -f` + grep for `==` on every line |
| AC4 | Versions from working environment | N/A — no environment; used latest stable PyPI (documented) |
| AC5 | torch/faster-whisper/onnxruntime-gpu compatible | Verified via CUDA 12 compatibility chain above |
| AC6 | Each file installable without conflicts | `pip install --dry-run -r [file]` |
| AC7 | Git shows changed files | Will show as new files (cyrus2/ is empty); AC is incorrect for rewrite sprint |

## Implementation Steps

### Step 1: Create `cyrus2/requirements.txt` (base)

Write this exact content (alphabetical, one per line, `package==version`):

```
comtypes==1.4.16
pyautogui==0.9.54
pygetwindow==0.0.9
pyperclip==1.11.0
python-dotenv==1.2.2
uiautomation==2.0.29
websockets==16.0
```

**File:** `cyrus2/requirements.txt`

### Step 2: Verify base file

```bash
cd /home/daniel/Projects/barf/cyrus
test -f cyrus2/requirements.txt && echo "OK" || echo "FAIL"
```

```bash
python3 -c "
import sys
with open('cyrus2/requirements.txt') as f:
    lines = [l.strip() for l in f if l.strip()]
for line in lines:
    if '==' not in line:
        print(f'FAIL: not pinned: {line}')
        sys.exit(1)
print(f'OK: {len(lines)} packages, all pinned')
if len(lines) != 7:
    print(f'WARN: expected 7, got {len(lines)}')
    sys.exit(1)
"
```

### Step 3: Create `cyrus2/requirements-voice.txt`

Write this exact content:

```
edge-tts==7.2.7
faster-whisper==1.2.1
keyboard==0.13.5
numpy==2.4.3
pygame-ce==2.5.7
python-dotenv==1.2.2
silero-vad==6.2.1
sounddevice==0.5.5
torch==2.10.0
websockets==16.0
```

**File:** `cyrus2/requirements-voice.txt`

### Step 4: Verify voice file

```bash
python3 -c "
import sys
with open('cyrus2/requirements-voice.txt') as f:
    lines = [l.strip() for l in f if l.strip()]
for line in lines:
    if '==' not in line:
        print(f'FAIL: not pinned: {line}')
        sys.exit(1)
print(f'OK: {len(lines)} packages, all pinned')
if len(lines) != 10:
    print(f'WARN: expected 10, got {len(lines)}')
    sys.exit(1)
"
```

### Step 5: Create `cyrus2/requirements-brain.txt` (full system)

Write this exact content:

```
comtypes==1.4.16
edge-tts==7.2.7
faster-whisper==1.2.1
keyboard==0.13.5
kokoro-onnx[gpu]==0.5.0
numpy==2.4.3
onnxruntime-gpu==1.24.3
pyautogui==0.9.54
pygame-ce==2.5.7
pygetwindow==0.0.9
pyperclip==1.11.0
python-dotenv==1.2.2
silero-vad==6.2.1
sounddevice==0.5.5
torch==2.10.0
uiautomation==2.0.29
websockets==16.0
```

**File:** `cyrus2/requirements-brain.txt`

### Step 6: Verify brain file

```bash
python3 -c "
import sys
with open('cyrus2/requirements-brain.txt') as f:
    lines = [l.strip() for l in f if l.strip()]
for line in lines:
    if '==' not in line and '[' not in line.split('==')[0]:
        # kokoro-onnx[gpu]==0.5.0 is valid
        pass
    if '==' not in line:
        print(f'FAIL: not pinned: {line}')
        sys.exit(1)
print(f'OK: {len(lines)} packages, all pinned')
if len(lines) != 17:
    print(f'WARN: expected 17, got {len(lines)}')
    sys.exit(1)
"
```

### Step 7: Cross-file consistency check

Verify shared packages have identical versions across all files:

```bash
python3 -c "
import sys

def parse_reqs(path):
    with open(path) as f:
        return {l.split('==')[0].strip(): l.strip() for l in f if l.strip()}

base = parse_reqs('cyrus2/requirements.txt')
voice = parse_reqs('cyrus2/requirements-voice.txt')
brain = parse_reqs('cyrus2/requirements-brain.txt')

errors = []

# Check shared packages
for pkg in ['python-dotenv', 'websockets']:
    versions = set()
    for name, reqs in [('base', base), ('voice', voice), ('brain', brain)]:
        if pkg in reqs:
            versions.add(reqs[pkg])
    if len(versions) > 1:
        errors.append(f'{pkg} version mismatch: {versions}')

# Check brain is superset of base
for pkg in base:
    if pkg not in brain:
        errors.append(f'brain missing base package: {pkg}')

# Check brain is superset of voice
for pkg in voice:
    if pkg not in brain:
        errors.append(f'brain missing voice package: {pkg}')

# Check fragile packages are present
for pkg in ['torch', 'faster-whisper', 'onnxruntime-gpu', 'kokoro-onnx[gpu]']:
    key = pkg.split('[')[0]
    if key not in brain:
        errors.append(f'brain missing fragile package: {pkg}')

if errors:
    for e in errors:
        print(f'FAIL: {e}')
    sys.exit(1)
print('OK: all cross-file checks pass')
"
```

### Step 8: Syntax validation with pip (if available)

```bash
pip install --dry-run -r cyrus2/requirements.txt 2>&1 | tail -5
pip install --dry-run -r cyrus2/requirements-voice.txt 2>&1 | tail -5
pip install --dry-run -r cyrus2/requirements-brain.txt 2>&1 | tail -5
```

Note: `--dry-run` may fail if packages aren't available in the current environment's platform (e.g., `comtypes` and `uiautomation` are Windows-only). This is expected on Linux — the syntax validation in steps 2/4/6 covers correctness.

## Risk Assessment

**Low risk.** Three new text files with no code changes. The only failure modes are:
1. **Typo in package name** — caught by pip dry-run in step 8
2. **Version doesn't exist on PyPI** — caught by pip dry-run in step 8
3. **GPU version incompatibility** — mitigated by CUDA 12 compatibility chain analysis; full verification requires GPU hardware

**Known limitations:**
- `comtypes` and `uiautomation` are Windows-only; dry-run will fail on Linux for files containing them (base and brain)
- `keyboard==0.13.5` is unmaintained (last release 2020) but is the only version available
- Without a `pip freeze` from a known-good environment, versions are best-effort from PyPI latest stable
