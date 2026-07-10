@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "ROOT=%~dp0"
set "BACKEND_START=8004"
set "BACKEND_MAX=8050"
set "FRONTEND_START=3010"
set "FRONTEND_MAX=3050"

echo.
echo  Spec Check - starting dev servers...
echo.

if not exist "%ROOT%backend\venv\Scripts\python.exe" (
    echo ERROR: Backend virtualenv not found at backend\venv
    echo Create it with:
    echo   cd backend
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
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

(
    echo NEXT_PUBLIC_API_BASE_URL=http://localhost:!BACKEND_PORT!/api/v1
    echo NEXT_PUBLIC_API_HEALTH_URL=http://localhost:!BACKEND_PORT!/api/health/
) > "%ROOT%frontend\.env.local"

set "EXTRA_CORS_ORIGINS=http://localhost:!FRONTEND_PORT!,http://127.0.0.1:!FRONTEND_PORT!"

echo.
echo Starting backend on http://127.0.0.1:!BACKEND_PORT!
start "Spec Check Backend" cmd /k "cd /d %ROOT%backend && call venv\Scripts\activate.bat && set EXTRA_CORS_ORIGINS=!EXTRA_CORS_ORIGINS! && python manage.py runserver 127.0.0.1:!BACKEND_PORT!"

timeout /t 2 /nobreak >nul

echo Starting frontend on http://localhost:!FRONTEND_PORT!
start "Spec Check Frontend" cmd /k "cd /d %ROOT%frontend && npx next dev -p !FRONTEND_PORT!"

echo.
echo  Spec Check is running
echo    App:     http://localhost:!FRONTEND_PORT!
echo    API:     http://localhost:!BACKEND_PORT!/api/v1
echo    Health:  http://localhost:!BACKEND_PORT!/api/health/
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
