@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_ground.ps1" %*
exit /b %ERRORLEVEL%
