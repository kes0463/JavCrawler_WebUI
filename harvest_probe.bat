@echo off
setlocal
REM Harvest probe: enter a product code to see what each site returns.
REM   harvest_probe.bat                 interactive
REM   harvest_probe.bat SNOS-334 --full args + merged harvest result
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"

set "PY=%~dp0venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0..\JavCrawler_WebUI\venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] venv not found. Run setup.bat first.
    pause
    exit /b 1
)

"%PY%" "%~dp0scripts\harvest_probe.py" %*
if "%~1"=="" pause
