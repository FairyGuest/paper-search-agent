@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Launch
if errorlevel 1 (
  echo Installation or application failed. See the message above.
  pause
  exit /b 1
)
