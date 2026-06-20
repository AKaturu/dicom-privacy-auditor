@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-dat.ps1" "%~1" "%~2"
exit /b %ERRORLEVEL%
