# MCP 서버를 다른 앱에서 쓰기

`mcp_server.py` 는 표준 MCP 서버라서, 우리 에이전트(graph.py)뿐 아니라 MCP 를 지원하는 다른 앱에도 그대로 연결된다.
발표 때 "도구를 한 번 만들면 어떤 AI 앱에서도 쓸 수 있다"를 보여 주는 시연용.

## 1. 우리 에이전트에서 (기본)
`config.TOOL_BACKEND = "mcp"` → `mcp_client.py` 가 서버를 하위 프로세스로 켜고 stdio 로 통신한다.
화면 오른쪽 로그에 `[Function Call] calc_alba_pay (via MCP)` 처럼 표시된다.
비교용으로 `set TOOL_BACKEND=local` 후 실행하면 MCP 없이 함수를 직접 부른다.

## 2. Claude 데스크톱 앱에서
Claude 데스크톱 → 설정 → 개발자 → 구성 편집 (`claude_desktop_config.json`) 에 아래를 추가하고 앱을 다시 켠다.
경로는 본인 PC 의 저장소 위치로 바꾼다. (팀원이 MCP 앱 연결을 시연하고 싶을 때만)

```json
{
  "mcpServers": {
    "alba-money-tools": {
      "command": "C:\\경로\\alba-money-agent\\.venv\\Scripts\\python.exe",
      "args": ["C:\\경로\\alba-money-agent\\mcp_server.py"]
    }
  }
}
```
연결되면 Claude 에게 "시급 10320원에 주 20시간이면 한 달 얼마야?"라고 물었을 때 `calc_alba_pay` 도구를 쓰는 것을 볼 수 있다.

## 3. 서버만 직접 확인
```bash
python mcp_client.py
```
→ 서버의 도구 5개 목록과 알바비 계산 결과가 출력되면 정상.

## 설계 메모 (발표 설명용)
- **서버 = 계산만**: 알바비·예산·적금 계산, 상품 비교, 문서 검색 (tools.py 를 MCP 용으로 얇게 포장)
- **클라이언트(에이전트) = 판단·통제**: 어느 도구를 쓸지, 누가 쓸 수 있는지(권한), 금액이 사용자 말에 있는지(검증), 사람 확인
- 그래서 다른 앱이 서버를 쓰더라도 계산 결과는 같고, 안전장치는 각 앱(클라이언트)이 책임진다.
