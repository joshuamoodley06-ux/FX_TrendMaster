@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart-dev.ps1" %*
exit /b %ERRORLEVEL%
