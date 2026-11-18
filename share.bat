@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
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
rem    앱 출력은 logs\share_app.log 에 남긴다 → 앱이 꺼지면 원인을 볼 수 있게
if not exist logs mkdir logs
echo ===== %DATE% %TIME% 공유 시작 ===== >> logs\share_app.log
start "알바머니 앱 (공유 끝나면 닫기)" /min cmd /c ""%CD%\.venv\Scripts\python.exe" app.py %LOCK% >> logs\share_app.log 2>&1"

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
rem ── 앱이 실제로 응답할 때까지 기다린 뒤에 공개 주소를 만든다 ──
rem    (모델을 GPU 에 올리는 동안 주소부터 열면 Cloudflare 502 '호스트 오류'가 뜸)
echo 앱 준비 중... (모델을 GPU 에 올리는 중, 보통 20~60초)
set /a WAIT=0
:wait_app
curl -s -o nul http://127.0.0.1:7870 && goto app_ready
set /a WAIT+=2
if %WAIT% GEQ 180 (
    echo [오류] 3분이 지나도 앱이 켜지지 않았어요. logs\share_app.log 의 오류 메시지를 확인하세요.
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait_app
:app_ready
echo 앱 준비 완료 (%WAIT%초). 공개 주소를 만듭니다 — 아래 https://....trycloudflare.com 이 나오면 바로 접속하세요.
echo.
rem localhost 는 IPv6(::1) 로 먼저 접속하다 거부될 수 있어 127.0.0.1 로 고정
rem QUIC 방식은 실시간 진행 표시(SSE)를 모아서 보내는 경우가 있어 http2 로 고정
"%CF%" tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:7870
pause
