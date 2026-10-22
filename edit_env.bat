@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".env" goto noenv
notepad ".env"
exit /b 0

:noenv
echo.
echo   [ERROR] .env not found in this folder.
echo.
pause
exit /b 1
