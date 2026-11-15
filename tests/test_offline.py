"""LLM 없이 돌리는 테스트 — 도구 계산값, RAG 검색, 개인정보 가림, 에이전트 루프(가짜 모델).

실행: python tests/test_offline.py   (또는 pytest)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent
import tools
from rag import Retriever


def test_pay_basic():
    out = tools.calc_alba_pay.invoke({"hourly_wage": 10320, "hours_per_week": 20})
    assert "기본급 206,400원" in out
    assert "주휴수당 41,280원" in out            # (20/40) × 8 × 10,320
    assert "= 247,680원" in out
    assert "세전 1,076,228원" in out              # 247,680 × 365/7/12


def test_pay_tax_and_min_wage():
    out = tools.calc_alba_pay.invoke({"hourly_wage": 10320, "hours_per_week": 20, "tax_33": True})
    assert "실수령 약 1,040,712원" in out or "실수령 약 1,040,713원" in out
    low = tools.calc_alba_pay.invoke({"hourly_wage": 9000, "hours_per_week": 10})
    assert "주휴수당 0원 (주 15시간 미만)" in low and "최저시급" in low


def test_pay_juhyu_cap_and_absence():
    out = tools.calc_alba_pay.invoke({"hourly_wage": 10000, "hours_per_week": 45, "weeks": 1})
    assert "주휴수당 80,000원" in out             # 40시간 상한 → 8시간분
    out = tools.calc_alba_pay.invoke({"hourly_wage": 10320, "hours_per_week": 20, "full_attendance": False})
    assert "결근" in out


def test_savings():
    out = tools.calc_savings.invoke({"monthly_amount": 100000, "months": 12, "annual_rate": 4.5})
    assert "세전 이자 29,250원" in out            # 100,000 × 0.045/12 × 78
    assert "만기 실수령 약 1,224,745원" in out


def test_compare_filters():
    out = tools.compare_savings_products.invoke({"monthly_amount": 100000, "months": 12, "age": 22})
    assert "S01" in out and "S02" in out and "S04" in out
    assert "S03 청춘 26주 챌린지: 제외" in out    # 6개월만 가능
    out = tools.compare_savings_products.invoke({"monthly_amount": 100000, "months": 12, "age": 40})
    assert "S01 첫월급 정기적금: 제외 (가입대상" in out


def test_rag_keyword():
    r = Retriever(use_embedding=False)
    top = r.search("주휴수당 받으려면 몇 시간 일해야 해?")[0][1]
    assert "주휴수당" in top["title"]
    assert r.search("오늘 서울 날씨 어때") == []   # 관련 문서 없음 → 빈 결과 (추측 금지 경로)


def test_mask_pii():
    text, n = agent.mask_pii("내 계좌 110-123-456789 이고 번호는 010-1234-5678, 주민번호 990101-1234567")
    assert n == 3 and "110-123" not in text and "1234567" not in text


def test_agent_loop_with_fake_model(monkeypatch=None):
    """가짜 모델: 1번째엔 calc_alba_pay 호출 요청, 2번째엔 최종 답. 루프가 도구를 실제로 실행하는지 확인."""
    replies = iter([
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "calc_alba_pay", "arguments": {"hourly_wage": 10320, "hours_per_week": 20}}}]},
        {"role": "assistant", "content": "한 달에 약 1,076,228원이에요."},
    ])
    original = agent.ollama_chat
    agent.ollama_chat = lambda messages, tools=None: next(replies)
    try:
        answer, log, messages = agent.run_agent("시급 10320원 주 20시간 월급?")
    finally:
        agent.ollama_chat = original
    assert log[0]["tool"] == "calc_alba_pay" and "247,680원" in log[0]["result"]
    assert [m["role"] for m in messages[1:]] == ["user", "assistant", "tool", "assistant"]
    assert "1,076,228" in answer


if __name__ == "__main__":
    tools.retriever = Retriever(use_embedding=False)
    passed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
            passed += 1
    print(f"\n{passed}개 테스트 모두 통과")
