@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8765"

set "PY="
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if defined PY goto found
where python >nul 2>nul
if errorlevel 1 goto nopython
set "PY=python"

:found
"%PY%" -c "import docx" 2>nul
if errorlevel 1 goto nodocx

echo.
echo   Contract Reviewer starting at http://127.0.0.1:%PORT%
echo   Press Ctrl+C to stop.
echo.
"%PY%" main.py --port %PORT%
pause
exit /b 0

:nopython
echo.
echo   [ERROR] Python not found. Install Python 3.9+ and add it to PATH.
echo.
pause
exit /b 1

:nodocx
echo.
echo   [ERROR] python-docx is missing.
echo   Run this command first:
echo       "%PY%" -m pip install python-docx
echo.
pause
exit /b 1
