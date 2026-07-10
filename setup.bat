@echo off
setlocal
cd /d "%~dp0"

echo.
if /I "%~1"=="server" (
    echo  Spec Check - SERVER setup ^(192.168.10.38:7004^)
) else if /I "%~1"=="help" (
    goto ShowHelp
) else if /I "%~1"=="/?" (
    goto ShowHelp
) else (
    echo  Spec Check - LOCAL project setup
)
echo.

where powershell >nul 2>&1
if errorlevel 1 (
    echo ERROR: PowerShell is required to run setup.
    pause
    exit /b 1
)

set "SETUP_ARGS="
if /I "%~1"=="server" (
    set "SETUP_ARGS=-Server"
    shift
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %SETUP_ARGS% %*
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

:ShowHelp
echo.
echo Spec Check — project setup
echo.
echo   setup.bat          Local setup ^(this folder, ports 8004 / 3010^)
echo   setup.bat server   Server setup at C:\AI_Code\Spec_Check_RAG_V1_7004\Spec-Check-RAG
echo                      App URL: http://192.168.10.38:7004
echo.
echo Options passed through to setup.ps1, e.g.:
echo   setup.bat -AdminPassword "YourPass123"
echo   setup.bat server -AdminPassword "YourPass123"
echo.
pause
exit /b 0
