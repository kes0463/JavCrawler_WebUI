@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo      JAVSTORY WebUI - webapi + frontend
echo ============================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv not found. Run setup.bat first.
    pause
    exit /b 1
)

call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1

if not defined JAVSTORY_WEBAPI_PORT set JAVSTORY_WEBAPI_PORT=8765
if not defined JAVSTORY_VITE_PORT set JAVSTORY_VITE_PORT=5173

echo Stopping any process on port %JAVSTORY_WEBAPI_PORT% ...
:kill_port_loop
set "FOUND=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%JAVSTORY_WEBAPI_PORT% " ^| findstr LISTENING') do (
    set "FOUND=1"
    taskkill /F /PID %%a >nul 2>&1
)
if "%FOUND%"=="1" (
    timeout /t 1 /nobreak >nul
    goto kill_port_loop
)
timeout /t 1 /nobreak >nul

echo Stopping any process on port %JAVSTORY_VITE_PORT% (Vite) ...
:kill_vite_loop
set "VITE_FOUND=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%JAVSTORY_VITE_PORT% " ^| findstr LISTENING') do (
    set "VITE_FOUND=1"
    taskkill /F /PID %%a >nul 2>&1
)
if "%VITE_FOUND%"=="1" (
    timeout /t 1 /nobreak >nul
    goto kill_vite_loop
)
timeout /t 1 /nobreak >nul

echo Starting webapi on port %JAVSTORY_WEBAPI_PORT% ...
if /I "%JAVSTORY_WEBAPI_RELOAD%"=="1" (
  start "JAVSTORY webapi" /MIN /D "%~dp0." "%~dp0venv\Scripts\python.exe" -m uvicorn webapi.main:app --host 127.0.0.1 --port %JAVSTORY_WEBAPI_PORT% --reload
) else (
  start "JAVSTORY webapi" /MIN /D "%~dp0." "%~dp0venv\Scripts\python.exe" -m uvicorn webapi.main:app --host 127.0.0.1 --port %JAVSTORY_WEBAPI_PORT%
)

timeout /t 3 /nobreak >nul
"%~dp0venv\Scripts\python.exe" -c "import json,urllib.request,sys; s=json.load(urllib.request.urlopen('http://127.0.0.1:%JAVSTORY_WEBAPI_PORT%/api/status')); n=s.get('actress_count'); p=s.get('library_patch'); print('[OK] webapi ready — actresses:', n if n is not None else 'MISSING (wrong project?)', '| library_patch:', p); sys.exit(0 if n is not None and p else 1)"
if errorlevel 1 (
    echo [ERROR] webapi on port %JAVSTORY_WEBAPI_PORT% is missing actress API or library PATCH.
    echo         Close all python/uvicorn windows, then run this script again from JAVSTORY_WebUI.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo Installing frontend dependencies...
    pushd frontend
    call npm install
    popd
)

echo Starting Electron WebUI (Vite + Electron)...
pushd frontend
call npm run electron:dev
popd

pause
