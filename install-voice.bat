@echo off
:: Cyrus Voice Installer — double-click this file to install.
:: (Wraps install-voice.ps1, bypassing the default execution policy.)

powershell -ExecutionPolicy Bypass -File "%~dp0install-voice.ps1" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Installation failed. See errors above.
)
pause
