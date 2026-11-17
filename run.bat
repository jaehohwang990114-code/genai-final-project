@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title 알바머니 도우미 - 실행 중 (끄려면 이 창을 닫으세요)

if not exist ".venv\Scripts\python.exe" (
    echo 먼저 setup.bat 을 실행해 주세요.
    pause
    exit /b 1
)

set "OLLAMA=ollama"
where ollama >nul 2>&1 || set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
"%OLLAMA%" list >nul 2>&1 || (
    echo Ollama 서버를 켜는 중...
    start "" /min "%OLLAMA%" serve
    timeout /t 5 /nobreak >nul
)

rem 다른 모델로 바꾸려면: set CHAT_MODEL=qwen2.5:7b
if "%CHAT_MODEL%"=="" set CHAT_MODEL=alba-agent
echo 모델: %CHAT_MODEL%  /  주소: http://localhost:7860
echo 모델을 GPU 에 올리는 중이라 첫 화면까지 20초쯤 걸릴 수 있어요.
".venv\Scripts\python.exe" app.py --open
pause
