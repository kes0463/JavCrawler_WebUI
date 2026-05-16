@echo off
setlocal
cd /d "%~dp0.."
set MODEL=%JAVSTORY_OLLAMA_MODEL%
if "%MODEL%"=="" set MODEL=javstory-ko-av
set FILE=config\ollama\Modelfile
if not exist "%FILE%" (
  echo [ERROR] Modelfile not found: %FILE%
  exit /b 1
)
echo Creating Ollama model "%MODEL%" from %FILE% ...
ollama create %MODEL% -f %FILE%
if errorlevel 1 (
  echo [ERROR] ollama create failed. Is Ollama running?
  exit /b 1
)
echo Done. Use model name "%MODEL%" in JAVSTORY Settings ^(Ollama^).
exit /b 0
