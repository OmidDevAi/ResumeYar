@echo off
setlocal
cd /d "%~dp0"

set "PYEXE=..\.venv\Scripts\python.exe"
set "PYW=..\.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=%PYEXE%"
if not exist "%PYEXE%" (
  echo Virtual environment not found: ..\.venv
  echo Run ..\run.bat once, then install desktop\requirements_desktop.txt.
  pause
  exit /b 1
)

"%PYEXE%" -c "import webview" 2>nul
if errorlevel 1 (
  echo pywebview is missing. Installing from requirements_desktop.txt...
  "%PYEXE%" -m pip install -r requirements_desktop.txt || (
    echo Install failed.
    pause
    exit /b 1
  )
)

start "" "%PYW%" launcher.py
