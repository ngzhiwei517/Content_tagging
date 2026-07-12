@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Run run_windows.bat once to create the local environment.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m streamlit run creative_type_accuracy_checker_v7_alias_normalized.py
exit /b %errorlevel%

