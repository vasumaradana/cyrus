@echo off
:: Cyrus Brain Installer — double-click this file to install.
:: (Wraps install-brain.ps1, bypassing the default execution policy.)

powershell -ExecutionPolicy Bypass -File "%~dp0install-brain.ps1" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Installation failed. See errors above.
)
pause
