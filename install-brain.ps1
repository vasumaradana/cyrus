# Cyrus Brain — Install Script (Windows)
# Run: powershell -ExecutionPolicy Bypass -File install-brain.ps1
#
# Installs Cyrus Brain + Hook + VS Code Companion Extension.
# Brain runs on the machine with VS Code + Claude Code.

param(
    [string]$InstallDir = "$env:USERPROFILE\.cyrus\brain"
)

$ErrorActionPreference = "Stop"

Write-Host "`n=== Cyrus Brain Installer ===" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Create install directory
Write-Host "`n[1/5] Creating install directory: $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# 2. Copy brain files
Write-Host "[2/5] Copying brain files..."
Copy-Item "$ScriptDir\cyrus_brain.py" "$InstallDir\" -Force
Copy-Item "$ScriptDir\cyrus_hook.py" "$InstallDir\" -Force
Copy-Item "$ScriptDir\requirements-brain.txt" "$InstallDir\" -Force

# Copy pre-built companion extension
$VsixFile = Get-ChildItem "$ScriptDir\cyrus-companion\*.vsix" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($VsixFile) {
    Copy-Item $VsixFile.FullName "$InstallDir\" -Force
    Write-Host "       Companion extension: $($VsixFile.Name)"
} else {
    Write-Host "       WARNING: No .vsix found. Build it first: cd cyrus-companion && npm run compile && npx @vscode/vsce package --no-dependencies" -ForegroundColor Yellow
}

# 3. Create virtual environment and install dependencies
Write-Host "[3/5] Setting up Python virtual environment..."
$VenvDir = "$InstallDir\venv"
if (-not (Test-Path "$VenvDir\Scripts\activate.ps1")) {
    python -m venv $VenvDir
}
& "$VenvDir\Scripts\pip.exe" install --upgrade pip -q
& "$VenvDir\Scripts\pip.exe" install -r "$InstallDir\requirements-brain.txt" -q

# 4. Install VS Code companion extension
Write-Host "[4/5] Installing VS Code companion extension..."
$VsixInDest = Get-ChildItem "$InstallDir\*.vsix" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($VsixInDest) {
    & code --install-extension $VsixInDest.FullName --force 2>$null
    Write-Host "       Extension installed. Restart VS Code to activate."
} else {
    Write-Host "       Skipped (no .vsix file found)." -ForegroundColor Yellow
}

# 5. Configure Claude Code hooks
Write-Host "[5/5] Configuring Claude Code hooks..."
$ClaudeDir = "$env:USERPROFILE\.claude"
New-Item -ItemType Directory -Force -Path $ClaudeDir | Out-Null
$HookPython = "$VenvDir\Scripts\python.exe" -replace '\\', '/'
$HookScript = "$InstallDir\cyrus_hook.py" -replace '\\', '/'

$HooksConfig = @{
    hooks = @{
        Stop = @(@{
            hooks = @(@{
                type    = "command"
                command = "$HookPython $HookScript"
                timeout = 5
            })
        })
        PreToolUse = @(@{
            hooks = @(@{
                type    = "command"
                command = "$HookPython $HookScript"
                timeout = 5
            })
        })
        PostToolUse = @(@{
            hooks = @(@{
                type    = "command"
                command = "$HookPython $HookScript"
                timeout = 5
            })
        })
        Notification = @(@{
            hooks = @(@{
                type    = "command"
                command = "$HookPython $HookScript"
                timeout = 5
            })
        })
        PreCompact = @(@{
            hooks = @(@{
                type    = "command"
                command = "$HookPython $HookScript"
                timeout = 5
            })
        })
    }
}

$SettingsFile = "$ClaudeDir\settings.json"
if (Test-Path $SettingsFile) {
    $Backup = "$SettingsFile.bak"
    Copy-Item $SettingsFile $Backup -Force
    Write-Host "       Backed up existing settings to: $Backup"
}
$HooksConfig | ConvertTo-Json -Depth 10 | Set-Content $SettingsFile -Encoding UTF8

# Create launch script
$LaunchScript = @"
@echo off
echo Starting Cyrus Brain
cd /d "$InstallDir"
"$VenvDir\Scripts\python.exe" cyrus_brain.py %*
pause
"@
Set-Content -Path "$InstallDir\start-brain.bat" -Value $LaunchScript

Write-Host "`n=== Installation Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Brain installed to: $InstallDir"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Restart VS Code (to activate companion extension)" -ForegroundColor Yellow
Write-Host "  2. Run: $InstallDir\start-brain.bat" -ForegroundColor Yellow
Write-Host "  3. On the voice machine, run install-voice and point it at this machine's IP" -ForegroundColor Yellow
Write-Host ""
