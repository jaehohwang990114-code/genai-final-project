"""MCP 서버 — 알바머니 도구 5개를 표준(MCP)으로 내보내는 '도구 창고'.

에이전트(graph.py)는 도구 코드를 직접 import 하지 않고, 이 서버에 접속해 도구 목록을 받고 실행을 요청한다.
같은 서버를 Claude 데스크톱 같은 다른 MCP 앱에도 그대로 연결할 수 있다.

실행 방식: stdio (클라이언트가 이 파일을 하위 프로세스로 켜고 표준입출력으로 JSON-RPC 메시지를 주고받는다)
    직접 확인: python mcp_server.py   (멈춘 것처럼 보이면 정상 — 클라이언트 메시지를 기다리는 중. Ctrl+C 로 종료)

계산·검색 로직은 tools.py 에 그대로 있고, 여기서는 MCP 용 '얇은 포장'만 한다.
금액 검증·도구 권한 같은 가드는 에이전트 쪽(graph.py)에 있다 → 서버는 계산만, 판단·통제는 클라이언트.
"""
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

import tools as T

mcp = FastMCP("alba-money-tools", log_level="WARNING", instructions="알바비·예산·적금 계산과 노동·금융 안내 문서 검색 도구. 은행 상품은 시연용 가상 데이터.")


@mcp.tool(description=T.search_guide.description)
def search_guide(query: Annotated[str, Field(description="검색할 질문이나 키워드 (예: 주휴수당 조건, 적금 중도해지)")]) -> str:
    return T.search_guide.invoke({"query": query})


@mcp.tool(description=T.calc_alba_pay.description)
def calc_alba_pay(
    hourly_wage: Annotated[int, Field(description="시급(원). 사용자가 말한 값만")],
    hours_per_week: Annotated[float, Field(description="1주 근무시간(시간). 하루 4시간씩 주 5일이면 20")],
    weeks: Annotated[Optional[float], Field(description="계산할 주 수. 한 달 월급이면 넣지 않음(자동으로 4.345주)")] = None,
    tax_33: Annotated[bool, Field(description="3.3% 를 떼고 받으면 true")] = False,
    full_attendance: Annotated[bool, Field(description="그 주 근무일을 결근 없이 나갔으면 true. false 면 주휴수당 없음")] = True,
) -> str:
    return T.calc_alba_pay.invoke({"hourly_wage": hourly_wage, "hours_per_week": hours_per_week, "weeks": weeks,
                                   "tax_33": tax_33, "full_attendance": full_attendance})


@mcp.tool(description=T.calc_savings.description)
def calc_savings(
    monthly_amount: Annotated[int, Field(description="월 납입액(원)")],
    months: Annotated[int, Field(description="가입 기간(개월)")],
    annual_rate: Annotated[float, Field(description="연 금리(%). 예: 4.5")],
    tax_free: Annotated[bool, Field(description="비과세 상품이면 true")] = False,
) -> str:
    return T.calc_savings.invoke({"monthly_amount": monthly_amount, "months": months,
                                  "annual_rate": annual_rate, "tax_free": tax_free})


@mcp.tool(description=T.compare_savings_products.description)
def compare_savings_products(
    monthly_amount: Annotated[int, Field(description="월 납입 가능 금액(원)")],
    months: Annotated[int, Field(description="원하는 가입 기간(개월). 6, 12, 24 중")],
    age: Annotated[Optional[int], Field(description="만 나이. 모르면 생략")] = None,
) -> str:
    return T.compare_savings_products.invoke({"monthly_amount": monthly_amount, "months": months, "age": age})


@mcp.tool(description=T.plan_budget.description)
def plan_budget(
    monthly_income: Annotated[int, Field(description="한 달 실수령 수입(원)")],
    fixed_costs: Annotated[Optional[int], Field(description="월세·통신비·교통비 같은 한 달 고정비 합계(원). 모르면 생략")] = None,
) -> str:
    return T.plan_budget.invoke({"monthly_income": monthly_income, "fixed_costs": fixed_costs})


if __name__ == "__main__":
    mcp.run()          # 기본 transport = stdio
