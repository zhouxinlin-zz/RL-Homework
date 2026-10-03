@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment is missing. Run Setup-Game.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m server.launch %*
if errorlevel 1 pause
