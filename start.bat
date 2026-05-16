@echo off
setlocal
REM Run from repo root (works when started as Administrator too)
cd /d "%~dp0"

echo ============================================================
echo      Starting JAV Story Analyzer GUI
echo ============================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found: %~dp0venv
    echo.
    echo Run setup.bat once from this folder, then start.bat again.
    echo   setup.bat
    echo.
    pause
    exit /b 1
)

call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate venv.
    pause
    exit /b 1
)

python "%~dp0main.py"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
    echo.
    echo [ERROR] main.py exited with code %EXITCODE%
)
pause
exit /b %EXITCODE%
