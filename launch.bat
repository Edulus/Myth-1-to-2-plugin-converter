@echo off
rem Double-click entry point. Runs the real logic in scripts\launch.ps1 with
rem the execution policy bypassed just for this one script -- Windows blocks
rem .ps1 files from running by default, which is why this .bat exists at all.
title Myth plugin converter
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\launch.ps1"
echo.
echo Press any key to close this window.
pause >nul
endlocal
