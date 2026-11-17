"""Gradio 웹 데모 — 왼쪽 상담, 오른쪽 실행 로그 (어떤 도구를 불렀는지 시연 때 보여 주기).

실행: python app.py            → http://localhost:7860
      python app.py --share    → 임시 공개 주소 (시연 끝나면 반드시 종료)
"""
import sys

import gradio as gr
import requests

import config
from agent import Conversation

conv = Conversation()

EXAMPLES = [
    # 정상
    "시급 10320원에 하루 4시간, 주 5일 일해. 한 달에 얼마 받아? 3.3% 떼",
    "매달 10만원씩 12개월 적금 넣으려면 어떤 상품이 있어? 나 22살이야",
    "주휴수당은 어떤 조건이면 받을 수 있어?",
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
        return f"Ollama 연결됨 · 모델 `{config.CHAT_MODEL}` {'✅' if ok else '❌ 없음 (ollama pull 필요)'}"
    except Exception:
        return f"❌ Ollama 서버({config.OLLAMA_URL})에 연결할 수 없습니다. `ollama serve` 를 먼저 실행하세요."


def ui_send(message, chat_history):
    if not message.strip():
        return "", chat_history, gr.update()
    try:
        answer, log = conv.process(message)
    except requests.exceptions.RequestException as e:
        answer, log = "로컬 LLM 서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.", f"[연결 오류] {e}"
    chat_history = (chat_history or []) + [{"role": "user", "content": message},
                                           {"role": "assistant", "content": answer}]
    return "", chat_history, log


def ui_clear():
    conv.clear()
    return [], ""


with gr.Blocks(title="알바머니 도우미") as demo:
    gr.Markdown("## 💸 알바머니 도우미 — 알바비 계산 + 적금 상품 안내\n"
                "로컬 LLM(Ollama) · RAG 문서 검색 · 도구 호출 | 은행 상품은 **시연용 가상 데이터**이며 "
                "법률·금융 자문이 아닌 정보 안내입니다. 개인정보는 입력하지 마세요.")
    status = gr.Markdown(server_status())
    with gr.Row():
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(label="상담", height=460)
            msg = gr.Textbox(label="질문", placeholder="예) 시급 10320원에 주 20시간 일하면 한 달에 얼마야?")
            with gr.Row():
                send = gr.Button("보내기", variant="primary")
                clear = gr.Button("대화 초기화")
            gr.Examples(EXAMPLES, inputs=msg, label="시연용 예시 (위 3개 정상 · 아래 4개 예외)")
        with gr.Column(scale=2):
            log_box = gr.Textbox(label="실행 로그 (Function Call / Parameters / Output)", lines=26)

    msg.submit(ui_send, [msg, chatbot], [msg, chatbot, log_box])
    send.click(ui_send, [msg, chatbot], [msg, chatbot, log_box])
    clear.click(ui_clear, None, [chatbot, log_box])

if __name__ == "__main__":
    try:                                                     # 모델을 GPU 에 미리 올려 첫 질문이 느리지 않게 (워밍업)
        requests.post(f"{config.OLLAMA_URL}/api/chat", timeout=180, json={
            "model": config.CHAT_MODEL, "messages": [{"role": "user", "content": "안녕"}], "stream": False})
    except requests.exceptions.RequestException:
        pass
    demo.launch(server_name="0.0.0.0", share="--share" in sys.argv,
                inbrowser="--open" in sys.argv)                # --open: 브라우저 자동으로 열기
