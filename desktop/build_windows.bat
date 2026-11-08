@echo off
setlocal
cd /d "%~dp0"

set "PY=..\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Virtual environment not found: %PY%
  echo Create it first in the repo root with: py -3 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)

"%PY%" -m pip install pyinstaller || exit /b 1
"%PY%" -m pip install -r requirements_desktop.txt || exit /b 1
"%PY%" -m PyInstaller --noconfirm --clean resumeyar.spec || exit /b 1

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 not found. Portable build is ready in dist\Resumeyar
  exit /b 0
)

"%ISCC%" installer.iss || exit /b 1

echo.
echo Build finished.
echo   Portable: dist\Resumeyar\Resumeyar.exe
echo   Installer: installer\Resumeyar-Setup-1.0.0.exe
