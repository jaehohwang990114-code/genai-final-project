"""MCP 클라이언트 — 에이전트가 MCP 서버(mcp_server.py)에 접속해 도구를 쓰는 창구.

    에이전트(graph.py) ──list_tools / call_tool──▶ 이 클라이언트 ──stdio(JSON-RPC)──▶ mcp_server.py ──▶ tools.py

MCP SDK 는 비동기(async)인데 Gradio·LangGraph 코드는 동기라서, 별도 스레드에 이벤트 루프를 하나 띄워
서버 연결(세션)을 계속 유지하고, 동기 함수 list_tools()/call_tool() 이 그 루프에 일을 맡기고 결과를 기다린다.
서버는 처음 한 번만 켜고 계속 재사용한다 (요청마다 켜면 느림).
"""
import asyncio
import atexit
import sys
import threading
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).parent / "mcp_server.py"


class MCPToolClient:
    def __init__(self, server_path=SERVER):
        self.params = StdioServerParameters(command=sys.executable, args=[str(server_path)],
                                            cwd=str(Path(server_path).parent))
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True, name="mcp-client").start()
        self.session = None
        self._schemas = None
        self._ready = threading.Event()
        self._main_future = asyncio.run_coroutine_threadsafe(self._main(), self.loop)
        if not self._ready.wait(60):
            raise RuntimeError("MCP 서버에 연결하지 못했습니다.")

    def _run(self, coro, timeout=120):
        """비동기 작업을 백그라운드 루프에 맡기고 결과를 기다린다."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _main(self):
        """연결을 여는 일과 닫는 일을 한 작업 안에서 한다 (MCP SDK 규칙). 종료 신호가 올 때까지 연결 유지."""
        self._stop = asyncio.Event()
        async with stdio_client(self.params) as (read, write):          # ① 서버 프로세스 켜기
            async with ClientSession(read, write) as session:
                await session.initialize()                              # ② 악수(초기화)
                self.session = session
                self._ready.set()
                await self._stop.wait()                                 # 앱이 끝날 때까지 연결 유지

    def list_tools(self):
        """③ 서버가 가진 도구 목록 → Ollama 가 읽는 도구 설명서(JSON 스키마) 형식으로 바꿔 돌려준다."""
        if self._schemas is None:
            result = self._run(self.session.list_tools())
            self._schemas = {t.name: {"type": "function", "function": {
                "name": t.name, "description": t.description or "", "parameters": t.inputSchema}}
                for t in result.tools}
        return self._schemas

    def call_tool(self, name, args):
        """④ 서버에 도구 실행을 요청하고 결과 글을 돌려준다."""
        result = self._run(self.session.call_tool(name, args or {}))
        text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
        return f"[도구 실행 오류] {text}" if result.isError else text

    def close(self):
        self.loop.call_soon_threadsafe(self._stop.set)                 # 종료 신호 → _main 이 연결을 닫음
        try:
            self._main_future.result(10)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)


_client = None
_lock = threading.Lock()


def get_client():
    """앱 전체에서 MCP 연결 하나를 같이 쓴다 (처음 부를 때 서버를 켬)."""
    global _client
    with _lock:
        if _client is None:
            _client = MCPToolClient()
            atexit.register(_client.close)                     # 앱이 꺼질 때 MCP 서버 프로세스도 같이 끈다
        return _client


if __name__ == "__main__":                                   # python mcp_client.py 로 서버 연결 확인
    c = get_client()
    print("MCP 서버 도구:", list(c.list_tools()))
    print(c.call_tool("calc_alba_pay", {"hourly_wage": 10320, "hours_per_week": 20}))
    c.close()
