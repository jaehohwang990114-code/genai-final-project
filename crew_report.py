"""CrewAI 월간 재무 리포트 — 계산은 MCP 서버가 먼저, 글은 에이전트 3명이 나눠 쓴다.

    0단계 (코드)        : MCP 서버로 알바비 → 예산(50/30/20) → 적금 비교 → 주의점 문서 검색을 '미리' 실행
    ① 💼 재무 분석가    : 알바비·예산 결과를 해석해 '수입 · 예산 · 저축 계획'을 쓴다
    ② 🏦 상품 리서처    : 적금 비교 결과를 해석해 '조건에 맞는 순위'를 쓴다
    ③ 🔍 검토자         : 두 글의 숫자를 계산 결과와 대조하고, 문서로 '주의할 점'을 붙여 최종 리포트로 묶는다

왜 계산을 미리 하나?
  처음에는 에이전트가 도구를 직접 골라 불렀는데, 모델 호출이 10번 넘게 일어나 50~70초가 걸렸고
  분석가가 금액을 잘못 옮겨 적는 일도 있었다. 숫자는 코드(MCP)가 정확히 계산하고,
  에이전트는 해석·작성·검토에 집중하게 바꿔 모델 호출을 3번으로 줄였다.

LangGraph(graph.py)의 'report' 갈림길에서만 부른다. CrewAI 가 없거나 실패하면 안내 문장을 돌려준다.
"""
import logging
import os
import re

# CrewAI 의 사용 통계 전송·실행 기록 공유 질문을 끈다 (개인정보·대기 시간 방지). import 전에 설정해야 함
os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
logging.getLogger("crewai").setLevel(logging.ERROR)    # 토큰 추정 경고 같은 잡음 숨김
import warnings
warnings.filterwarnings("ignore", message="A function callback cannot be saved")

import config
import tools as T

try:
    from crewai import LLM, Agent, Crew, Process, Task
    AVAILABLE = True
except Exception as e:                                       # 설치 안 됨 / DLL 차단 등
    AVAILABLE, IMPORT_ERROR = False, e


def _execute(name, args):
    """도구 실행 — 채팅 에이전트와 같은 MCP 서버 (TOOL_BACKEND=local 이면 직접)."""
    if config.TOOL_BACKEND == "mcp":
        from mcp_client import get_client
        return get_client().call_tool(name, args)
    return str({t.name: t for t in T.ALL_TOOLS}[name].invoke(args))


def _money_on(text, marker):
    """text 에서 marker 가 들어간 줄의 마지막 금액. 예: '[한 달' 줄 → 실수령액"""
    lines = [ln for ln in text.splitlines() if marker in ln]
    amounts = T.money_in(lines[-1]) if lines else []
    return amounts[-1] if amounts else None


def precompute(p):
    """0단계: 리포트에 들어갈 숫자를 MCP 도구로 미리 계산한다 (모델 호출 없음, 1~2초)."""
    months = p.get("months") or 12
    pay = _execute("calc_alba_pay", {"hourly_wage": p["hourly_wage"], "hours_per_week": p["hours_per_week"],
                                     "tax_33": bool(p.get("tax_33"))})
    income = _money_on(pay, "[한 달")                         # 한 달 실수령액 (공제 없으면 세전)
    budget_args = {"monthly_income": income}
    if p.get("fixed_costs"):
        budget_args["fixed_costs"] = p["fixed_costs"]
    budget = _execute("plan_budget", budget_args)
    saving = _money_on(budget, "저축·비상금(20%)")            # 한 달 저축 가능 금액
    compare_args = {"monthly_amount": saving, "months": months}
    if p.get("age"):
        compare_args["age"] = p["age"]
    products = _execute("compare_savings_products", compare_args)
    docs = "\n\n".join(_execute("search_guide", {"query": q}) for q in ("비상금", "적금 중도해지"))
    return {"months": months, "income": income, "saving": saving,
            "pay": pay, "budget": budget, "products": products, "docs": docs}


def run_report(p, on_step=None):
    """p: hourly_wage, hours_per_week, fixed_costs·age(선택), tax_33(bool), months(기본 12)
    on_step: 진행 상황을 알릴 함수 (화면에 '분석가 완료' 같은 문구 표시용)
    반환: (리포트 글, 실행 로그 리스트)"""
    step = on_step or (lambda msg: None)
    log = []
    if not AVAILABLE:
        return f"지금은 리포트 기능을 쓸 수 없어요. (CrewAI 불러오기 실패: {IMPORT_ERROR.__class__.__name__})", log

    # ── 0단계: 숫자는 코드가 MCP 로 계산 ──
    step("🧮 MCP 서버로 알바비·예산·적금 비교 계산 중…")
    try:
        f = precompute(p)
    except Exception as e:
        return f"계산 도구(MCP)를 실행하지 못했어요. 잠시 후 다시 시도해 주세요. ({e.__class__.__name__})", log
    log += [f"[Report 계산] calc_alba_pay → 한 달 {f['income']:,}원",
            f"[Report 계산] plan_budget → 저축 가능 {f['saving']:,}원",
            f"[Report 계산] compare_savings_products · search_guide(비상금, 적금 중도해지) 완료 (via MCP)"]
    step(f"✅ 계산 완료 — 한 달 {f['income']:,}원, 저축 가능 {f['saving']:,}원")

    # ── 1~3단계: 에이전트 3명이 해석·작성·검토 ──
    llm = LLM(model=f"ollama_chat/{config.CHAT_MODEL}", base_url=config.OLLAMA_URL, temperature=0,
              context_window_size=config.NUM_CTX)
    # '/no_think' : qwen3 의 긴 생각 모드를 끄는 신호 (CrewAI 는 Ollama 의 think 옵션을 직접 못 넘겨서 글로 전달)
    rule = "아래 [계산 결과]의 숫자만 그대로 쓰고 새 숫자를 만들지 않는다. 한국어 마크다운. 짧고 쉽게. /no_think"

    analyst = Agent(role="💼 재무 분석가", goal="알바비와 예산 계산 결과를 대학생이 이해하기 쉽게 해석한다",
                    backstory="알바하는 대학생의 돈 관리를 돕는 분석가. 계산은 이미 끝났고 해석만 한다.", llm=llm,
                    allow_delegation=False, max_iter=1, verbose=False)
    researcher = Agent(role="🏦 상품 리서처", goal="적금 비교 결과를 조건에 맞는 순위로 설명한다",
                       backstory="특정 상품을 권유하지 않고 조건과 숫자로만 비교한다. 모든 상품은 시연용 가상 상품이다.",
                       llm=llm, allow_delegation=False, max_iter=1, verbose=False)
    reviewer = Agent(role="🔍 검토자", goal="앞 두 글의 숫자를 계산 결과와 대조하고 최종 리포트로 묶는다",
                     backstory="계산 결과·문서에 없는 숫자와 말을 걸러내는 검토자.", llm=llm,
                     allow_delegation=False, max_iter=1, verbose=False)

    t1 = Task(agent=analyst,
              description=(f"{rule}\n[계산 결과: 알바비]\n{f['pay']}\n[계산 결과: 예산]\n{f['budget']}\n"
                           "다음 두 절을 쓴다.\n## 1. 이번 달 수입\n## 2. 예산 (50/30/20)\n"
                           f"그리고 '## 3. 저축 계획'에 한 달 저축 가능 금액 {f['saving']:,}원과 비상금 목표를 한두 줄로 쓴다."),
              expected_output="1~3절 마크다운", async_execution=True)     # 리서처와 동시에 작성
    t2 = Task(agent=researcher,
              description=(f"{rule}\n[계산 결과: 적금 비교 — 모두 {f['months']}개월 기준]\n{f['products']}\n"
                           f"'## 4. 조건에 맞는 적금 순위 (가상 상품, {f['months']}개월 기준)' 절을 쓴다. "
                           "가입 가능한 상품을 최고금리 만기 금액 순으로 최대 3개, 각각 만기 금액과 우대조건을 채우기 쉬운지 한 줄."),
              expected_output="4절 마크다운", async_execution=True)
    # 검토자는 1~4절을 다시 쓰지 않는다 (전체를 다시 쓰느라 27초 걸렸음) → 대조 메모 + 5절만 쓰고, 조립은 코드가
    t3 = Task(agent=reviewer, context=[t1, t2],
              description=(f"{rule}\n① 앞 두 글(1~4절)의 숫자를 [계산 결과]와 대조해 틀린 숫자가 있으면 "
                           "'검토: <틀린 숫자> → <맞는 숫자>' 형식으로 한 줄씩, 없으면 '검토: 숫자 일치' 한 줄을 쓴다. "
                           "1~4절은 다시 쓰지 않는다.\n"
                           f"[계산 결과]\n{f['pay']}\n{f['budget']}\n{f['products']}\n"
                           f"[근거 문서]\n{f['docs']}\n[근거 문서 끝]\n"
                           "② 이어서 '## 5. 주의할 점'을 [근거 문서] 내용만으로 3줄 이내로 쓴다."),
              expected_output="검토 메모 한 줄 이상 + 5절 마크다운")

    def task_done(output):                                    # CrewAI 가 과제 하나를 끝낼 때마다 부른다
        who = {"💼 재무 분석가": "💼 분석가", "🏦 상품 리서처": "🏦 리서처"}.get(getattr(output, "agent", ""), "🔍 검토자")
        step(f"✅ {who} 작성 완료")

    step("💼 분석가 · 🏦 리서처가 동시에 작성 중… 이어서 🔍 검토자가 확인")
    crew = Crew(agents=[analyst, researcher, reviewer], tasks=[t1, t2, t3], process=Process.sequential,
                verbose=False, task_callback=task_done)
    try:
        crew.kickoff()
    except Exception as e:
        return f"리포트를 만드는 중 오류가 났어요. 잠시 후 다시 시도해 주세요. ({e.__class__.__name__})", log
    # 최종 조립은 코드가: 분석가(1~3절) + 리서처(4절) + 검토자의 5절. 검토 메모는 로그로
    review = t3.output.raw if t3.output else ""
    notes = [ln.strip() for ln in review.splitlines() if ln.strip().startswith("검토")]
    part5 = review[review.find("## 5"):] if "## 5" in review else "## 5. 주의할 점\n" + review
    log += [f"[🔍 검토자] {n}" for n in notes] or ["[🔍 검토자] (검토 메모 없음)"]
    report = "\n\n".join([t1.output.raw.strip(), t2.output.raw.strip(), part5.strip(),
                          "※ 정보 안내용이며 최종 결정은 본인이 합니다."])

    report = re.sub(r"<think>.*?</think>", "", report or "", flags=re.DOTALL).strip()
    # 기간 표기 가드: 비교는 항상 months 개월로 했으므로 '(N개월 기준)' 표기를 바로잡는다
    # (실제 테스트에서 상품 이름 '든든 2년'에 끌려 '24개월 기준'이라고 쓴 적이 있다)
    fixed = re.sub(r"\(\s*\d+\s*개월\s*기준\s*\)", f"({f['months']}개월 기준)", report)
    if fixed != report:
        log.append(f"[가드] 만기 금액의 기간 표기를 {f['months']}개월로 바로잡음")
        report = fixed
    # 근거 없는 금액 가드: 입력값·계산 결과·문서에 없는 금액이 든 줄은 뺀다 (graph.py 와 같은 원칙)
    evidence = " ".join([str(v) for v in p.values() if v is not None] + [f["pay"], f["budget"], f["products"], f["docs"]])
    bad = [ln for ln in report.splitlines() if T.unknown_money(ln, evidence)]
    if bad:
        report = "\n".join(ln for ln in report.splitlines() if ln not in bad)
        report += "\n\n(근거를 확인할 수 없는 금액이 든 문장은 뺐어요.)"
        log.append(f"[가드] 리포트에서 검증 안 된 금액이 든 줄 {len(bad)}개 삭제")
    return report, log


if __name__ == "__main__":                                   # python crew_report.py 로 단독 실행
    import time
    t = time.time()
    text, log = run_report({"hourly_wage": 10320, "hours_per_week": 20, "fixed_costs": 400000, "age": 23},
                           on_step=lambda m: print(f"[{time.time() - t:5.1f}s] {m}"))
    print("\n".join(log))
    print("=" * 70)
    print(text)
    print(f"\n({time.time() - t:.1f}초)")
