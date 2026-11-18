"""LangGraph 멀티 에이전트 흐름을 가짜 모델로 확인 (LLM 없이).

실행: python tests/test_graph_offline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent
import graph
import tools
from rag import Retriever


def fake_model(replies):
    it = iter(replies)
    return lambda messages, tools=None: next(it)


def call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def say(text):
    return {"role": "assistant", "content": text}


def run(replies, *messages):
    original = agent.ollama_chat
    agent.ollama_chat = fake_model(replies)
    try:
        conv = graph.GraphConversation()
        return [conv.process(m) for m in messages]
    finally:
        agent.ollama_chat = original


def test_coach_route():
    out = run([say("coach"), call("calc_alba_pay", hourly_wage=10320, hours_per_week=20), say("한 달 약 1,076,228원이에요.")],
              "시급 10320원 주 20시간 월급?")
    answer, log, pending = out[0]
    assert not pending and "1,076,228" in answer
    assert "[Router] coach" in log and "calc_alba_pay" in log and "247,680원" in log


def test_matcher_confirm_then_run():
    out = run([say("matcher"), call("compare_savings_products", monthly_amount=100000, months=12, age=22),
               say("조건에 맞는 순위: 1위 S01 ...")],
              "10만원 12개월 적금 뭐가 좋아? 22살", "응")
    (a1, log1, p1), (a2, log2, p2) = out
    assert p1 and "월 100,000원 · 12개월 · 만 22세" in a1 and "[⏸ 대기]" in log1
    assert not p2 and "1위 S01" in a2 and "[확인]" in log2 and "S01 가상 하늘은행" in log2


def test_matcher_correction():
    out = run([say("matcher"), call("compare_savings_products", monthly_amount=100000, months=12),
               call("compare_savings_products", monthly_amount=50000, months=6),
               say("월 5만원 6개월 기준 순위예요.")],
              "적금 추천", "월 5만원 6개월로", "응")
    assert out[0][2] and out[1][2]                               # 수정 후 다시 확인을 묻는다
    assert "월 50,000원 · 6개월" in out[1][0]
    assert not out[2][2] and "[수정]" in out[2][1]


def test_both_route():
    out = run([say("both"), call("plan_budget", monthly_income=1000000), say("저축은 월 20만원이 적당해요."),
               call("compare_savings_products", monthly_amount=200000, months=12), say("월 20만원 기준 순위예요.")],
              "월 100만원 버는데 얼마 저축하고 어떤 적금이 맞아?", "응")
    answer = out[1][0]
    assert "💼 머니 코치" in answer and "🏦 상품 매칭" in answer


def test_money_guard():
    """도구 결과에 없는 금액(1,260,000원)을 말하면 한 번 되돌려 고치게 한다."""
    out = run([say("coach"), call("plan_budget", monthly_income=1000000),
               say("저축 20만원씩 하면 1년 뒤 약 1,260,000원이 돼요."),
               say("저축은 월 200,000원이 적당해요.")],
              "월 100만원 벌면 얼마 저축해?")
    answer, log, _ = out[0]
    assert "[가드] 근거 없는 금액 발견(1,260,000원)" in log and "1,260,000" not in answer


def test_money_guard_strips_second_time():
    """두 번째에도 근거 없는 금액이 남으면 그 줄을 코드가 지운다."""
    out = run([say("coach"), call("plan_budget", monthly_income=1000000),
               say("저축은 월 200,000원이에요.\n1년 뒤 약 1,260,000원이 돼요."),
               say("저축은 월 200,000원이에요.\n1년 뒤 약 2,470,000원이 돼요.")],
              "월 100만원 벌면 얼마 저축해?")
    answer, log, _ = out[0]
    assert "200,000원" in answer and "2,470,000" not in answer and "줄 1개 삭제" in log


def _fake_crew(calls):
    """CrewAI 대신 받은 입력만 기록하는 가짜 리포트 모듈."""
    import types
    mod = types.ModuleType("crew_report")
    mod.run_report = lambda p, on_step=None: (calls.append(p) or "## 1. 이번 달 수입\n- 총 수입: 1,076,228원", ["[Crew Tool] 가짜"])
    sys.modules["crew_report"] = mod


def test_report_asks_missing_values():
    calls = []
    _fake_crew(calls)
    out = run([], "이번 달 재무 리포트 만들어줘")                  # 모델 호출 없이 키워드로 report
    answer, log, pending = out[0]
    assert not pending and "시급, 주 근무시간" in answer and not calls


def test_report_confirm_then_crew():
    calls = []
    _fake_crew(calls)
    out = run([], "월간 리포트 만들어줘. 시급 10320원, 주 20시간, 월세 40만원, 23살", "응")
    (a1, _, p1), (a2, log2, p2) = out
    assert p1 and "시급 10,320원 · 주 20시간 · 고정비 400,000원 · 만 23세" in a1
    assert not p2 and "1,076,228" in a2 and "[Report] 완료" in log2
    assert calls[0]["hourly_wage"] == 10320 and calls[0]["fixed_costs"] == 400000


def test_report_correction():
    calls = []
    _fake_crew(calls)
    out = run([], "리포트 만들어줘 시급 10320원 주 20시간", "월세 50만원", "응")
    assert out[0][2] and out[1][2] and "고정비 500,000원" in out[1][0]
    assert calls[0]["fixed_costs"] == 500000


def test_tool_permission():
    """머니 코치가 상품 비교 도구를 부르면 코드가 막는다."""
    out = run([say("coach"), call("compare_savings_products", monthly_amount=1, months=12), say("담당이 아니에요.")],
              "아무거나")
    assert "쓸 수 없는 도구" in out[0][1]


if __name__ == "__main__":
    tools.retriever = Retriever(use_embedding=False)
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name); n += 1
    print(f"\n{n}개 그래프 테스트 모두 통과")
