@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python 3.11 environment...
  py -3.11 -m venv .venv
  if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import streamlit, plotly" >nul 2>&1
if errorlevel 1 (
  echo Installing requirements...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :error
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -m streamlit run app.py
exit /b %errorlevel%

:error
echo Setup failed. Check that Python 3.11 is installed and available through the py launcher.
pause
exit /b 1

