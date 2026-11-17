@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title 알바머니 도우미 - 처음 설치

rem ── Ollama 위치 찾기 (PATH 에 없으면 기본 설치 경로) ──
set "OLLAMA=ollama"
where ollama >nul 2>&1 || set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
"%OLLAMA%" --version >nul 2>&1 || (
    echo [오류] Ollama 가 설치되어 있지 않습니다. https://ollama.com 에서 설치한 뒤 다시 실행하세요.
    goto :fail
)
"%OLLAMA%" list >nul 2>&1 || (
    echo Ollama 서버를 켜는 중...
    start "" /min "%OLLAMA%" serve
    timeout /t 5 /nobreak >nul
)

echo.
echo [1/5] 파이썬 가상환경(.venv) 만들기
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv || goto :fail
)

echo [2/5] 패키지 설치 (gradio, langchain-core, numpy, requests)
".venv\Scripts\python.exe" -m pip install -q --upgrade pip || goto :fail
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :fail

echo [3/5] 모델 받기 - 처음 한 번만, 약 10GB
"%OLLAMA%" pull qwen3:14b || goto :fail
"%OLLAMA%" pull bge-m3 || goto :fail

echo [4/5] 전용 모델 alba-agent 만들기 (ollama\Modelfile)
"%OLLAMA%" create alba-agent -f ollama\Modelfile || goto :fail

echo [5/5] 오프라인 테스트
".venv\Scripts\python.exe" tests\test_offline.py || goto :fail
".venv\Scripts\python.exe" tests\test_graph_offline.py || goto :fail

echo.
echo ===== 설치 완료! 이제 run.bat 을 더블클릭하세요 =====
pause
exit /b 0

:fail
echo.
echo ===== 설치 중 오류가 났습니다. 위 메시지를 확인하세요 =====
pause
exit /b 1
