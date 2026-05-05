@echo off
:: Ensure the script runs in its own directory, especially when run as Administrator
cd /d "%~dp0"

echo ============================================================
echo      Starting JAV Story Analyzer GUI
echo ============================================================

IF NOT EXIST "venv" (
    echo [ERROR] Virtual environment 'venv' not found!
    echo Please run setup.bat first.
    pause
    exit /b 1
)

:: Activate venv and run GUI v2
call venv\Scripts\activate.bat
python main.py
pause
