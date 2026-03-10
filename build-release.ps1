# Cyrus — Build Release Packages
# Run: powershell -ExecutionPolicy Bypass -File build-release.ps1
#
# Creates two zip files in dist/:
#   cyrus-voice-<version>.zip  — Voice service (runs anywhere)
#   cyrus-brain-<version>.zip  — Brain + Hook + Companion (runs on dev machine)

param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir   = "$ScriptDir\dist"

Write-Host "`n=== Building Cyrus Release v$Version ===" -ForegroundColor Cyan

# Clean dist
if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

# ── Build companion extension ─────────────────────────────────────────────────
Write-Host "`n[1/3] Building companion extension..."
Push-Location "$ScriptDir\cyrus-companion"
$ErrorActionPreference = "Continue"
npm run compile 2>&1 | Out-Null
npx @vscode/vsce package --no-dependencies 2>&1 | Out-Null
$ErrorActionPreference = "Stop"
Pop-Location

# ── Download Kokoro TTS models if not present ────────────────────────────────
$KokoroModel  = "$ScriptDir\kokoro-v1.0.onnx"
$KokoroVoices = "$ScriptDir\voices-v1.0.bin"
$HfBase = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

if (-not (Test-Path $KokoroModel)) {
    Write-Host "[1.5/3] Downloading Kokoro TTS model (~370 MB)..."
    Invoke-WebRequest -Uri "$HfBase/kokoro-v1.0.onnx" -OutFile $KokoroModel
}
if (-not (Test-Path $KokoroVoices)) {
    Write-Host "[1.5/3] Downloading Kokoro voices (~4 MB)..."
    Invoke-WebRequest -Uri "$HfBase/voices-v1.0.bin" -OutFile $KokoroVoices
}

# ── Package Voice ─────────────────────────────────────────────────────────────
Write-Host "[2/3] Packaging cyrus-voice..."
$VoiceStage = "$DistDir\_voice"
New-Item -ItemType Directory -Force -Path $VoiceStage | Out-Null

Copy-Item "$ScriptDir\cyrus_voice.py"            "$VoiceStage\"
Copy-Item "$ScriptDir\requirements-voice.txt"     "$VoiceStage\"
Copy-Item "$ScriptDir\install-voice.ps1"          "$VoiceStage\"
Copy-Item "$ScriptDir\install-voice.sh"           "$VoiceStage\"

# Include Kokoro TTS models
if (Test-Path $KokoroModel)  { Copy-Item $KokoroModel  "$VoiceStage\" }
if (Test-Path $KokoroVoices) { Copy-Item $KokoroVoices "$VoiceStage\" }

Compress-Archive -Path "$VoiceStage\*" -DestinationPath "$DistDir\cyrus-voice-$Version.zip" -Force
Remove-Item $VoiceStage -Recurse -Force

# ── Package Brain ─────────────────────────────────────────────────────────────
Write-Host "[3/3] Packaging cyrus-brain..."
$BrainStage = "$DistDir\_brain"
New-Item -ItemType Directory -Force -Path $BrainStage | Out-Null

Copy-Item "$ScriptDir\cyrus_brain.py"            "$BrainStage\"
Copy-Item "$ScriptDir\cyrus_hook.py"             "$BrainStage\"
Copy-Item "$ScriptDir\requirements-brain.txt"     "$BrainStage\"
Copy-Item "$ScriptDir\install-brain.ps1"          "$BrainStage\"
Copy-Item "$ScriptDir\install-brain.sh"           "$BrainStage\"

# Include pre-built companion extension
$VsixFile = Get-ChildItem "$ScriptDir\cyrus-companion\*.vsix" | Select-Object -First 1
if ($VsixFile) {
    New-Item -ItemType Directory -Force -Path "$BrainStage\cyrus-companion" | Out-Null
    Copy-Item $VsixFile.FullName "$BrainStage\cyrus-companion\"
}

Compress-Archive -Path "$BrainStage\*" -DestinationPath "$DistDir\cyrus-brain-$Version.zip" -Force
Remove-Item $BrainStage -Recurse -Force

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host "`n=== Release Built ===" -ForegroundColor Green
Write-Host ""
Get-ChildItem "$DistDir\*.zip" | ForEach-Object {
    $size = [math]::Round($_.Length / 1MB, 2)
    Write-Host "  $($_.Name)  ($size MB)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Upload these to GitHub Releases or share directly."
Write-Host ""
