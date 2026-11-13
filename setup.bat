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

REM --index-url 필수: 지정 안 하면 pip가 CPU 전용 torch를 조용히 설치할 수 있음
REM (torch.cuda.is_available()==False, 에러 없이 STT가 CPU로만 돎). RTX 50시리즈
REM (Blackwell)는 cu124 이하로는 동작 안 함 — 반드시 cu128 이상 인덱스 사용.
pip install -r "%~dp0requirements-torch.txt" --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 (
    echo [ERROR] pip install -r requirements-torch.txt failed.
    echo See INSTALL.md for CPU-only PyTorch install.
    pause
    exit /b 1
)

REM Harvest 브라우저 단계(Scrapling StealthyFetcher)용 Chromium. 실패해도 HTTP 수집은 동작하므로 경고만.
python -m patchright install chromium
if errorlevel 1 (
    echo [WARN] patchright chromium install failed. Harvest browser fallback will be unavailable.
)

echo.
echo ============================================================
echo Setup complete. Run: start.bat
echo ============================================================
pause
exit /b 0
