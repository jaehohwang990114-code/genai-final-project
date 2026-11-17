"""화면 디자인만 담당 — SF(공상과학) HUD 테마. 기능 코드(app.py, agent.py)와 분리해 둔다.

구성: ① Gradio 기본 테마(어두운 색) ② CSS(네온·유리 패널·움직이는 격자 배경) ③ 헤더 HTML ④ 다크 모드 강제 JS
"""
import gradio as gr

# ① 기본 테마 — 글꼴과 기본 색. 세부 모양은 아래 CSS 가 덮어쓴다.
THEME = gr.themes.Base(
    primary_hue="cyan",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Noto Sans KR"), "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
)

# ④ 항상 어두운 화면으로 (Gradio 는 body 에 'dark' 클래스가 있으면 다크 모드)
FORCE_DARK_JS = "() => { document.body.classList.add('dark'); }"

HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&display=swap" rel="stylesheet">
"""

# ③ 헤더 — 제목, 부제, 기술 배지
HEADER_HTML = """
<div class="hud-header">
  <div class="hud-corner tl"></div><div class="hud-corner tr"></div>
  <div class="hud-corner bl"></div><div class="hud-corner br"></div>
  <div class="hud-kicker">// LOCAL AI AGENT · SYSTEM ONLINE</div>
  <h1 class="hud-title" data-text="ALBA·MONEY">ALBA·MONEY</h1>
  <div class="hud-sub">알바비 계산 <span>✦</span> 적금 상품 안내 <span>✦</span> 노동·금융 문서 검색</div>
  <div class="hud-chips">
    <span class="chip">RAG</span><span class="chip">TOOL CALLING</span>
    <span class="chip">LANGGRAPH · MULTI-AGENT</span><span class="chip">MCP SERVER</span>
    <span class="chip">OLLAMA · LOCAL LLM</span><span class="chip">PII GUARD</span>
  </div>
  <div class="hud-note">은행 상품은 시연용 <b>가상 데이터</b> · 법률·금융 자문이 아닌 정보 안내 · 개인정보는 입력하지 마세요</div>
</div>
"""


def status_html(ok, text):
    """서버 상태 표시줄 (초록 = 정상, 빨강 = 문제)"""
    cls = "ok" if ok else "bad"
    return f'<div class="hud-status {cls}"><span class="dot"></span>{text}</div>'


# ② CSS ─────────────────────────────────────────────────────────────
CSS = r"""
:root {
  --neon-cyan: #22e6ff;
  --neon-pink: #ff2bd6;
  --neon-violet: #8b5cff;
  --neon-green: #3dff9a;
  --ink: #e6f6ff;
  --ink-dim: #8aa4c2;
  --glass: rgba(10, 18, 40, 0.55);
  --glass-border: rgba(34, 230, 255, 0.28);
}

/* ── 우주 배경 + 움직이는 격자 바닥 + 별 ─────────────────────── */
body, gradio-app {
  background: #03040c !important;
}
body::before {                               /* 성운 빛 + 별 */
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background:
    radial-gradient(1px 1px at 12% 18%, #fff 50%, transparent 51%),
    radial-gradient(1px 1px at 72% 12%, #bff 50%, transparent 51%),
    radial-gradient(1.5px 1.5px at 42% 32%, #fff 50%, transparent 51%),
    radial-gradient(1px 1px at 86% 44%, #fdf 50%, transparent 51%),
    radial-gradient(1px 1px at 24% 58%, #fff 50%, transparent 51%),
    radial-gradient(1.5px 1.5px at 62% 70%, #bff 50%, transparent 51%),
    radial-gradient(1px 1px at 92% 82%, #fff 50%, transparent 51%),
    radial-gradient(1px 1px at 6% 88%, #fdf 50%, transparent 51%),
    radial-gradient(60% 50% at 15% 0%, rgba(139, 92, 255, 0.35), transparent 70%),
    radial-gradient(50% 45% at 100% 20%, rgba(255, 43, 214, 0.22), transparent 70%),
    radial-gradient(70% 60% at 50% 110%, rgba(34, 230, 255, 0.25), transparent 70%);
  animation: twinkle 6s ease-in-out infinite alternate;
}
body::after {                                /* 원근 격자 바닥 */
  content: ""; position: fixed; left: -50%; right: -50%; bottom: -10vh; height: 55vh;
  z-index: 0; pointer-events: none;
  background-image:
    linear-gradient(rgba(34, 230, 255, 0.35) 1px, transparent 1px),
    linear-gradient(90deg, rgba(34, 230, 255, 0.35) 1px, transparent 1px);
  background-size: 60px 60px;
  transform: perspective(500px) rotateX(62deg);
  transform-origin: center top;
  mask-image: linear-gradient(to top, rgba(0,0,0,0.9), transparent 85%);
  -webkit-mask-image: linear-gradient(to top, rgba(0,0,0,0.9), transparent 85%);
  animation: grid-run 4s linear infinite;
}
@keyframes grid-run { to { background-position: 0 60px, 0 0; } }
@keyframes twinkle { from { opacity: 0.75; } to { opacity: 1; } }

.gradio-container {
  position: relative; z-index: 1;
  background: transparent !important;
  max-width: 1280px !important;
  color: var(--ink);
}
/* 화면 전체에 옅은 주사선 */
.gradio-container::after {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 50;
  background: repeating-linear-gradient(to bottom, rgba(255,255,255,0.025) 0 1px, transparent 1px 3px);
}
footer { opacity: 0.35; }

/* ── 헤더 ───────────────────────────────────────────────────── */
.hud-header {
  position: relative; text-align: center; padding: 26px 16px 20px; margin-bottom: 4px;
  border: 1px solid var(--glass-border); border-radius: 18px;
  background:
    linear-gradient(120deg, rgba(34,230,255,0.10), rgba(139,92,255,0.10) 50%, rgba(255,43,214,0.10)),
    var(--glass);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 0 40px rgba(34,230,255,0.15), inset 0 0 30px rgba(139,92,255,0.12);
  overflow: hidden;
}
.hud-header::before {                       /* 위에서 아래로 훑는 스캔 빛 */
  content: ""; position: absolute; left: 0; right: 0; height: 40%; top: -40%;
  background: linear-gradient(to bottom, transparent, rgba(34,230,255,0.12), transparent);
  animation: scan 5s ease-in-out infinite;
}
@keyframes scan { 0% { top: -40%; } 60%, 100% { top: 110%; } }
.hud-corner { position: absolute; width: 18px; height: 18px; border: 2px solid var(--neon-cyan);
  filter: drop-shadow(0 0 6px var(--neon-cyan)); }
.hud-corner.tl { top: 8px; left: 8px; border-right: 0; border-bottom: 0; }
.hud-corner.tr { top: 8px; right: 8px; border-left: 0; border-bottom: 0; }
.hud-corner.bl { bottom: 8px; left: 8px; border-right: 0; border-top: 0; }
.hud-corner.br { bottom: 8px; right: 8px; border-left: 0; border-top: 0; }
.hud-kicker { font-family: 'Orbitron', sans-serif; font-size: 11px; letter-spacing: 0.35em;
  color: var(--neon-green); text-shadow: 0 0 8px var(--neon-green); }
.hud-title {
  position: relative; margin: 6px 0 4px !important;
  font-family: 'Orbitron', sans-serif !important; font-weight: 900 !important;
  font-size: clamp(34px, 7vw, 64px) !important; letter-spacing: 0.08em; line-height: 1.1 !important;
  background-image: linear-gradient(90deg, #22e6ff, #ffffff 35%, #ff2bd6 65%, #8b5cff) !important;
  background-size: 200% auto !important;
  -webkit-background-clip: text !important; background-clip: text !important; color: transparent !important;
  filter: drop-shadow(0 0 14px rgba(34,230,255,0.55)) drop-shadow(0 0 28px rgba(255,43,214,0.35));
  animation: shine 6s linear infinite, flicker 7s infinite;
}
@keyframes shine { to { background-position: 200% center; } }
@keyframes flicker { 0%, 92%, 100% { opacity: 1; } 93% { opacity: 0.55; } 94% { opacity: 1; } 96% { opacity: 0.7; } }
.hud-sub { color: var(--ink); font-size: 15px; letter-spacing: 0.04em; }
.hud-sub span { color: var(--neon-pink); text-shadow: 0 0 8px var(--neon-pink); margin: 0 6px; }
.hud-chips { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.chip { font-family: 'Orbitron', sans-serif; font-size: 10.5px; letter-spacing: 0.15em;
  padding: 5px 11px; border-radius: 999px; color: var(--neon-cyan);
  border: 1px solid rgba(34,230,255,0.5); background: rgba(34,230,255,0.08);
  box-shadow: 0 0 10px rgba(34,230,255,0.25); }
.hud-note { margin-top: 12px; font-size: 12px; color: var(--ink-dim); }
.hud-note b { color: var(--neon-pink); }

/* ── 상태 표시줄 ───────────────────────────────────────────── */
.hud-status { display: inline-flex; align-items: center; gap: 10px; font-family: 'JetBrains Mono', monospace;
  font-size: 12.5px; padding: 7px 14px; border-radius: 10px; color: var(--ink);
  border: 1px solid var(--glass-border); background: var(--glass); }
.hud-status .dot { width: 9px; height: 9px; border-radius: 50%; }
.hud-status.ok .dot { background: var(--neon-green); box-shadow: 0 0 10px var(--neon-green); animation: pulse 1.6s infinite; }
.hud-status.bad .dot { background: #ff4d6d; box-shadow: 0 0 10px #ff4d6d; animation: pulse 0.8s infinite; }
@keyframes pulse { 50% { transform: scale(1.5); opacity: 0.5; } }

/* ── 유리 패널 (채팅 / 로그) ───────────────────────────────── */
.hud-panel {
  position: relative; border-radius: 18px !important; padding: 12px !important;
  background: var(--glass) !important;
  border: 1px solid var(--glass-border) !important;
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 0 0 1px rgba(139,92,255,0.15), 0 0 36px rgba(34,230,255,0.12), inset 0 0 40px rgba(34,230,255,0.05);
}
.hud-panel-title { font-family: 'Orbitron', 'Noto Sans KR', sans-serif; font-size: 12px; letter-spacing: 0.22em;
  color: var(--neon-cyan); text-shadow: 0 0 8px var(--neon-cyan); padding: 2px 4px 8px; }
.hud-panel-title.pink { color: var(--neon-pink); text-shadow: 0 0 8px var(--neon-pink); }
.hud-panel .block, .hud-panel .form { background: transparent !important; border-color: transparent !important; box-shadow: none !important; }

/* 채팅창 */
#chat { background: rgba(3, 6, 18, 0.55) !important; border: 1px solid rgba(34,230,255,0.15) !important;
  border-radius: 14px !important; }
#chat [data-testid="user"], #chat .message.user {
  background: linear-gradient(135deg, rgba(255,43,214,0.35), rgba(139,92,255,0.35)) !important;
  border: 1px solid rgba(255,43,214,0.55) !important; color: #fff !important;
  box-shadow: 0 0 16px rgba(255,43,214,0.3) !important; border-radius: 14px 14px 4px 14px !important;
}
#chat [data-testid="bot"], #chat .message.bot {
  background: linear-gradient(135deg, rgba(34,230,255,0.12), rgba(10,18,40,0.6)) !important;
  border: 1px solid rgba(34,230,255,0.45) !important; color: var(--ink) !important;
  box-shadow: 0 0 16px rgba(34,230,255,0.18) !important; border-radius: 14px 14px 14px 4px !important;
}
#chat strong, #chat b { color: var(--neon-cyan); }

/* 입력창 */
#prompt textarea {
  background: rgba(3, 6, 18, 0.75) !important; color: var(--ink) !important;
  border: 1px solid rgba(34,230,255,0.4) !important; border-radius: 12px !important;
  font-size: 15px !important; transition: box-shadow .2s, border-color .2s;
}
#prompt textarea:focus { border-color: var(--neon-cyan) !important;
  box-shadow: 0 0 0 2px rgba(34,230,255,0.25), 0 0 22px rgba(34,230,255,0.45) !important; }
#prompt textarea::placeholder { color: #5f7894 !important; }

/* 버튼 — 네온 그라데이션 + 빛이 훑고 지나감 */
#send-btn, #clear-btn {
  position: relative; overflow: hidden; border-radius: 12px !important;
  font-family: 'Orbitron', 'Noto Sans KR', sans-serif !important; font-weight: 700 !important; letter-spacing: 0.12em;
  transition: transform .15s, box-shadow .2s;
}
#send-btn {
  background: linear-gradient(90deg, var(--neon-cyan), var(--neon-violet), var(--neon-pink)) !important;
  background-size: 200% auto !important; animation: shine 4s linear infinite;
  color: #050814 !important; border: none !important;
  box-shadow: 0 0 18px rgba(34,230,255,0.55), 0 0 36px rgba(255,43,214,0.3) !important;
}
#clear-btn { background: rgba(10,18,40,0.7) !important; color: var(--neon-pink) !important;
  border: 1px solid rgba(255,43,214,0.55) !important; box-shadow: 0 0 12px rgba(255,43,214,0.25) !important; }
#send-btn:hover, #clear-btn:hover { transform: translateY(-2px); }
/* 사람 확인 버튼 — LangGraph 가 확인을 기다릴 때만 나타난다 */
#confirm-btn {
  border-radius: 12px !important; font-family: 'Orbitron', 'Noto Sans KR', sans-serif !important; font-weight: 700 !important;
  letter-spacing: 0.1em; color: #031a0d !important; border: none !important;
  background: linear-gradient(90deg, #3dff9a, #22e6ff) !important;
  box-shadow: 0 0 20px rgba(61,255,154,0.6) !important; animation: pulse-glow 1.4s ease-in-out infinite;
}
@keyframes pulse-glow { 50% { box-shadow: 0 0 34px rgba(61,255,154,0.95), 0 0 60px rgba(34,230,255,0.4); } }
#send-btn::after {
  content: ""; position: absolute; top: 0; left: -60%; width: 40%; height: 100%;
  background: linear-gradient(100deg, transparent, rgba(255,255,255,0.7), transparent);
  animation: sweep 2.8s ease-in-out infinite;
}
@keyframes sweep { 0% { left: -60%; } 55%, 100% { left: 130%; } }

/* 예시 질문 칩 */
#examples { background: transparent !important; border: none !important; }
#examples > div, #examples .block { background: transparent !important; }
#examples button, #examples .gallery-item, #examples td {
  background: rgba(139,92,255,0.12) !important; color: var(--ink) !important;
  border: 1px solid rgba(139,92,255,0.45) !important; border-radius: 10px !important;
  transition: box-shadow .2s, border-color .2s;
}
#examples button:hover, #examples .gallery-item:hover, #examples td:hover {
  border-color: var(--neon-pink) !important; box-shadow: 0 0 14px rgba(255,43,214,0.45) !important; }
#examples .label, #examples span { color: var(--ink-dim) !important; }

/* 실행 로그 — 터미널 느낌 */
#syslog textarea {
  background: rgba(0, 8, 4, 0.78) !important; color: var(--neon-green) !important;
  font-family: 'JetBrains Mono', monospace !important; font-size: 12.5px !important; line-height: 1.55 !important;
  border: 1px solid rgba(61,255,154,0.35) !important; border-radius: 12px !important;
  text-shadow: 0 0 6px rgba(61,255,154,0.55);
  box-shadow: inset 0 0 24px rgba(61,255,154,0.08);
}

/* 라벨 숨김 (패널 제목을 따로 단다) */
#chat .label-wrap, #syslog label > span, #prompt label > span { display: none !important; }

/* 휴대폰 */
@media (max-width: 760px) {
  .hud-header { padding: 20px 12px 16px; }
  .hud-sub { font-size: 13px; }
  .hud-title { font-size: 30px !important; letter-spacing: 0.03em; }
  .hud-kicker { letter-spacing: 0.2em; }
  .hud-sub, .hud-note { word-break: keep-all; }
  .gradio-container { padding: 0 8px !important; }
}
/* 움직임 줄이기 설정을 켠 사용자는 애니메이션 끄기 */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""
