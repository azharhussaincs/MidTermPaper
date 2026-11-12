@echo off
rem MindBridge Intake AI - stop the servers started by start.bat.
rem
rem Closes the "MindBridge-Backend" / "MindBridge-Frontend" windows with their child processes,
rem then stops any leftover uvicorn/vite/esbuild process whose command line points into THIS
rem project directory. Servers of other projects are never touched.

setlocal EnableExtensions

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "RUN_DIR=%ROOT%\.run"

for %%W in (MindBridge-Backend MindBridge-Frontend) do (
    tasklist /V /FI "WINDOWTITLE eq %%W*" 2>nul | find /I "%%W" >nul
    if not errorlevel 1 (
        taskkill /FI "WINDOWTITLE eq %%W*" /T /F >nul 2>&1
        echo  Stopped %%W window
    ) else (
        echo  %%W window was not open
    )
)

rem Leftovers matched by project path (also covers Windows Terminal, where window titles
rem are not visible to tasklist/taskkill).
set "MB_ROOT=%ROOT%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = $env:MB_ROOT;" ^
  "$pattern = 'uvicorn(\.exe)?\W+app\.main:app|node_modules\\vite\\bin\\vite\.js|node_modules\\\.bin\\vite|@esbuild|esbuild\.exe';" ^
  "$procs = @(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.Contains($root) -and $_.CommandLine -match $pattern });" ^
  "foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; Write-Output (' Stopped leftover ' + $p.Name + ' (pid ' + $p.ProcessId + ')') }"

if exist "%RUN_DIR%\ports.env" del /Q "%RUN_DIR%\ports.env"
echo  MindBridge stopped.
exit /b 0
