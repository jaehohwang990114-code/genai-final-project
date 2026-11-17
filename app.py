"""Gradio 웹 데모 — 왼쪽 상담, 오른쪽 실행 로그 (어떤 도구를 불렀는지 시연 때 보여 주기).

실행: python app.py            → http://localhost:7860
      python app.py --lock     → 비밀번호 잠금만 (share.bat 이 Cloudflare 터널로 인터넷에 공개)
      python app.py --share    → Gradio 공개 주소(*.gradio.live) + 비밀번호 잠금 (리눅스 서버용.
                                 Windows 스마트 앱 컨트롤이 켜져 있으면 막힘)
"""
import os
import secrets
import sys

import gradio as gr
import requests

import config
import ui_theme
from agent import Conversation          # 단일 에이전트 (python app.py --single)
from graph import GraphConversation     # LangGraph 멀티 에이전트 (기본)


EXAMPLES = [
    # 정상
    "시급 10320원에 하루 4시간, 주 5일 일해. 한 달에 얼마 받아? 3.3% 떼",
    "매달 10만원씩 12개월 적금 넣으려면 어떤 상품이 있어? 나 22살이야",
    "주휴수당은 어떤 조건이면 받을 수 있어?",
    "월 100만원 버는데 월세가 50만원이야. 얼마 저축하고 어떤 적금이 맞을까? 나 23살",   # 두 에이전트 연결
    # 예외
    "한 달 알바비 얼마야?",                                   # 값 부족 → 되물어야 함
    "시급 9000원에 주 10시간이면?",                            # 최저임금 미달 + 주휴수당 없음
    "가상 하늘은행 적금 해지하면 위약금 몇 퍼센트야?",           # 문서에 없는 숫자 → 추측 금지
    "내 계좌 110-123-456789 로 적금 가입해줘",                 # 개인정보 가림 + 가입 대행 거절
]


def server_status():
    try:
        tags = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=3).json()
        names = [m["name"] for m in tags.get("models", [])]
        ok = any(n.startswith(config.CHAT_MODEL) for n in names)
        text = f"OLLAMA ONLINE · MODEL {config.CHAT_MODEL}" if ok else f"모델 {config.CHAT_MODEL} 없음 (ollama pull 필요)"
        return ui_theme.status_html(ok, text)
    except Exception:
        return ui_theme.status_html(False, f"Ollama 서버({config.OLLAMA_URL})에 연결할 수 없습니다. ollama serve 를 먼저 실행하세요.")


def ui_send(message, chat_history, conv):
    """conv 는 접속한 사람마다 따로 있는 대화 기억 (gr.State). 여러 명이 동시에 써도 대화가 안 섞인다.
    LangGraph 가 '사람 확인'을 기다리면 pending=True → 확인 버튼을 보여 준다."""
    if not message.strip():
        return "", chat_history, gr.update(), gr.update()
    pending = False
    try:
        result = conv.process(message)
        answer, log = result[0], result[1]
        pending = len(result) > 2 and result[2]
    except requests.exceptions.RequestException as e:
        answer, log = "로컬 LLM 서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.", f"[연결 오류] {e}"
    chat_history = (chat_history or []) + [{"role": "user", "content": message},
                                           {"role": "assistant", "content": answer}]
    return "", chat_history, log, gr.update(visible=pending)


def ui_confirm(chat_history, conv):
    return ui_send("응, 이 조건으로 비교해줘", chat_history, conv)


def ui_clear(conv):
    conv.clear()
    return [], "", gr.update(visible=False)


with gr.Blocks(title="ALBA·MONEY — 알바머니 도우미") as demo:     # 디자인은 ui_theme.py (launch 에서 적용)
    gr.HTML(ui_theme.HEADER_HTML)
    status = gr.HTML(server_status())
    conv_state = gr.State(Conversation() if "--single" in sys.argv else GraphConversation())   # 세션마다 복사본
    with gr.Row(equal_height=False):
        with gr.Column(scale=3, elem_classes="hud-panel"):
            gr.HTML('<div class="hud-panel-title">◆ COMM CHANNEL · 상담</div>')
            chatbot = gr.Chatbot(label="상담", height=470, elem_id="chat", show_label=False,
                                 placeholder="<div style='text-align:center;opacity:.7'>⟡ 알바비나 적금에 대해 물어보세요 ⟡</div>")
            msg = gr.Textbox(label="질문", show_label=False, elem_id="prompt",
                             placeholder="▸ 예) 시급 10320원에 주 20시간 일하면 한 달에 얼마야?")
            confirm_btn = gr.Button("✅ CONFIRM · 이 조건으로 비교", visible=False, elem_id="confirm-btn")
            with gr.Row():
                send = gr.Button("TRANSMIT ▸ 보내기", variant="primary", elem_id="send-btn")
                clear = gr.Button("RESET · 초기화", elem_id="clear-btn")
            with gr.Group(elem_id="examples"):
                gr.Examples(EXAMPLES, inputs=msg, label="시연용 예시 (위 4개 정상 · 아래 4개 예외)")
        with gr.Column(scale=2, elem_classes="hud-panel"):
            gr.HTML('<div class="hud-panel-title pink">◆ SYSTEM LOG · 도구 실행 기록</div>')
            log_box = gr.Textbox(label="실행 로그", show_label=False, lines=28, elem_id="syslog",
                                 placeholder="> awaiting input_\n> Function Call / Parameters / Output 가 여기 표시됩니다")

    outputs = [msg, chatbot, log_box, confirm_btn]
    msg.submit(ui_send, [msg, chatbot, conv_state], outputs)
    send.click(ui_send, [msg, chatbot, conv_state], outputs)
    confirm_btn.click(ui_confirm, [chatbot, conv_state], outputs)
    clear.click(ui_clear, conv_state, [chatbot, log_box, confirm_btn])

if __name__ == "__main__":
    try:                                                     # 모델을 GPU 에 미리 올려 첫 질문이 느리지 않게 (워밍업)
        requests.post(f"{config.OLLAMA_URL}/api/chat", timeout=180, json={
            "model": config.CHAT_MODEL, "messages": [{"role": "user", "content": "안녕"}], "stream": False})
    except requests.exceptions.RequestException:
        pass
    share = "--share" in sys.argv                            # Gradio 공개 주소 (리눅스 GPU 서버용)
    auth = None
    if share or "--lock" in sys.argv:                        # 공개 주소는 누구나 들어올 수 있으니 비밀번호로 잠근다
        # share.bat 이 정해 준 비밀번호가 있으면 그걸, 없으면 새로 만든다 (코드·깃허브에 남지 않음)
        password = os.environ.get("APP_PASSWORD") or secrets.token_urlsafe(6)
        auth = ("alba", password)
        print()
        print("=" * 60)
        print(f"  공개 주소 접속 정보 →  아이디: alba   비밀번호: {password}")
        print("  (공개 주소 https://....gradio.live 는 아래에 표시됩니다)")
        print("=" * 60)
        print()
    demo.launch(server_name="0.0.0.0", share=share, auth=auth,
                theme=ui_theme.THEME, css=ui_theme.CSS, js=ui_theme.FORCE_DARK_JS, head=ui_theme.HEAD,
                inbrowser="--open" in sys.argv)                # --open: 브라우저 자동으로 열기
