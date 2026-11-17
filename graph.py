"""LangGraph 멀티 에이전트 — 라우터가 질문을 보고 전문 에이전트에게 보낸다.

    START → router ─┬─ coach   (💼 머니 코치: 알바비 계산·예산·재무 관리)
                    ├─ matcher (🏦 상품 매칭: 조건에 맞는 적금 순위)
                    └─ both    (머니 코치 → 상품 매칭 순서로 둘 다)

    각 에이전트:  agent ──(도구 요청)──▶ tools ──▶ agent ── … ──(최종 답)──▶ 다음 에이전트 또는 END
                    └──(상품 비교 요청)──▶ confirm ⏸ 사람 확인(interrupt) ─▶ tools

agent.py 의 부품(ollama_chat, get_tool_calls, mask_pii)을 그대로 쓰고, 흐름 제어만 LangGraph 로 한다.
"""
import re
import uuid
from datetime import date
from typing import TypedDict

from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import agent
import config
import tools as T

# ── 에이전트 정의 ───────────────────────────────────────────────────
COMMON_RULES = f"""공통 규칙:
- 숫자는 반드시 도구로 계산하고, 도구 결과의 숫자를 그대로 씁니다. 암산하지 않습니다.
- 법·제도·상품 설명은 search_guide 로 찾은 문서 내용만 말합니다. 정말 없을 때만 "자료에서 확인할 수 없어요"라고 합니다.
- 계산에 필요한 값이 빠졌으면 도구를 부르지 말고 먼저 되묻습니다. 값을 지어내지 않습니다.
- 개인정보(계좌번호·주민번호·비밀번호)는 묻지도 받지도 않습니다. 실제 가입·이체·해지는 대신 할 수 없습니다.
- 법률·금융은 정보 안내로만 답합니다. 체불은 고용노동부 1350, 금융사기는 1332·112 를 안내합니다.
- 쉬운 말로, 한국어로, 짧게. 오늘 날짜는 {date.today().isoformat()} 입니다."""

AGENTS = {
    "coach": {
        "name": "💼 머니 코치",
        "prompt": "당신은 알바하는 대학생의 '머니 코치'입니다. 알바비(기본급·주휴수당·3.3% 공제)를 계산하고, "
                  "그 돈을 어떻게 나눠 쓰고 모으면 좋을지(예산, 선저축, 통장 나누기, 비상금, 피해야 할 빚) "
                  "문서에 있는 일반 원칙으로 알려 줍니다. 특정 금융상품을 고르는 일은 '상품 매칭' 담당이니 하지 않습니다. "
                  "투자 종목 추천 같은 개인 맞춤 투자 조언은 하지 않습니다. "
                  "돈 관리·저축 방법·비상금 같은 질문은 반드시 search_guide 로 '재무 관리' 문서를 먼저 찾고 그 내용으로 답합니다. "
                  "수입 금액을 알려 주면 plan_budget 으로 실제 금액을 나눠 보여 줍니다.\n" + COMMON_RULES,
        "tools": [T.calc_alba_pay, T.plan_budget, T.calc_savings, T.search_guide],
    },
    "matcher": {
        "name": "🏦 상품 매칭",
        "prompt": "당신은 '상품 매칭' 담당입니다. 사용자의 월 납입액·기간·나이에 맞는 가상 적금 상품을 "
                  "compare_savings_products 로 찾아 '조건에 맞는 순위'로 보여 줍니다. 순위 기준(최고금리 만기 금액, "
                  "우대조건을 채우기 쉬운지)을 함께 설명하고, 최종 결정은 사용자가 한다고 말합니다. "
                  "모든 상품은 시연용 가상 상품임을 밝힙니다. 우대조건·중도해지 같은 설명은 search_guide 로 찾습니다. "
                  "앞 담당자(머니 코치)의 결과가 있으면 그 숫자(예: 저축 가능 금액)를 월 납입액으로 씁니다.\n" + COMMON_RULES,
        "tools": [T.compare_savings_products, T.calc_savings, T.search_guide],
    },
}
NEED_CONFIRM = {"compare_savings_products"}      # 실행 전에 사람 확인을 받는 도구

ROUTER_PROMPT = """질문을 담당할 곳을 골라 한 단어로만 답하세요.
- coach   : 알바비·시급·주휴수당·세금·월급 계산, 예산·저축 습관·비상금·재무 관리, 인사나 기타 질문
- matcher : 적금·예금·은행 상품 비교, 금리·우대조건·중도해지, 어떤 상품이 맞는지.
            월 납입액(예: 매달 10만원씩)이 이미 정해져 있으면 matcher 입니다.
- both    : 수입(시급·월급)이나 생활비를 보고 '얼마를 저축할지'부터 계산해야 하고, 그다음 상품까지 물을 때만
답은 coach, matcher, both 중 하나만 쓰세요."""

MATCH_WORDS = re.compile(r"적금|예금|상품|은행|금리|우대|중도해지|위약금|만기")
# 문서 근거가 필요한 '설명형' 질문 (이런 질문인데 도구 없이 답하면 한 번 되돌린다)
DOC_WORDS = re.compile(r"관리|방법|비상금|통장|조건|제도|주의|어떻게|왜|위약금|중도해지|우대|퇴직금|근로계약|가산|사기")
COACH_WORDS = re.compile(r"알바비|시급|주휴|월급|주급|급여|세금|3\.3|예산|생활비|비상금|저축 습관|관리")


class State(TypedDict, total=False):
    question: str          # 이번 질문 (개인정보 가린 뒤)
    history: list          # 이전 대화 [{"role","content"}] — 최종 답만
    route: str             # coach | matcher | both
    queue: list            # 아직 차례가 안 온 에이전트들
    active: str            # 지금 일하는 에이전트
    messages: list         # 지금 에이전트의 작업 메시지 (system + 대화 + 도구 결과)
    calls: list            # 실행을 기다리는 도구 요청
    answers: list          # [[에이전트 이름, 답], ...]
    log: list              # 화면 오른쪽 실행 로그
    steps: int             # 지금 에이전트의 반복 횟수 (무한 루프 방지)
    nudged: bool           # "검색해 볼게요"만 하고 멈춘 경우 재촉했는지
    money_checked: bool    # 근거 없는 금액 가드를 이미 한 번 썼는지


# ── 노드 ───────────────────────────────────────────────────────────
def router(state: State):
    """① 질문을 보고 담당 에이전트를 고른다. 모델 답이 이상하면 키워드로 보정."""
    recent = state.get("history", [])[-4:]
    msg = agent._strip_think(agent.ollama_chat(
        [{"role": "system", "content": ROUTER_PROMPT}] + recent + [{"role": "user", "content": state["question"]}]))
    word = (msg.get("content") or "").strip().lower()
    route = next((r for r in ("both", "matcher", "coach") if r in word), None)
    how = "LLM"
    if route is None:                                            # 모델이 형식을 안 지키면 키워드로
        m, c = MATCH_WORDS.search(state["question"]), COACH_WORDS.search(state["question"])
        route, how = ("both" if m and c else "matcher" if m else "coach"), "키워드"
    queue = ["coach", "matcher"] if route == "both" else [route]
    names = " → ".join(AGENTS[a]["name"] for a in queue)
    return {"route": route, "queue": queue, "answers": [],
            "log": state.get("log", []) + [f"[Router] {route} ({how}) → {names}"]}


def start_agent(state: State):
    """② 대기열에서 다음 에이전트를 꺼내 작업 메시지를 준비한다. 앞 에이전트의 답은 참고 자료로 넘긴다."""
    queue = list(state["queue"])
    active = queue.pop(0)
    spec = AGENTS[active]
    messages = [{"role": "system", "content": spec["prompt"]}] + state.get("history", [])[-6:]
    if state.get("answers"):
        prev = "\n\n".join(f"[{n}의 결과]\n{a}" for n, a in state["answers"])
        messages.append({"role": "system", "content": "앞 담당자가 이미 처리한 내용입니다. 이어서 당신 담당 부분만 답하세요.\n" + prev})
    if queue:                                                # 뒤에 다른 담당자가 남아 있으면 그 일은 넘긴다
        messages.append({"role": "system", "content": "적금 상품 추천, 금리, 이자·만기 금액 계산은 다음 담당자(상품 매칭)가 맡습니다. "
                                                      "당신은 예산과 '한 달 저축 가능 금액'까지만 답하고, 적금·이자 이야기는 쓰지 마세요."})
    messages.append({"role": "user", "content": state["question"]})
    return {"queue": queue, "active": active, "messages": messages, "steps": 0, "nudged": False, "money_checked": False,
            "log": state["log"] + [f"[Agent] {spec['name']} 시작"]}


def _evidence(state):
    """금액의 근거로 인정하는 글: 사용자 질문·이전 대화의 사용자 말·도구 결과·앞 담당자의 답."""
    return " ".join([state["question"]]
                    + [m["content"] for m in state.get("history", []) if m["role"] == "user"]
                    + [m.get("content") or "" for m in state["messages"] if m["role"] == "tool"]
                    + [a for _, a in state.get("answers", [])])


def agent_step(state: State):
    """③ 지금 에이전트가 한 번 생각한다: 도구 요청을 쓰거나 최종 답을 쓴다."""
    spec = AGENTS[state["active"]]
    schemas = [convert_to_openai_tool(t) for t in spec["tools"]]
    msg = agent._strip_think(agent.ollama_chat(state["messages"], tools=schemas))
    calls = agent.get_tool_calls(msg)
    content = msg.get("content") or ""
    messages = state["messages"] + [{"role": "assistant", "content": content,
                                     **({"tool_calls": msg["tool_calls"]} if msg.get("tool_calls") else {})}]
    update = {"messages": messages, "calls": calls, "steps": state["steps"] + 1}
    used_tool = any(m["role"] == "tool" for m in state["messages"])
    skipped_docs = not calls and not used_tool and DOC_WORDS.search(state["question"])
    if not calls and (agent.PROMISE_RE.search(content) or skipped_docs) and not state["nudged"]:
        # ① "검색해 볼게요"라고 말만 하고 멈춤  ② 설명형 질문인데 문서를 안 찾고 자기 지식으로 답함 → 한 번 되돌린다
        hint = ("말로만 하지 말고 지금 바로 알맞은 도구를 호출하세요." if not skipped_docs
                else "답하기 전에 search_guide 로 문서를 먼저 찾고, 문서 내용으로만 다시 답하세요.")
        update["messages"] = messages + [{"role": "user", "content": hint}]
        update["nudged"] = True
        update["calls"] = [{"name": "__retry__"}]               # 다시 agent_step 으로 돌아가라는 표시
        update["log"] = state["log"] + [f"[가드] 문서 근거 없이 답하려 해서 다시 시킴" if skipped_docs
                                        else "[가드] 도구를 말로만 부르려 해서 다시 시킴"]
    elif not calls and not state.get("money_checked") and (bad := T.unknown_money(content, _evidence(state))):
        # ③ 근거 없는 금액 가드: 답에 나온 금액이 사용자 말·도구 결과에 없으면 지어낸 숫자 → 한 번 고치게 한다
        listed = ", ".join(f"{v:,}원" for v in bad[:5])
        update["messages"] = messages + [{"role": "user", "content":
            f"답에 도구 결과에 없는 금액이 있습니다: {listed}. 이 금액은 도구로 계산하거나, 계산할 수 없으면 빼고 "
            f"다시 답하세요. 사과하거나 '수정하겠다'는 말 없이 고친 답만 쓰세요."}]
        update["money_checked"] = True
        update["calls"] = [{"name": "__retry__"}]
        update["log"] = state["log"] + [f"[가드] 근거 없는 금액 발견({listed}) → 다시 시킴"]
    elif not calls:
        log = state["log"]
        bad = T.unknown_money(content, _evidence(state))
        if bad:                                              # 한 번 고치게 했는데도 남아 있으면 → 그 문장을 코드로 뺀다
            kept = [ln for ln in content.splitlines() if not T.unknown_money(ln, _evidence(state))]
            removed = len(content.splitlines()) - len(kept)
            content = "\n".join(kept) + "\n\n(근거를 확인할 수 없는 금액이 든 문장은 뺐어요.)"
            log = log + [f"[가드] 검증 안 된 금액이 든 줄 {removed}개 삭제"]
        update["answers"] = state.get("answers", []) + [[spec["name"], content.strip()]]
        update["log"] = log + [f"[{spec['name']} 답변] {content.strip()[:300]}"]
    return update


def confirm(state: State):
    """④ 사람 확인 (Human-in-the-loop). 상품 비교 조건을 보여 주고 사용자의 '확인/수정'을 기다린다."""
    call = next(c for c in state["calls"] if c.get("name") in NEED_CONFIRM)   # 확인이 필요한 요청 하나
    decision = interrupt({"tool": call["name"], "args": call.get("arguments") or {}})   # ⏸ 여기서 멈춤
    if decision.get("ok"):
        return {"log": state["log"] + ["[확인] 사용자가 조건을 승인했습니다"]}
    # 사용자가 조건을 고쳤다 → 실행하지 않고, 고친 내용을 모델에게 알려 다시 요청하게 한다
    msgs = state["messages"] + [{"role": "tool", "tool_name": c.get("name"),
                                 "content": "[실행 안 함] 사용자가 조건을 확인하지 않았습니다."} for c in state["calls"]]
    msgs.append({"role": "user", "content": f"조건을 이렇게 바꿀게요: {decision.get('text', '')}"})
    return {"messages": msgs, "calls": [], "log": state["log"] + [f"[수정] 사용자 수정: {decision.get('text', '')}"]}


def run_tools(state: State):
    """⑤ 도구 실행은 우리 코드가. 지금 에이전트에게 허락된 도구만 실행한다 (권한은 코드로)."""
    allowed = {t.name: t for t in AGENTS[state["active"]]["tools"]}
    messages, log = list(state["messages"]), list(state["log"])
    # 값 지어내기 방지: 사용자가 한 말 + 지금까지의 도구 결과·앞 담당자 답에 있는 숫자만 금액으로 인정
    user_text = " ".join([state["question"]] + [m["content"] for m in state.get("history", []) if m["role"] == "user"])
    tool_text = " ".join([m.get("content") or "" for m in messages if m["role"] == "tool"]
                         + [a for _, a in state.get("answers", [])])
    for c in state["calls"]:
        name, args = c.get("name"), c.get("arguments") or {}
        problem = T.check_user_values(name, args, user_text, tool_text)
        if name not in allowed:
            result = f"[에러] {name} 은(는) 이 담당자가 쓸 수 없는 도구입니다. 사용 가능: {list(allowed)}"
        elif problem:
            result = problem
        else:
            try:
                result = str(allowed[name].invoke(args))
            except Exception as e:
                result = f"[도구 실행 오류] {e}. 인자 형식을 확인하세요."
        log += [f"[Function Call] {name}", f"[Parameters] {args}", f"[Output] {result[:700]}"]
        messages.append({"role": "tool", "tool_name": name, "content": result})
    return {"messages": messages, "calls": [], "log": log}


# ── 갈림길 (조건부 엣지) ───────────────────────────────────────────
def after_agent(state: State):
    calls = state.get("calls") or []
    if calls and calls[0].get("name") == "__retry__":
        return "agent"
    if calls and state["steps"] < config.MAX_ITERS:
        allowed = {t.name for t in AGENTS[state["active"]]["tools"]}
        gated = any(c.get("name") in NEED_CONFIRM and c.get("name") in allowed for c in calls)
        return "confirm" if gated else "tools"          # 권한 없는 도구는 확인 없이 tools 에서 거절된다
    if calls:                                                    # 반복 한도 초과
        return "next"
    return "next"


def after_confirm(state: State):
    return "tools" if state.get("calls") else "agent"


def next_or_end(state: State):
    return "start_agent" if state.get("queue") else END


def finish(state: State):
    """반복 한도를 넘었는데 답이 없으면 안내 문구를 남긴다."""
    if state.get("calls"):
        name = AGENTS[state["active"]]["name"]
        return {"calls": [], "answers": state.get("answers", []) + [[name, "도구 호출이 너무 많아 중단했어요. 질문을 조금 더 구체적으로 해 주세요."]]}
    return {}


def build_graph():
    g = StateGraph(State)
    g.add_node("router", router)
    g.add_node("start_agent", start_agent)
    g.add_node("agent", agent_step)
    g.add_node("confirm", confirm)
    g.add_node("tools", run_tools)
    g.add_node("next", finish)
    g.add_edge(START, "router")
    g.add_edge("router", "start_agent")
    g.add_edge("start_agent", "agent")
    g.add_conditional_edges("agent", after_agent, ["agent", "confirm", "tools", "next"])
    g.add_conditional_edges("confirm", after_confirm, ["tools", "agent"])
    g.add_edge("tools", "agent")
    g.add_conditional_edges("next", next_or_end, ["start_agent", END])
    return g.compile(checkpointer=InMemorySaver())             # 체크포인터: interrupt 후 이어서 실행하려면 필요


GRAPH = build_graph()

YES_RE = re.compile(r"^\s*(응|네|예|넵|ㅇㅇ|ok|오케이|좋아|그래|맞아|확인|진행|yes)", re.IGNORECASE)


def describe_args(args):
    a = args or {}
    parts = []
    if a.get("monthly_amount"): parts.append(f"월 {int(a['monthly_amount']):,}원")
    if a.get("months"): parts.append(f"{a['months']}개월")
    if a.get("age"): parts.append(f"만 {a['age']}세")
    return " · ".join(parts) or str(a)


class GraphConversation:
    """Gradio 한 명(세션)당 하나. thread_id 로 LangGraph 체크포인트를 구분하고, 확인 대기 상태를 기억한다."""

    def __init__(self, keep=8):
        self.thread_id = None        # 첫 질문 때 만든다 (gr.State 가 세션마다 복사해도 서로 다른 id 가 되게)
        self.history = []
        self.keep = keep
        self.pending = False
        self.question = ""

    @property
    def cfg(self):
        return {"configurable": {"thread_id": self.thread_id}}

    def process(self, message):
        if self.thread_id is None:
            self.thread_id = str(uuid.uuid4())
        safe, n_masked = agent.mask_pii(message)
        warn = "⚠ 계좌번호·주민번호 같은 개인정보는 입력하지 마세요. 가린 뒤 처리했어요.\n\n" if n_masked else ""
        if self.pending:                                           # 확인 질문에 대한 대답이면 → 멈춘 곳부터 이어서
            decision = {"ok": True} if YES_RE.match(safe) else {"ok": False, "text": safe}
            result = GRAPH.invoke(Command(resume=decision), self.cfg)
        else:
            self.question = safe
            result = GRAPH.invoke({"question": safe, "history": self.history, "log": [f"[User Input] {safe}"]}, self.cfg)

        log = result.get("log", [])
        if n_masked:
            log = log + [f"[보안] 개인정보 {n_masked}건을 가린 뒤 처리했습니다."]
        interrupts = result.get("__interrupt__")
        if interrupts:                                              # ⏸ 사람 확인 대기
            self.pending = True
            info = interrupts[0].value
            answer = (f"🏦 상품 매칭: 이 조건으로 가상 적금 상품을 비교할까요?\n\n"
                      f"**{describe_args(info.get('args'))}**\n\n"
                      f"맞으면 **확인** 버튼이나 '응', 다르면 바꿀 조건을 적어 주세요. (예: 월 5만원으로)")
            return warn + answer, "\n".join(log + ["[⏸ 대기] 사용자 확인을 기다리는 중"]), True

        self.pending = False
        answers = result.get("answers", [])
        if len(answers) == 1:
            answer = answers[0][1]
        else:
            answer = "\n\n".join(f"**{n}**\n{a}" for n, a in answers)
        self.history = (self.history + [{"role": "user", "content": self.question},
                                        {"role": "assistant", "content": answer}])[-self.keep:]
        return warn + answer, "\n".join(log), False

    def clear(self):
        self.__init__(self.keep)
