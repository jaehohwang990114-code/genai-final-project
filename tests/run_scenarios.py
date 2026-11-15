"""실제 로컬 LLM 으로 시연 시나리오를 돌려 '어떤 도구를 불렀는지'와 답을 기록한다.
결과는 보고서의 '테스트와 개선' 장 재료가 된다.

실행: python tests/run_scenarios.py            (기본 모델)
      CHAT_MODEL=exaone3.5:7.8b python tests/run_scenarios.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agent import Conversation
from app import EXAMPLES

# (질문, 기대: 불러야 할 도구 이름 또는 None=도구 없이 되묻기/거절)
EXPECT = ["calc_alba_pay", "compare_savings_products", "search_guide",
          None, "calc_alba_pay", "search_guide", None]

print(f"모델: {config.CHAT_MODEL}\n")
for q, expect in zip(EXAMPLES, EXPECT):
    conv = Conversation()                          # 시나리오마다 새 대화
    t = time.time()
    answer, log = conv.process(q)
    called = [line.split("] ", 1)[1] for line in log.splitlines() if line.startswith("[Function Call]")]
    ok = (expect in called) if expect else True
    print("=" * 80)
    print(f"Q: {q}\n기대 도구: {expect} | 실제 호출: {called or '없음'} | {'OK' if ok else '확인 필요'} | {time.time() - t:.1f}초")
    print(f"A: {answer}\n")
