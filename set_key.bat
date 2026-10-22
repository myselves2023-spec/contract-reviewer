@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

set "PY="
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if defined PY goto found
where python >nul 2>nul
if errorlevel 1 goto nopython
set "PY=python"

:found
echo.
echo   ============================================================
echo     Step 1 / 2 : Save your API key
echo   ============================================================
"%PY%" tools\set_key.py
if errorlevel 1 goto failed

echo.
echo   ============================================================
echo     Step 2 / 2 : Test the connection
echo   ============================================================
"%PY%" tools\check_key.py
set "CODE=%ERRORLEVEL%"
echo.
pause
exit /b %CODE%

:failed
echo.
echo   Key was not saved. Nothing changed.
echo.
pause
exit /b 1

:nopython
echo.
echo   [ERROR] Python not found.
echo.
pause
exit /b 1
