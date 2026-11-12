@echo off
rem MindBridge Intake AI - start backend (FastAPI) + frontend (Vite) on Windows.
rem
rem   start.bat                        defaults: backend 8000, frontend 5173 (8010 / 5174+ if busy)
rem   set BACKEND_PORT=9000 & start.bat
rem
rem First run creates backend\.venv, installs requirements, runs npm install and creates
rem backend\.env from .env.example. Each server runs in its own titled window. Stop with stop.bat.

setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "RUN_DIR=%ROOT%\.run"
set "VENV=%BACKEND%\.venv"
if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"

rem ---------------------------------------------------------------------------
rem Already running?
rem ---------------------------------------------------------------------------
tasklist /V /FI "WINDOWTITLE eq MindBridge-Backend*" 2>nul | find /I "MindBridge-Backend" >nul
if not errorlevel 1 (
    echo MindBridge is already running. Run stop.bat first to restart.
    if exist "%RUN_DIR%\ports.env" type "%RUN_DIR%\ports.env"
    exit /b 0
)

rem ---------------------------------------------------------------------------
rem Prerequisites
rem ---------------------------------------------------------------------------
where node >nul 2>&1 || (echo [ERROR] Node.js 20+ is required: https://nodejs.org & exit /b 1)
where npm >nul 2>&1 || (echo [ERROR] npm is required ^(ships with Node.js^). & exit /b 1)

if not exist "%VENV%\Scripts\python.exe" (
    set "PY="
    for %%V in (3.13 3.12 3.11) do (
        if not defined PY (
            py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
        )
    )
    if not defined PY (
        python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1 && set "PY=python"
    )
    if not defined PY (
        echo [ERROR] Python 3.11+ is required: https://www.python.org/downloads/
        exit /b 1
    )
    echo ^> Creating backend virtual environment with !PY!
    !PY! -m venv "%VENV%" || exit /b 1
)

rem Reinstall requirements on first run or whenever requirements.txt changes.
set "REQ_HASH="
for /f "delims=" %%H in ('certutil -hashfile "%BACKEND%\requirements.txt" SHA256 ^| findstr /v ":"') do (
    if not defined REQ_HASH set "REQ_HASH=%%H"
)
set "REQ_HASH=%REQ_HASH: =%"
set "OLD_HASH="
if exist "%VENV%\.requirements.sha256" set /p OLD_HASH=<"%VENV%\.requirements.sha256"
if not "%OLD_HASH%"=="%REQ_HASH%" (
    echo ^> Installing backend requirements ^(first run or requirements.txt changed^)...
    "%VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pip || exit /b 1
    "%VENV%\Scripts\python.exe" -m pip install --quiet -r "%BACKEND%\requirements.txt" || exit /b 1
    >"%VENV%\.requirements.sha256" echo %REQ_HASH%
)

if not exist "%FRONTEND%\node_modules" (
    echo ^> Installing frontend dependencies ^(npm install^)...
    pushd "%FRONTEND%"
    call npm install --no-audit --no-fund --loglevel=error
    if errorlevel 1 (popd & exit /b 1)
    popd
)

if not exist "%BACKEND%\.env" (
    copy /Y "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
    echo [!] Created backend\.env from .env.example. Add GEMINI_API_KEY there ^(or use local Ollama^).
)

rem ---------------------------------------------------------------------------
rem Ports (never take over a port another app is using)
rem ---------------------------------------------------------------------------
if not defined BACKEND_PORT set "BACKEND_PORT=8000"
if not defined FRONTEND_PORT set "FRONTEND_PORT=5173"
set "WANT_BACKEND=%BACKEND_PORT%"
set "WANT_FRONTEND=%FRONTEND_PORT%"
call :pick_port %WANT_BACKEND% 8010 BACKEND_PORT || (echo [ERROR] No free backend port found. & exit /b 1)
call :pick_port %WANT_FRONTEND% 5174 FRONTEND_PORT || (echo [ERROR] No free frontend port found. & exit /b 1)
if not "%BACKEND_PORT%"=="%WANT_BACKEND%" echo [!] Port %WANT_BACKEND% is busy; backend will use %BACKEND_PORT%.
if not "%FRONTEND_PORT%"=="%WANT_FRONTEND%" echo [!] Port %WANT_FRONTEND% is busy; frontend will use %FRONTEND_PORT%.

set "BACKEND_URL=http://localhost:%BACKEND_PORT%"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"
rem Inherited by the server windows started below.
set "CORS_ORIGINS=%FRONTEND_URL%,http://127.0.0.1:%FRONTEND_PORT%"
set "VITE_API_BASE_URL=%BACKEND_URL%"
(
    echo BACKEND_PORT=%BACKEND_PORT%
    echo FRONTEND_PORT=%FRONTEND_PORT%
) >"%RUN_DIR%\ports.env"

rem ---------------------------------------------------------------------------
rem Launch (absolute paths, so stop.bat can recognise exactly these processes)
rem ---------------------------------------------------------------------------
echo ^> Starting backend on %BACKEND_URL%
start "MindBridge-Backend" /D "%BACKEND%" cmd /k ""%VENV%\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port %BACKEND_PORT%"

echo ^> Starting frontend on %FRONTEND_URL%
start "MindBridge-Frontend" /D "%FRONTEND%" cmd /k ""%FRONTEND%\node_modules\.bin\vite.cmd" --port %FRONTEND_PORT% --strictPort"

call :wait_for "Backend" "http://127.0.0.1:%BACKEND_PORT%/api/system/health" || goto :startup_failed
call :wait_for "Frontend" "http://localhost:%FRONTEND_PORT%/" || goto :startup_failed

echo.
echo  MindBridge Intake AI is running
echo.
echo    Frontend UI     %FRONTEND_URL%
echo    API (Swagger)   %BACKEND_URL%/docs
echo    Health          %BACKEND_URL%/api/system/health
echo.
echo    Server output is in the "MindBridge-Backend" and "MindBridge-Frontend" windows.
echo    Stop: stop.bat
findstr /R /C:"^GEMINI_API_KEY=your-gemini-api-key-here" /C:"^GEMINI_API_KEY= *$" "%BACKEND%\.env" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo  [!] No GEMINI_API_KEY in backend\.env: chat needs it, or a working local Ollama model.
)
exit /b 0

:startup_failed
echo [ERROR] Startup failed; check the server windows for details. Stopping...
call "%ROOT%\stop.bat" >nul 2>&1
exit /b 1

rem ---------------------------------------------------------------------------
rem Subroutines
rem ---------------------------------------------------------------------------

:port_free
rem errorlevel 0 if nothing LISTENS on TCP port %1 (IPv4 or IPv6).
rem A listening socket is a row whose local address ends in ":<port>" and whose foreign address
rem ends in ":0". Matching on that (not the word "LISTENING") works in every Windows language.
for /f "tokens=2,3" %%A in ('netstat -ano') do (
    set "_local=%%A#"
    set "_foreign=%%B#"
    if not "!_local::%~1#=!"=="!_local!" if not "!_foreign::0#=!"=="!_foreign!" exit /b 1
)
exit /b 0

:pick_port
rem %1 preferred, %2 first fallback, %3 output variable. Tries %2..%2+20 if %1 is busy.
call :port_free %~1 && (set "%~3=%~1" & exit /b 0)
set /a _cand=%~2
set /a _last=%~2+20
:pick_loop
if !_cand! GTR !_last! exit /b 1
if not "!_cand!"=="%~1" (
    call :port_free !_cand! && (set "%~3=!_cand!" & exit /b 0)
)
set /a _cand+=1
goto :pick_loop

:http_ok
where curl.exe >nul 2>&1
if not errorlevel 1 (
    curl.exe -fsS -o nul --max-time 2 "%~1" >nul 2>&1
    exit /b !errorlevel!
)
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%~1' | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
exit /b %errorlevel%

:wait_for
rem %1 name, %2 url. Waits up to 90 s.
set /a _waited=0
:wait_loop
call :http_ok "%~2" && (echo   %~1 is healthy & exit /b 0)
if !_waited! GEQ 90 (
    echo [ERROR] %~1 did not become healthy within 90s.
    exit /b 1
)
rem ping as a 1 s sleep: unlike "timeout", it works when input is redirected.
ping -n 2 127.0.0.1 >nul
set /a _waited+=1
goto :wait_loop
