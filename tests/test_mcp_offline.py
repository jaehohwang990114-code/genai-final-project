"""MCP 서버·클라이언트 확인 (LLM 없이).

실행: python tests/test_mcp_offline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools
from mcp_client import MCPToolClient

client = MCPToolClient()


def test_lists_five_tools():
    names = set(client.list_tools())
    assert names == {"search_guide", "calc_alba_pay", "calc_savings", "compare_savings_products", "plan_budget"}


def test_schema_has_arg_descriptions():
    """모델이 읽는 설명서에 인자 설명·필수값이 들어 있어야 도구를 제대로 고른다."""
    s = client.list_tools()["calc_alba_pay"]["function"]
    props = s["parameters"]["properties"]
    assert "시급" in props["hourly_wage"]["description"]
    assert set(s["parameters"]["required"]) == {"hourly_wage", "hours_per_week"}
    assert "주휴수당" in s["description"]


def test_same_result_as_local():
    """MCP 로 실행한 결과 = 함수를 직접 실행한 결과."""
    args = {"monthly_amount": 100000, "months": 12, "age": 22}
    assert client.call_tool("compare_savings_products", args) == tools.compare_savings_products.invoke(args)
    args = {"hourly_wage": 10320, "hours_per_week": 20, "tax_33": True}
    assert "1,040,713" in client.call_tool("calc_alba_pay", args)


def test_bad_args_return_error_text():
    out = client.call_tool("calc_savings", {"monthly_amount": "많이"})
    assert out.startswith("[도구 실행 오류]")


if __name__ == "__main__":
    n = 0
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                fn(); print("PASS", name); n += 1
    finally:
        client.close()
    print(f"\n{n}개 MCP 테스트 모두 통과")
