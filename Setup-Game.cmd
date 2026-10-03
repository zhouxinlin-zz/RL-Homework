@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
if errorlevel 1 (
  echo Setup failed. See the message above and README.md.
) else (
  echo Setup complete. Double-click Start-Game.cmd to play.
)
pause
