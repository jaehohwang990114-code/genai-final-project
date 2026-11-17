"""실제 로컬 LLM 으로 LangGraph 멀티 에이전트 시나리오를 돌려 라우팅·도구·확인 흐름을 기록한다.
확인 질문이 나오면 자동으로 '응'이라고 답한다.

실행: python tests/run_graph_scenarios.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from graph import GraphConversation

# (질문, 기대 라우트, 기대 도구 또는 None=도구 없이 답)
SCENARIOS = [
    ("시급 10320원에 하루 4시간, 주 5일 일해. 한 달에 얼마 받아? 3.3% 떼", "coach", "calc_alba_pay"),
    ("매달 10만원씩 12개월 적금 넣으려면 어떤 상품이 있어? 나 22살이야", "matcher", "compare_savings_products"),
    ("주휴수당은 어떤 조건이면 받을 수 있어?", "coach", "search_guide"),
    ("알바비 받으면 어떻게 관리하는 게 좋아?", "coach", "search_guide"),
    ("월 100만원 버는데 월세가 50만원이야. 얼마 저축하고 어떤 적금이 맞을까? 나 23살", "both", "compare_savings_products"),
    ("한 달 알바비 얼마야?", "coach", None),
    ("시급 9000원에 주 10시간이면?", "coach", "calc_alba_pay"),
    ("가상 하늘은행 적금 해지하면 위약금 몇 퍼센트야?", "matcher", "search_guide"),
    ("내 계좌 110-123-456789 로 적금 가입해줘", None, None),
]

print(f"모델: {config.CHAT_MODEL}\n")
ok_count = 0
for q, want_route, want_tool in SCENARIOS:
    conv = GraphConversation()
    t = time.time()
    answer, log, pending = conv.process(q)
    confirms = 0
    while pending and confirms < 2:                       # 사람 확인 → 자동 승인
        confirms += 1
        answer, log, pending = conv.process("응")
    route = next((l.split()[1] for l in log.splitlines() if l.startswith("[Router]")), "?")
    called = [l.split("] ", 1)[1].split(" (via")[0] for l in log.splitlines() if l.startswith("[Function Call]")]
    ok = (want_route is None or route == want_route) and ((want_tool in called) if want_tool else not called or want_route is None)
    ok_count += ok
    print("=" * 80)
    print(f"Q: {q}\n라우트: {route} (기대 {want_route}) | 도구: {called or '없음'} (기대 {want_tool}) | "
          f"확인 {confirms}회 | {'OK' if ok else '확인 필요'} | {time.time() - t:.1f}초")
    print(f"A: {answer}\n")
print(f"결과: {ok_count} / {len(SCENARIOS)}")
