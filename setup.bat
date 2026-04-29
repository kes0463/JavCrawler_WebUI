@echo off
echo ============================================================
echo      JAV Story Analyzer & Timeline UI - Windows Setup
echo ============================================================
echo.
echo [1/3] Checking for Python...
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH. Please install Python 3.10+.
    pause
    exit /b 1
)

echo [2/3] Creating Virtual Environment (venv)...
IF NOT EXIST "venv" (
    python -m venv venv
    echo Virtual environment created successfully.
) ELSE (
    echo Virtual environment already exists.
)

echo [3/3] Installing/Updating required packages...
call venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo ============================================================
echo Setup Complete!
echo You can now run the GUI using: start.bat
echo ============================================================
pause
