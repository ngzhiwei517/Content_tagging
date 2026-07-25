@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CMD="

py -3.14 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.14"

if not defined PYTHON_CMD (
  py -3.13 -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=py -3.13"
)

if not defined PYTHON_CMD (
  py -3.11 -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=py -3.11"
)

if not defined PYTHON_CMD (
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD goto :python_error

if not exist ".venv\Scripts\python.exe" (
  echo Creating the local Python environment...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto :error
)

set "VENV_PYTHON=.venv\Scripts\python.exe"
set "REQUIREMENTS_MARKER=.venv\.requirements.sha256"
set "INSTALL_REQUIREMENTS="

"%VENV_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto :venv_error

"%VENV_PYTHON%" -c "import hashlib, pathlib, sys; req=pathlib.Path('requirements.txt'); marker=pathlib.Path(r'%REQUIREMENTS_MARKER%'); digest=hashlib.sha256(req.read_bytes()).hexdigest(); raise SystemExit(0 if marker.exists() and marker.read_text(encoding='utf-8').strip() == digest else 1)" >nul 2>&1
if errorlevel 1 set "INSTALL_REQUIREMENTS=1"

if not defined INSTALL_REQUIREMENTS (
  "%VENV_PYTHON%" -c "import streamlit, pandas, pyarrow, openpyxl, requests, cv2, apify_client, google.genai, numpy, librosa, soundfile, imageio_ffmpeg, PIL, plotly, google.protobuf" >nul 2>&1
  if errorlevel 1 set "INSTALL_REQUIREMENTS=1"
)

if defined INSTALL_REQUIREMENTS (
  echo Installing requirements...
  "%VENV_PYTHON%" -m pip install --upgrade pip
  if errorlevel 1 goto :error
  "%VENV_PYTHON%" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
  "%VENV_PYTHON%" -c "import hashlib, pathlib; req=pathlib.Path('requirements.txt'); pathlib.Path(r'%REQUIREMENTS_MARKER%').write_text(hashlib.sha256(req.read_bytes()).hexdigest(), encoding='utf-8')"
  if errorlevel 1 goto :error
)

"%VENV_PYTHON%" -m streamlit run app.py
exit /b %errorlevel%

:python_error
echo.
echo No supported Python installation was found.
echo Install Python 3.14 with the Python Launcher for Windows, then try again.
echo Python 3.13 and 3.11 are also supported fallbacks.
pause
exit /b 1

:venv_error
echo.
echo The existing .venv uses an unsupported or broken Python installation.
echo Delete the .venv folder, then run this file again to recreate it.
pause
exit /b 1

:error
echo.
echo Setup failed. Review the error above, then see docs\HANDOVER.md.
pause
exit /b 1

