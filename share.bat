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

rem run.bat(7860) 과 겹치지 않게 공유용 앱은 7870 포트로
set GRADIO_SERVER_PORT=7870

rem ── 기본: 로그인 없이 공유 / "share.bat lock" 으로 실행하면 비밀번호 잠금 ──
set "LOCK="
if /i "%~1"=="lock" (
    set "LOCK=--lock"
    set "APP_PASSWORD=alba%RANDOM%%RANDOM%"
)

rem ── 앱은 작은 창에서 실행 (그 창도 이 창과 함께 닫아 주세요) ──
start "알바머니 앱 (공유 끝나면 닫기)" /min ".venv\Scripts\python.exe" app.py %LOCK%

echo.
echo ============================================================
if defined LOCK (
    echo   접속 아이디: alba     비밀번호: %APP_PASSWORD%
) else (
    echo   로그인 없이 열립니다. 주소를 아는 사람은 누구나 쓸 수 있어요.
    echo   비밀번호를 걸려면 이 창을 닫고 "share.bat lock" 으로 실행하세요.
)
echo   잠시 후 아래에 https://....trycloudflare.com 주소가 나옵니다.
echo   주소는 믿을 수 있는 사람에게만 보내세요. 질문하면 이 PC 의 GPU 를 씁니다.
echo   다 쓰면 이 창과 작은 앱 창을 모두 닫으세요.
echo ============================================================
echo.
timeout /t 15 /nobreak >nul
"%CF%" tunnel --no-autoupdate --url http://localhost:7870
pause
