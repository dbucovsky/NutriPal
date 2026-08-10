@echo off
REM Double-clickable wrapper for start-services.ps1 — runs it with
REM -ExecutionPolicy Bypass for this invocation only, so it works without
REM changing your PowerShell execution policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-services.ps1"
pause
