"""에이전트 도구 4개 — 3장 2부 실습과 같은 구조 (@tool + docstring + 본문 + 반환 문장).

모델이 보는 건 이름·docstring·인자뿐이다. 그래서 docstring 에 입력 형식, 예시 값, 생략 시 동작을 적고
오류는 예외 대신 "다음에 할 일" 문장으로 돌려준다.

  search_guide              RAG: 안내 문서 검색 (주휴수당, 세금, 적금 기초, 가상 상품 설명서, 사기 주의)
  calc_alba_pay             계산: 주급·월급 (기본급 + 주휴수당 - 3.3% 공제), 최저임금 미달 경고
  calc_savings              계산: 적금 만기 금액 (단리, 이자소득세 15.4%)
  compare_savings_products  조회+계산: 조건에 맞는 가상 적금 상품을 골라 만기 금액 비교
"""
import json
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

import config
from rag import Retriever

PRODUCTS = json.loads((Path(__file__).parent / "data" / "products.json").read_text(encoding="utf-8"))
retriever = None                                   # 첫 검색 때 한 번만 만든다 (임베딩 계산이 느리므로)


def _won(x):
    return f"{int(x):,}원"


# ── 도구 1 · RAG 검색 ─────────────────────────────────────────────
@tool(parse_docstring=True)
def search_guide(query: str) -> str:
    """알바·금융 안내 문서를 검색합니다. 주휴수당 조건, 최저임금, 3.3% 세금, 가산수당, 근로계약서, 퇴직금,
    예금·적금 차이, 우대금리, 중도해지, 예금자보호, 가상 은행 상품 설명, 금융사기 주의 같은 '규칙·설명' 질문에 씁니다.

    Args:
        query: 검색할 질문이나 키워드 (예: 주휴수당 조건, 적금 중도해지)
    """
    global retriever
    if retriever is None:
        retriever = Retriever()
    hits = retriever.search(query)
    if not hits:
        return "관련 문서를 찾지 못했습니다. 문서에 없는 내용이므로 추측하지 말고 '확인할 수 없다'고 안내하세요."
    return "\n\n".join(f"[근거 {i}: {c['source']} > {c['title']}]\n{c['text']}"
                       for i, (_, c) in enumerate(hits, 1))


# ── 도구 2 · 알바비 계산 ──────────────────────────────────────────
@tool(parse_docstring=True)
def calc_alba_pay(hourly_wage: int, hours_per_week: float, weeks: Optional[float] = None,
                  tax_33: bool = False, full_attendance: bool = True) -> str:
    """알바비(주급·월급)를 계산합니다. 기본급 + 주휴수당을 더하고, 3.3% 공제 여부를 반영합니다.
    시급이 최저임금보다 낮으면 경고합니다. 야간·연장 가산수당은 계산하지 않습니다.

    Args:
        hourly_wage: 시급(원). 예: 10320
        hours_per_week: 1주 근무시간(시간). 예: 하루 4시간씩 주 5일이면 20
        weeks: 계산할 주 수. 한 달 월급을 물으면 넣지 마세요(생략하면 자동으로 한 달 평균 4.345주로 계산)
        tax_33: 3.3% 를 떼고 받으면 true, 아니면 false(기본)
        full_attendance: 그 주 근무일을 결근 없이 모두 나갔으면 true(기본). false 면 주휴수당 없음
    """
    if hourly_wage <= 0 or hours_per_week <= 0:
        return "시급과 주 근무시간은 0보다 커야 합니다. 사용자에게 시급과 주 몇 시간 일하는지 다시 물어보세요."
    if hours_per_week > 52:
        return "주 근무시간이 52시간을 넘습니다. 입력이 맞는지 사용자에게 확인하세요."

    base = hourly_wage * hours_per_week                                    # 주 기본급
    if hours_per_week >= 15 and full_attendance:                           # 주휴수당 조건 2가지
        juhyu = min(hours_per_week, 40) / 40 * 8 * hourly_wage
        juhyu_note = f"주휴수당 {_won(juhyu)} (주 {hours_per_week:g}시간 ≥ 15시간, 개근)"
    else:
        juhyu = 0
        juhyu_note = ("주휴수당 0원 (주 15시간 미만)" if hours_per_week < 15
                      else "주휴수당 0원 (결근이 있어 조건 미충족)")
    weekly = base + juhyu

    if weeks and abs(weeks - config.WEEKS_PER_MONTH) < 0.01:              # 모델이 4.345 를 직접 넣어도 '한 달'로 같게 처리
        weeks = None
    n_weeks = weeks if weeks else config.WEEKS_PER_MONTH
    label = f"{weeks:g}주" if weeks else "한 달(평균 4.345주)"
    gross = weekly * n_weeks
    tax = gross * config.TAX_33 if tax_33 else 0

    lines = [f"[1주] 기본급 {_won(base)} (시급 {_won(hourly_wage)} × {hours_per_week:g}시간) + {juhyu_note} = {_won(weekly)}",
             f"[{label}] 세전 {_won(gross)}"]
    if tax_33:
        lines.append(f"[{label}] 3.3% 공제 -{_won(tax)} → 실수령 약 {_won(gross - tax)}")
    else:
        lines.append(f"[{label}] 공제 없이 약 {_won(gross)} (4대보험 가입자는 급여명세서의 공제액을 확인)")
    if hourly_wage < config.MIN_WAGE:
        lines.append(f"⚠ 시급 {_won(hourly_wage)}은 {config.MIN_WAGE_YEAR}년 최저시급 {_won(config.MIN_WAGE)}보다 "
                     f"{_won(config.MIN_WAGE - hourly_wage)} 낮습니다. 고용노동부 1350 상담을 안내하세요.")
    return "\n".join(lines)


# ── 도구 3 · 적금 만기 계산 ───────────────────────────────────────
def _savings(monthly, months, rate, tax_free=False):
    """단리 정기적금: 이자 = 월납입 × (연금리/12) × n(n+1)/2. (원금, 세전이자, 세후 만기액) 반환."""
    principal = monthly * months
    interest = monthly * (rate / 100 / 12) * months * (months + 1) / 2
    after_tax = interest if tax_free else interest * (1 - config.INTEREST_TAX)
    return principal, interest, principal + after_tax


@tool(parse_docstring=True)
def calc_savings(monthly_amount: int, months: int, annual_rate: float, tax_free: bool = False) -> str:
    """정기적금 만기 금액을 계산합니다(단리, 매달 같은 날 납입 가정). 이자소득세 15.4% 를 뺀 실수령액도 보여 줍니다.

    Args:
        monthly_amount: 월 납입액(원). 예: 100000
        months: 가입 기간(개월). 예: 12
        annual_rate: 연 금리(%). 예: 4.5
        tax_free: 비과세 상품이면 true, 일반과세면 false(기본)
    """
    if monthly_amount <= 0 or months <= 0:
        return "월 납입액과 기간은 0보다 커야 합니다. 사용자에게 다시 물어보세요."
    if not 0 < annual_rate < 20:
        return "연 금리는 0~20% 사이 숫자(예: 4.5)로 넣어 주세요."
    principal, interest, total = _savings(monthly_amount, months, annual_rate, tax_free)
    tax_note = "비과세" if tax_free else f"이자소득세 15.4% -{_won(interest * config.INTEREST_TAX)}"
    return (f"월 {_won(monthly_amount)} × {months}개월, 연 {annual_rate}% 단리\n"
            f"원금 {_won(principal)} + 세전 이자 {_won(interest)} ({tax_note})\n"
            f"만기 실수령 약 {_won(total)}")


# ── 도구 4 · 가상 상품 비교 ───────────────────────────────────────
@tool(parse_docstring=True)
def compare_savings_products(monthly_amount: int, months: int, age: Optional[int] = None) -> str:
    """월 납입액·기간(·나이)에 가입 가능한 가상 은행 적금 상품을 찾아, 기본금리와 최고금리 기준 만기 금액을 비교합니다.
    특정 상품을 권유하지 않고 조건만 비교합니다.

    Args:
        monthly_amount: 월 납입 가능 금액(원). 예: 100000
        months: 원하는 가입 기간(개월). 예: 6, 12, 24
        age: 만 나이. 생략하면 나이 조건은 따지지 않고 표시만 함
    """
    rows, skipped = [], []
    for p in PRODUCTS:
        if p["종류"] == "정기예금":
            continue
        reason = None
        if months not in p["가입기간"]:
            reason = f"기간 {p['가입기간']}개월만 가능"
        elif not p["월최소"] <= monthly_amount <= p["월최대"]:
            reason = f"월 {_won(p['월최소'])}~{_won(p['월최대'])}만 가능"
        elif age is not None and p["가입대상"].startswith("만 "):
            lo, hi = map(int, p["가입대상"][2:-1].split("~"))
            if not lo <= age <= hi:
                reason = f"가입대상 {p['가입대상']}"
        if reason:
            skipped.append(f"- {p['상품ID']} {p['상품명']}: 제외 ({reason})")
            continue
        _, _, base_total = _savings(monthly_amount, months, p["기본금리"])
        _, _, max_total = _savings(monthly_amount, months, p["최고금리"])
        rows.append((max_total, f"- {p['상품ID']} {p['은행']} {p['상품명']} ({p['종류']}) | "
                                f"기본 {p['기본금리']}% → 만기 약 {_won(base_total)} | "
                                f"최고 {p['최고금리']}% → 만기 약 {_won(max_total)} | 우대: {p['우대조건']}"))
    head = f"조건: 월 {_won(monthly_amount)}, {months}개월" + (f", 만 {age}세" if age else "") + " (모두 가상 상품, 세후 금액)"
    if not rows:
        return head + "\n가입 가능한 상품이 없습니다. 기간이나 월 납입액을 바꿔 보라고 안내하세요.\n" + "\n".join(skipped)
    rows.sort(reverse=True)
    return "\n".join([head, "[가입 가능]"] + [r for _, r in rows] + (["[제외]"] + skipped if skipped else []))


ALL_TOOLS = [search_guide, calc_alba_pay, calc_savings, compare_savings_products]
