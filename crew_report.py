"""CrewAI 월간 재무 리포트 — 역할이 다른 에이전트 3명이 순서대로 일해 보고서 한 장을 만든다.

    ① 💼 재무 분석가  : 알바비 계산 → 50/30/20 예산 → 한 달 저축 가능 금액
    ② 🏦 상품 리서처  : 그 금액으로 가상 적금 비교 → 조건에 맞는 순위
    ③ 🔍 검토자       : 문서로 주의점 확인 → 앞 결과를 합쳐 최종 리포트 (앞 결과에 없는 숫자 금지)

LangGraph(graph.py)의 'report' 갈림길에서만 부른다. 도구는 채팅 에이전트와 같은 MCP 서버를 쓴다.
CrewAI 가 없거나 실패하면 run_report 가 안내 문장을 돌려주고, 나머지 상담 기능은 그대로 동작한다.
"""
import logging
import os
import re

# CrewAI 의 사용 통계 전송·실행 기록 공유 질문을 끈다 (개인정보·대기 시간 방지). import 전에 설정해야 함
os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from typing import Optional

logging.getLogger("crewai").setLevel(logging.ERROR)    # 토큰 추정 경고 같은 잡음 숨김

from pydantic import create_model

import config
import tools as T

try:
    from crewai import LLM, Agent, Crew, Process, Task
    from crewai.tools import BaseTool
    AVAILABLE = True
except Exception as e:                                       # 설치 안 됨 / DLL 차단 등
    AVAILABLE, IMPORT_ERROR = False, e


# ── MCP 도구를 CrewAI 도구로 감싸기 ──────────────────────────────────
def _schemas():
    if config.TOOL_BACKEND == "mcp":
        from mcp_client import get_client
        return get_client().list_tools()
    from langchain_core.utils.function_calling import convert_to_openai_tool
    return {t.name: convert_to_openai_tool(t) for t in T.ALL_TOOLS}


def _execute(name, args):
    if config.TOOL_BACKEND == "mcp":
        from mcp_client import get_client
        return get_client().call_tool(name, args)
    return str({t.name: t for t in T.ALL_TOOLS}[name].invoke(args))


JSON_TYPES = {"integer": int, "number": float, "boolean": bool, "string": str}


def make_tool(name, log, user_text):
    """MCP 서버가 알려 준 도구 설명서(JSON 스키마)로 CrewAI 도구를 만든다. 실행하면 log 에 기록.
    실행 전에 graph.py 와 같은 가드로 '사용자 입력·앞선 도구 결과에 없는 금액'을 막는다."""
    fn = _schemas()[name]["function"]
    props, required = fn["parameters"].get("properties", {}), set(fn["parameters"].get("required", []))
    fields = {}
    for key, p in props.items():
        typ = JSON_TYPES.get(p.get("type") or next((a.get("type") for a in p.get("anyOf", []) if a.get("type") != "null"), "string"), str)
        fields[key] = (typ, ...) if key in required else (Optional[typ], None)
    ArgsModel = create_model(f"{name}_args", **fields)

    class MCPTool(BaseTool):
        def _run(self, **kwargs):
            args = {k: v for k, v in kwargs.items() if v is not None}
            if name == "calc_alba_pay":
                args.pop("weeks", None)                      # 월간 리포트 → 항상 한 달 평균(4.345주)으로 계산
            if name == "plan_budget":
                # 실제 테스트에서 발견: 분석가가 주휴수당을 뺀 금액(825,600원)을 수입으로 옮겨 적음
                # → 수입은 반드시 알바비 계산 결과의 '한 달' 금액이어야 한다
                month_lines = [ln for ln in "\n".join(log).splitlines() if "[한 달" in ln]
                allowed = set().union(*[set(T.money_in(ln)) for ln in month_lines]) if month_lines else set()
                if allowed and args.get("monthly_income") not in allowed:
                    msg = (f"[실행 안 함] monthly_income={args.get('monthly_income')} 은 알바비 계산 결과의 한 달 금액이 아닙니다. "
                           f"calc_alba_pay 결과의 '한 달' 실수령액(공제 없으면 세전) 중 하나를 쓰세요: {sorted(allowed)}")
                    log.append(f"[가드] {msg}")
                    return msg
            problem = T.check_user_values(name, args, user_text, "\n".join(log))
            if problem:
                log.append(f"[가드] {name} {args} → {problem}")
                return problem
            result = _execute(name, args)
            log.append(f"[Crew Tool] {name} {args}\n[Output] {result[:500]}")
            return result

    return MCPTool(name=name, description=fn["description"][:900], args_schema=ArgsModel)


# ── 리포트 만들기 ─────────────────────────────────────────────────────
def run_report(p):
    """p: hourly_wage, hours_per_week, fixed_costs(선택), age(선택), tax_33(bool), months(기본 12)
    반환: (리포트 글, 실행 로그 리스트)"""
    log = []
    if not AVAILABLE:
        return f"지금은 리포트 기능을 쓸 수 없어요. (CrewAI 불러오기 실패: {IMPORT_ERROR.__class__.__name__})", log
    months = p.get("months") or 12
    # 가드가 '사용자가 말한 값'으로 인정할 글 (입력값을 문장으로)
    user_text = (f"시급 {p['hourly_wage']}원 주 {p['hours_per_week']}시간 고정비 {p.get('fixed_costs') or 0}원 "
                 + ("3.3% 공제" if p.get("tax_33") else ""))
    llm = LLM(model=f"ollama_chat/{config.CHAT_MODEL}", base_url=config.OLLAMA_URL, temperature=0,
              context_window_size=config.NUM_CTX)
    # '/no_think' : qwen3 의 긴 생각 모드를 끄는 신호 (CrewAI 는 Ollama 의 think 옵션을 직접 못 넘겨서 글로 전달)
    common = "숫자는 반드시 도구로 계산하고 도구 결과의 숫자를 그대로 쓴다. 한국어로 쓴다. 은행 상품은 시연용 가상 상품이다. /no_think"

    analyst = Agent(role="💼 재무 분석가", goal="알바비와 예산을 정확히 계산해 한 달 저축 가능 금액을 정한다",
                    backstory="알바하는 대학생의 돈 관리를 돕는 꼼꼼한 분석가. " + common, llm=llm,
                    tools=[make_tool("calc_alba_pay", log, user_text), make_tool("plan_budget", log, user_text)],
                    allow_delegation=False, max_iter=5, verbose=False)
    researcher = Agent(role="🏦 상품 리서처", goal="저축 가능 금액에 맞는 가상 적금 상품을 조건 순으로 비교한다",
                       backstory="특정 상품을 권유하지 않고 조건과 숫자로만 비교하는 리서처. " + common, llm=llm,
                       tools=[make_tool("compare_savings_products", log, user_text)],
                       allow_delegation=False, max_iter=4, verbose=False)
    reviewer = Agent(role="🔍 검토자", goal="앞 결과의 숫자를 검증하고 읽기 쉬운 최종 리포트로 정리한다",
                     backstory="문서에 없는 말과 도구 결과에 없는 숫자를 걸러내는 검토자. " + common, llm=llm,
                     tools=[make_tool("search_guide", log, user_text)], allow_delegation=False, max_iter=4, verbose=False)

    fixed = f", fixed_costs={p['fixed_costs']}" if p.get("fixed_costs") else ""
    t1 = Task(agent=analyst,
              description=(f"1) calc_alba_pay(hourly_wage={p['hourly_wage']}, hours_per_week={p['hours_per_week']}, "
                           f"tax_33={str(bool(p.get('tax_33'))).lower()}) 로 한 달 알바비를 계산한다. weeks 는 넣지 않는다.\n"
                           f"2) 결과의 '[한 달…]' 줄에 있는 실수령액(공제 없으면 세전 금액)을 그대로 monthly_income 으로 "
                           f"plan_budget(monthly_income=…{fixed}) 을 호출한다.\n"
                           "3) 한 달 수입, 필요/자유/저축 금액, '한 달 저축 가능 금액'(저축 20% 금액)을 정리한다."),
              expected_output="한 달 수입, 50/30/20 예산 금액, 한 달 저축 가능 금액(원)")
    age = f", age={p['age']}" if p.get("age") else ""
    t2 = Task(agent=researcher, context=[t1],
              description=(f"앞 결과의 '한 달 저축 가능 금액'을 monthly_amount 로 하여 "
                           f"compare_savings_products(monthly_amount=…, months={months}{age}) 를 호출한다. "
                           "가입 가능한 상품을 최고금리 만기 금액 순으로 3개까지 정리하고, 우대조건을 채우기 쉬운지 한 줄씩 덧붙인다."),
              expected_output="조건에 맞는 가상 적금 순위(만기 금액·우대조건 포함)")
    # 실제 테스트에서 발견: 검토자가 검색을 건너뛰고 "해지 시 3개월 이자 차감" 같은 문서에 없는 말을 씀
    # → 주의점 근거 문서는 코드가 MCP 로 먼저 찾아서 과제 설명에 넣어 준다 (검토자는 이 안에서만 쓴다)
    docs = "\n\n".join(_execute("search_guide", {"query": q}) for q in ("비상금", "적금 중도해지"))
    log.append("[Crew Docs] search_guide 비상금 / 적금 중도해지 → 검토자에게 전달")
    t3 = Task(agent=reviewer, context=[t1, t2],
              description=("앞 두 결과와 아래 [근거 문서]를 합쳐 마크다운 리포트를 쓴다. "
                           "'주의할 점'은 [근거 문서]에 있는 내용만 쓰고, 앞 결과와 문서에 없는 숫자는 절대 쓰지 않는다.\n"
                           f"[근거 문서]\n{docs}\n[근거 문서 끝]\n"
                           "## 1. 이번 달 수입\n## 2. 예산 (50/30/20)\n## 3. 저축 계획\n"
                           "## 4. 조건에 맞는 적금 순위 (가상 상품)\n## 5. 주의할 점\n"
                           "마지막 줄: '※ 정보 안내용이며 최종 결정은 본인이 합니다.'"),
              expected_output="5개 절로 된 한국어 마크다운 월간 재무 리포트")

    crew = Crew(agents=[analyst, researcher, reviewer], tasks=[t1, t2, t3], process=Process.sequential, verbose=False)
    try:
        report = crew.kickoff().raw
    except Exception as e:
        return f"리포트를 만드는 중 오류가 났어요. 잠시 후 다시 시도해 주세요. ({e.__class__.__name__})", log

    report = re.sub(r"<think>.*?</think>", "", report or "", flags=re.DOTALL).strip()
    # 실제 테스트에서 발견: 검토자가 상품 이름('든든 2년')에 끌려 만기 금액을 '24개월 기준'으로 잘못 적음
    # → 비교는 항상 months 개월로 했으므로 기간 표기를 코드로 바로잡는다
    fixed_period = re.sub(r"\(\s*\d+\s*개월\s*기준\s*\)", f"({months}개월 기준)", report)
    if fixed_period != report:
        log.append(f"[가드] 만기 금액의 기간 표기를 {months}개월로 바로잡음")
        report = fixed_period
    # 근거 없는 금액 가드: 입력값·도구 결과에 없는 금액이 든 줄은 뺀다 (graph.py 와 같은 원칙)
    evidence = " ".join([str(v) for v in p.values() if v is not None] + log)
    bad_lines = [ln for ln in report.splitlines() if T.unknown_money(ln, evidence)]
    if bad_lines:
        report = "\n".join(ln for ln in report.splitlines() if ln not in bad_lines)
        report += "\n\n(근거를 확인할 수 없는 금액이 든 문장은 뺐어요.)"
        log.append(f"[가드] 리포트에서 검증 안 된 금액이 든 줄 {len(bad_lines)}개 삭제")
    return report, log


if __name__ == "__main__":                                   # python crew_report.py 로 단독 실행
    import time
    t = time.time()
    text, log = run_report({"hourly_wage": 10320, "hours_per_week": 20, "fixed_costs": 400000, "age": 23})
    print("\n".join(log))
    print("=" * 70)
    print(text)
    print(f"\n({time.time() - t:.1f}초)")
