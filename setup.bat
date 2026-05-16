@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo      JAV Story Analyzer - Windows Setup
echo ============================================================
echo.

echo [1/3] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Install Python 3.10+ and enable "Add to PATH", then retry.
    pause
    exit /b 1
)
python --version

echo.
echo [2/3] Creating virtual environment...
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] python -m venv failed.
        pause
        exit /b 1
    )
    echo venv created.
) else (
    echo venv already exists.
)

echo.
echo [3/3] Installing packages...
call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate venv.
    pause
    exit /b 1
)

python -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] pip upgrade failed.
    pause
    exit /b 1
)

pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install -r requirements.txt failed.
    pause
    exit /b 1
)

pip install -r "%~dp0requirements-torch.txt"
if errorlevel 1 (
    echo [ERROR] pip install -r requirements-torch.txt failed.
    echo See INSTALL.md for CPU-only PyTorch install.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Setup complete. Run: start.bat
echo ============================================================
pause
exit /b 0
