"""에이전트 — Ollama 로컬 LLM + 도구 호출 루프 (3장 2부 run_agent 와 같은 구조).

① 모델에게 [system + 이전 대화 + user] 와 도구 설명서를 준다
② 모델이 도구 호출 요청(JSON)을 쓰면 → 우리 코드가 실행 → 결과를 role: tool 로 돌려준다
③ 요청이 없으면 그게 최종 답. max_iters 를 넘으면 중단
"""
import json
import re
from datetime import date

import requests
from langchain_core.utils.function_calling import convert_to_openai_tool

import config
from tools import ALL_TOOLS

SYSTEM_PROMPT = f"""당신은 아르바이트하는 대학생을 돕는 '알바머니 도우미'입니다.
규칙:
1. 알바비·주휴수당·적금 만기 같은 숫자는 반드시 계산 도구(calc_alba_pay, calc_savings, compare_savings_products)로 구합니다. 직접 암산하지 않습니다.
2. 법·제도·은행 상품(금리, 우대조건, 중도해지, 위약금 등)에 관한 질문은 '모른다'고 답하기 전에도 반드시 search_guide 를 먼저 호출합니다. 검색 결과에 답이 있으면 그 내용으로 바로 답하고 어느 문서인지 밝힙니다. 검색 결과에 정말 관련 내용이 없을 때만 "자료에서 확인할 수 없어요"라고 말합니다. 추측하지 않습니다.
3. 계산에 필요한 값(시급, 주 근무시간, 월 납입액, 기간)이 빠졌으면 도구를 부르지 말고 먼저 되묻습니다. 값을 지어내지 않습니다.
4. 특정 상품 가입을 권하지 않습니다. 조건과 금액만 비교하고, 최종 결정은 사용자가 한다고 안내합니다.
5. 은행 상품은 시연용 가상 데이터입니다. 상품을 안내할 때 '가상 상품'임을 밝힙니다.
6. 법률·금융 판단은 정보 안내로만 하고, 분쟁이나 체불은 고용노동부 1350, 금융사기는 1332·112 를 안내합니다.
7. 계좌번호·주민번호·비밀번호 같은 개인정보는 묻지도 받지도 않습니다. 적금 가입·이체·해지 같은 실제 금융 거래는 대신 할 수 없으니 은행 앱이나 창구에서 직접 하라고 안내합니다.
8. 계산 결과를 말할 때는 도구 결과의 숫자를 그대로 쓰고, 기본급·주휴수당·공제처럼 어떻게 나왔는지도 짧게 보여 줍니다.
9. 쉬운 말로, 항상 한국어로, 짧게 답합니다. 오늘 날짜는 {date.today().isoformat()} 입니다."""

TOOL_MAP = {t.name: t for t in ALL_TOOLS}
TOOL_SCHEMAS = [convert_to_openai_tool(t) for t in ALL_TOOLS]

# ── 보안: 개인정보는 모델에 닿기 전에 '코드로' 가린다 (프롬프트 규칙은 부탁일 뿐) ──────────
PII_PATTERNS = [
    (re.compile(r"\d{6}\s*-\s*[1-4]\d{6}"), "[주민번호 가림]"),
    (re.compile(r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"), "[카드번호 가림]"),
    (re.compile(r"01[016789][\s-]?\d{3,4}[\s-]?\d{4}"), "[전화번호 가림]"),
    (re.compile(r"\d{2,6}-\d{2,6}-\d{2,8}"), "[계좌번호 가림]"),
]


def mask_pii(text):
    """입력에서 개인정보 패턴을 찾아 가린다. (가린 글, 가린 개수)"""
    count = 0
    for pattern, repl in PII_PATTERNS:
        text, n = pattern.subn(repl, text)
        count += n
    return text, count


# ── LLM 호출 ───────────────────────────────────────────────────────
TEXT_TOOL_MODE = False      # 모델이 Ollama 의 tools 기능을 지원하지 않으면 True 로 바뀐다 (예: exaone3.5)


def _post_chat(messages, tools=None):
    payload = {"model": config.CHAT_MODEL, "messages": messages, "stream": False,
               "options": {"temperature": 0}}                       # 0 = 같은 질문엔 같은 답 (시연 안정성)
    if tools:
        payload["tools"] = tools
    return requests.post(f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=180)


def to_text_tool_messages(messages, tools):
    """tools 를 지원하지 않는 모델용 (3장 11단계 방식): 도구 설명서를 시스템 프롬프트에 글로 넣고,
    호출은 <tool_call>{...}</tool_call> 글자로 받는다. tool 결과는 user 메시지로 바꿔 전달한다."""
    guide = ("\n\n# 사용할 수 있는 도구 (JSON 설명서)\n" + json.dumps(tools, ensure_ascii=False) +
             "\n\n도구가 필요하면 다른 말 없이 정확히 이 형식 한 줄만 출력하세요:\n"
             '<tool_call>{"name": "도구이름", "arguments": {"인자": 값}}</tool_call>\n'
             "도구 결과를 받은 뒤에는 그 결과로 최종 답을 쓰세요.")
    out = []
    for m in messages:
        if m["role"] == "system":
            out.append({"role": "system", "content": m["content"] + guide})
        elif m["role"] == "tool":
            out.append({"role": "user", "content": f"[도구 {m.get('tool_name')} 실행 결과]\n{m['content']}"})
        else:
            out.append({"role": m["role"], "content": m.get("content") or ""})
    return out


def ollama_chat(messages, tools=None):
    """Ollama /api/chat 호출 → 모델의 메시지 dict ({role, content, tool_calls?})"""
    global TEXT_TOOL_MODE
    if tools and not TEXT_TOOL_MODE:
        res = _post_chat(messages, tools)
        if res.status_code == 400 and "does not support tools" in res.text:
            TEXT_TOOL_MODE = True                                    # 이후로는 글자 방식으로
        else:
            res.raise_for_status()
            return res.json()["message"]
    if tools and TEXT_TOOL_MODE:
        messages = to_text_tool_messages(messages, tools)
    res = _post_chat(messages)
    res.raise_for_status()
    return res.json()["message"]


# 실제 테스트에서 발견: qwen2.5 가 "검색해보겠습니다"라고만 쓰고 도구를 부르지 않고 끝내는 경우가 있었다.
PROMISE_RE = re.compile(r"(검색|찾아|확인|계산)\s*(해\s*)?(보겠|볼게|하겠|할게)")

TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def get_tool_calls(msg):
    """모델 메시지에서 도구 호출 요청을 꺼낸다.
    정상: Ollama 가 tool_calls 필드로 준다. 예비: 일부 모델은 본문에 <tool_call>{...}</tool_call> 글자로 쓴다."""
    calls = [{"name": c["function"]["name"], "arguments": c["function"].get("arguments") or {}}
             for c in msg.get("tool_calls") or []]
    if not calls:
        for m in TOOL_CALL_RE.finditer(msg.get("content") or ""):
            try:
                calls.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                pass
    for c in calls:                                                  # 인자가 문자열 JSON 으로 오는 모델 대비
        if isinstance(c.get("arguments"), str):
            try:
                c["arguments"] = json.loads(c["arguments"])
            except json.JSONDecodeError:
                c["arguments"] = {}
    return calls


# ── 에이전트 루프 ──────────────────────────────────────────────────
def run_agent(user_message, history=None, max_iters=config.MAX_ITERS, verbose=False):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(history or []) \
               + [{"role": "user", "content": user_message}]
    log, nudged = [], False
    for _ in range(max_iters):
        msg = ollama_chat(messages, tools=TOOL_SCHEMAS)              # ① 요청(JSON) 또는 최종 답
        calls = get_tool_calls(msg)
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         **({"tool_calls": msg["tool_calls"]} if msg.get("tool_calls") else {})})
        content = (msg.get("content") or "").strip()
        if not calls and PROMISE_RE.search(content) and not nudged:  # "검색해 볼게요"라고 말만 하고 도구를 안 부른 경우
            nudged = True                                            # → 한 번만 재촉해서 실제로 호출하게 한다
            messages.append({"role": "user", "content": "말로만 하지 말고 지금 바로 알맞은 도구를 호출하세요."})
            continue
        if not calls:                                                # ② 요청 없음 = 최종 답
            return content, log, messages
        for c in calls:                                              # ③ 실행은 우리 코드가
            name, args = c.get("name"), c.get("arguments") or {}
            if name not in TOOL_MAP:
                result = f"[에러] 없는 도구입니다: {name}. 사용 가능: {list(TOOL_MAP)}"
            else:
                try:
                    result = TOOL_MAP[name].invoke(args)
                except Exception as e:                               # 인자 타입 오류 등 → 문장으로 돌려줘 모델이 고치게
                    result = f"[도구 실행 오류] {e}. 인자 형식을 확인하세요."
            log.append({"tool": name, "args": args, "result": str(result)})
            if verbose:
                print(f"[Function Call] {name} {args}\n[Output] {str(result)[:300]}\n")
            messages.append({"role": "tool", "tool_name": name, "content": str(result)})   # ④ 결과 돌려주기
    return "도구 호출이 너무 많아 중단했어요. 질문을 조금 더 구체적으로 해 주세요.", log, messages


class Conversation:
    """멀티턴 기억 = 메시지 리스트를 통째로 다시 넘기기. 개인정보는 기억에 남기 전에 가린다."""

    def __init__(self, keep=12):
        self.history = []
        self.keep = keep

    def process(self, message):
        safe_message, n_masked = mask_pii(message)
        answer, log, messages = run_agent(safe_message, history=self.history)
        self.history = messages[1:][-self.keep:]
        while self.history and self.history[0]["role"] == "tool":    # 잘린 기록이 tool 로 시작하지 않게
            self.history.pop(0)
        lines = [f"[User Input] {safe_message}"]
        if n_masked:
            lines.append(f"[보안] 개인정보 {n_masked}건을 가린 뒤 모델에 전달했습니다.")
            answer = "⚠ 계좌번호·주민번호 같은 개인정보는 입력하지 마세요. 가린 뒤 처리했어요.\n\n" + answer
        for e in log:
            lines += [f"[Function Call] {e['tool']}", f"[Parameters] {e['args']}", f"[Output] {e['result'][:400]}"]
        lines.append(f"[AI Response] {answer}")
        return answer, "\n".join(lines)

    def clear(self):
        self.history = []


if __name__ == "__main__":                                           # python agent.py 로 터미널 확인
    conv = Conversation()
    for q in ["시급 10320원에 주 20시간 일하면 한 달에 얼마 받아?",
              "그럼 그중 10만원씩 12개월 적금 넣으면 어떤 상품이 있어?",
              "주휴수당은 어떤 조건이야?"]:
        answer, log = conv.process(q)
        print("=" * 70)
        print(log)
