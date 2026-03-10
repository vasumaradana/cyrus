# Cyrus Voice — Install Script (Windows)
# Run: powershell -ExecutionPolicy Bypass -File install-voice.ps1
#
# Installs Cyrus Voice service on this machine.
# Voice can run locally (same machine as Brain) or remotely.

param(
    [string]$InstallDir = "$env:USERPROFILE\.cyrus\voice",
    [string]$BrainHost  = "localhost",
    [int]$BrainPort     = 8766
)

$ErrorActionPreference = "Stop"

Write-Host "`n=== Cyrus Voice Installer ===" -ForegroundColor Cyan

# 1. Create install directory
Write-Host "`n[1/4] Creating install directory: $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# 2. Copy voice files
Write-Host "[2/4] Copying voice files..."
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Copy-Item "$ScriptDir\cyrus_voice.py" "$InstallDir\" -Force
Copy-Item "$ScriptDir\requirements-voice.txt" "$InstallDir\" -Force

# Copy or download Kokoro TTS model files
$HfBase = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
if (Test-Path "$ScriptDir\kokoro-v1.0.onnx") {
    Write-Host "       Copying Kokoro TTS model..."
    Copy-Item "$ScriptDir\kokoro-v1.0.onnx" "$InstallDir\" -Force
} elseif (-not (Test-Path "$InstallDir\kokoro-v1.0.onnx")) {
    Write-Host "       Downloading Kokoro TTS model (~370 MB)..."
    Invoke-WebRequest -Uri "$HfBase/kokoro-v1.0.onnx" -OutFile "$InstallDir\kokoro-v1.0.onnx"
}
if (Test-Path "$ScriptDir\voices-v1.0.bin") {
    Copy-Item "$ScriptDir\voices-v1.0.bin" "$InstallDir\" -Force
} elseif (-not (Test-Path "$InstallDir\voices-v1.0.bin")) {
    Write-Host "       Downloading Kokoro voices (~4 MB)..."
    Invoke-WebRequest -Uri "$HfBase/voices-v1.0.bin" -OutFile "$InstallDir\voices-v1.0.bin"
}

# 3. Create virtual environment and install dependencies
Write-Host "[3/4] Setting up Python virtual environment..."
$VenvDir = "$InstallDir\venv"
if (-not (Test-Path "$VenvDir\Scripts\activate.ps1")) {
    python -m venv $VenvDir
}
& "$VenvDir\Scripts\pip.exe" install --upgrade pip -q
& "$VenvDir\Scripts\pip.exe" install -r "$InstallDir\requirements-voice.txt" -q

# 4. Create launch script
Write-Host "[4/4] Creating launch script..."
$LaunchScript = @"
@echo off
echo Starting Cyrus Voice (connecting to Brain at $BrainHost`:$BrainPort)
cd /d "$InstallDir"
"$VenvDir\Scripts\python.exe" cyrus_voice.py --host $BrainHost --port $BrainPort %*
pause
"@
Set-Content -Path "$InstallDir\start-voice.bat" -Value $LaunchScript

Write-Host "`n=== Installation Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Voice installed to: $InstallDir"
Write-Host ""
Write-Host "To start Cyrus Voice:"
Write-Host "  $InstallDir\start-voice.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "To connect to a remote Brain:"
Write-Host "  $InstallDir\start-voice.bat --host <brain-ip>" -ForegroundColor Yellow
Write-Host ""
