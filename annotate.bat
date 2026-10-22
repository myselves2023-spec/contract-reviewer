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
"%PY%" tools\annotate.py %*
set "CODE=%ERRORLEVEL%"
echo.
pause
exit /b %CODE%

:nopython
echo.
echo   [ERROR] Python not found.
echo.
pause
exit /b 1
