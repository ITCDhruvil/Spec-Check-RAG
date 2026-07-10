@echo off
setlocal EnableDelayedExpansion

rem ── Server deployment (run on 192.168.10.38) ───────────────────────────────
set "SERVER_ROOT=C:\AI_Code\Spec_Check_RAG_V1_7004\Spec-Check-RAG"
set "SERVER_HOST=192.168.10.38"
set "SERVER_FRONTEND_PORT=7004"
set "SERVER_BACKEND_PORT=7005"

if /I "%~1"=="server" goto ServerStart
if /I "%~1"=="help" goto ShowHelp
if /I "%~1"=="/?" goto ShowHelp

rem ── Local development (default) ────────────────────────────────────────────
cd /d "%~dp0"
set "ROOT=%~dp0"
set "BIND_HOST=127.0.0.1"
set "BACKEND_START=8004"
set "BACKEND_MAX=8050"
set "FRONTEND_START=3010"
set "FRONTEND_MAX=3050"
set "PUBLIC_HOST=localhost"
goto StartCommon

:ServerStart
if not exist "%SERVER_ROOT%\backend\" (
    echo.
    echo ERROR: Server project path not found:
    echo   %SERVER_ROOT%
    echo.
    echo Copy or clone the project to that path on the server, then run:
    echo   setup.bat server
    echo   start.bat server
    echo.
    pause
    exit /b 1
)
cd /d "%SERVER_ROOT%"
set "ROOT=%SERVER_ROOT%\"
set "BIND_HOST=0.0.0.0"
set "BACKEND_PORT=%SERVER_BACKEND_PORT%"
set "FRONTEND_PORT=%SERVER_FRONTEND_PORT%"
set "PUBLIC_HOST=%SERVER_HOST%"
set "USE_FIXED_PORTS=1"
goto StartCommon

:ShowHelp
echo.
echo Spec Check — start servers
echo.
echo   start.bat          Local dev (ports 8004 / 3010, localhost only)
echo   start.bat server   Server mode at %SERVER_HOST%:%SERVER_FRONTEND_PORT%
echo.
echo Server project path: %SERVER_ROOT%
echo.
pause
exit /b 0

:StartCommon
echo.
if defined USE_FIXED_PORTS (
    echo  Spec Check - starting SERVER on %PUBLIC_HOST%...
) else (
    echo  Spec Check - starting LOCAL dev servers...
)
echo.

if not exist "%ROOT%backend\venv\Scripts\python.exe" (
    echo ERROR: Backend virtualenv not found at backend\venv
    echo Run setup first:
    if defined USE_FIXED_PORTS (
        echo   setup.bat server
    ) else (
        echo   setup.bat
    )
    pause
    exit /b 1
)

if not exist "%ROOT%frontend\node_modules" (
    echo Frontend dependencies not found. Running npm install...
    pushd "%ROOT%frontend"
    call npm install
    if errorlevel 1 (
        echo ERROR: npm install failed.
        popd
        pause
        exit /b 1
    )
    popd
)

if not defined USE_FIXED_PORTS (
    call :FindFreePort %BACKEND_START% %BACKEND_MAX% BACKEND_PORT
    if errorlevel 1 (
        echo ERROR: Could not find a free backend port between %BACKEND_START% and %BACKEND_MAX%.
        pause
        exit /b 1
    )

    call :FindFreePort %FRONTEND_START% %FRONTEND_MAX% FRONTEND_PORT
    if errorlevel 1 (
        echo ERROR: Could not find a free frontend port between %FRONTEND_START% and %FRONTEND_MAX%.
        pause
        exit /b 1
    )

    if not "!BACKEND_PORT!"=="%BACKEND_START%" (
        echo Backend port %BACKEND_START% is busy - using !BACKEND_PORT! instead.
    )
    if not "!FRONTEND_PORT!"=="%FRONTEND_START%" (
        echo Frontend port %FRONTEND_START% is busy - using !FRONTEND_PORT! instead.
    )
)

(
    echo NEXT_PUBLIC_API_BASE_URL=http://%PUBLIC_HOST%:!BACKEND_PORT!/api/v1
    echo NEXT_PUBLIC_API_HEALTH_URL=http://%PUBLIC_HOST%:!BACKEND_PORT!/api/health/
) > "%ROOT%frontend\.env.local"

set "EXTRA_CORS_ORIGINS=http://%PUBLIC_HOST%:!FRONTEND_PORT!,http://127.0.0.1:!FRONTEND_PORT!,http://localhost:!FRONTEND_PORT!"

echo.
echo Starting backend on http://%BIND_HOST%:!BACKEND_PORT!
start "Spec Check Backend" cmd /k "cd /d %ROOT%backend && call venv\Scripts\activate.bat && set EXTRA_CORS_ORIGINS=!EXTRA_CORS_ORIGINS! && python manage.py runserver %BIND_HOST%:!BACKEND_PORT!"

timeout /t 2 /nobreak >nul

echo Starting frontend on http://%BIND_HOST%:!FRONTEND_PORT!
if defined USE_FIXED_PORTS (
    start "Spec Check Frontend" cmd /k "cd /d %ROOT%frontend && npx next dev -H 0.0.0.0 -p !FRONTEND_PORT!"
) else (
    start "Spec Check Frontend" cmd /k "cd /d %ROOT%frontend && npx next dev -p !FRONTEND_PORT!"
)

echo.
echo  Spec Check is running
echo    App:     http://%PUBLIC_HOST%:!FRONTEND_PORT!
echo    API:     http://%PUBLIC_HOST%:!BACKEND_PORT!/api/v1
echo    Health:  http://%PUBLIC_HOST%:!BACKEND_PORT!/api/health/
if defined USE_FIXED_PORTS (
    echo.
    echo  Server mode — accessible on LAN at %SERVER_HOST%:!FRONTEND_PORT!
    echo  Project path: %SERVER_ROOT%
)
echo.
echo Close the Backend and Frontend terminal windows to stop.
echo.
pause
exit /b 0

:FindFreePort
set "PORT_SCAN=%~1"
set "PORT_LIMIT=%~2"
set "%~3="

:FindFreePortLoop
netstat -ano | findstr /R /C:":!PORT_SCAN! .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    set /a PORT_SCAN+=1
    if !PORT_SCAN! GTR %PORT_LIMIT% exit /b 1
    goto FindFreePortLoop
)

set "%~3=!PORT_SCAN!"
exit /b 0
