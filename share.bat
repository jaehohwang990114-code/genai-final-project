@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title 알바머니 도우미 - 인터넷 공유 중 (이 창을 닫으면 공개 주소가 꺼집니다)

if not exist ".venv\Scripts\python.exe" (
    echo 먼저 setup.bat 을 실행해 주세요.
    pause
    exit /b 1
)

rem ── Cloudflare 터널 프로그램 확인 (계정 없이 임시 공개 주소를 만들어 줌) ──
set "CF=cloudflared"
where cloudflared >nul 2>&1 || set "CF=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
"%CF%" --version >nul 2>&1 || (
    echo [오류] cloudflared 가 없습니다. 아래 명령으로 설치한 뒤 다시 실행하세요.
    echo        winget install --id Cloudflare.cloudflared
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

if "%CHAT_MODEL%"=="" set CHAT_MODEL=alba-agent

rem ── 실행할 때마다 새 비밀번호 ──
set APP_PASSWORD=alba%RANDOM%%RANDOM%
rem run.bat(7860) 과 겹치지 않게 공유용 앱은 7870 포트로
set GRADIO_SERVER_PORT=7870

rem ── 앱은 작은 창에서 비밀번호 잠금으로 실행 (그 창도 이 창과 함께 닫아 주세요) ──
start "알바머니 앱 (공유 끝나면 닫기)" /min ".venv\Scripts\python.exe" app.py --lock

echo.
echo ============================================================
echo   접속 아이디: alba     비밀번호: %APP_PASSWORD%
echo   잠시 후 아래에 https://....trycloudflare.com 주소가 나옵니다.
echo   그 주소를 휴대폰이나 다른 컴퓨터에서 열고 위 아이디/비밀번호로 로그인하세요.
echo   주소와 비밀번호를 아는 사람은 이 PC 의 GPU 로 질문할 수 있어요.
echo   다 쓰면 이 창과 작은 앱 창을 모두 닫으세요.
echo ============================================================
echo.
timeout /t 15 /nobreak >nul
"%CF%" tunnel --no-autoupdate --url http://localhost:7870
pause
