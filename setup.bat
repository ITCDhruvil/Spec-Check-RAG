@echo off
setlocal
cd /d "%~dp0"

echo.
echo  Spec Check - one-time project setup
echo.

where powershell >nul 2>&1
if errorlevel 1 (
    echo ERROR: PowerShell is required to run setup.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Setup failed with exit code %EXIT_CODE%.
    pause
    exit /b %EXIT_CODE%
)

echo.
pause
exit /b 0
