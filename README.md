# 알바머니 도우미

아르바이트하는 대학생이 **"이번 달 알바비가 맞게 들어왔나?"**와 **"남는 돈을 어디에 모을까?"**를 혼자 확인할 수 있게 돕는 AI 에이전트.
로컬 LLM(Ollama)이 질문을 보고 도구를 골라 실행하고, 안내 문서를 근거로 답한다.

## 사용한 기술 (5개 + 멀티 에이전트)
| 기술 | 프로젝트에서 하는 일 | 코드 |
|---|---|---|
| **RAG** | 주휴수당·최저임금·3.3% 세금·적금 기초·재무 관리·가상 상품 설명서·금융사기 문서를 검색해 답의 근거로 사용 | `rag.py`, `tools.search_guide` |
| **도구 호출** | 알바비(기본급+주휴수당−3.3%), 예산(50/30/20), 적금 만기 계산, 조건에 맞는 적금 상품 비교 | `tools.py` |
| **LangGraph** | 라우터가 질문을 💼 머니 코치 / 🏦 상품 매칭 에이전트로 분기, 상품 비교 전 **사람 확인(interrupt)** | `graph.py` |
| **CrewAI** | "월간 재무 리포트" 요청 시에만 분석가 → 상품 리서처 → 검토자 3명이 순서대로 보고서 작성 (도구는 같은 MCP 서버) | `crew_report.py` |
| **MCP (자체 서버)** | 도구 5개를 표준 MCP 서버로 제공 → 에이전트가 서버에서 도구 목록을 받아 실행. Claude 데스크톱 등 다른 앱에도 연결 가능 | `mcp_server.py`, `mcp_client.py` |

**멀티 에이전트 흐름** (`graph.py`)
```
START → router ─┬─ 💼 머니 코치  (알바비·예산·재무 관리)   도구: calc_alba_pay, plan_budget, calc_savings, search_guide
                ├─ 🏦 상품 매칭  (조건에 맞는 적금 순위)   도구: compare_savings_products, calc_savings, search_guide
                ├─ both: 머니 코치 → 상품 매칭
                └─ report: 📊 값 모으기(정규식) → 빠지면 되묻기 → ⏸ 확인 → CrewAI 팀(분석가→리서처→검토자)
각 에이전트: agent ⇄ tools  (상품 비교 요청이면 confirm ⏸ 사람 확인 후 실행)
```
```
에이전트(graph.py) ──list_tools / call_tool──▶ mcp_client.py ──stdio──▶ mcp_server.py ──▶ tools.py
   판단·권한·검증·사람 확인                                            계산·검색만
```
`set TOOL_BACKEND=local` 이면 MCP 없이 tools.py 를 직접 부른다 (비교용). 다른 앱 연결: `docs/MCP_다른앱에서_쓰기.md`

**코드로 막는 안전장치(가드)**: 담당자별 도구 권한 · 사용자가 말하지 않은 금액으로 계산 금지 · 문서 없이 설명하면 되돌림 ·
근거 없는 금액이 답에 나오면 한 번 고치게 하고, 그래도 남으면 그 줄 삭제 · 개인정보 가림.
`python app.py --single` 로 예전 단일 에이전트(`agent.py`)도 실행할 수 있다.

로컬 LLM: Ollama 전용 모델 `alba-agent` (qwen3:14b 기반, 기본) · 8GB GPU 는 `qwen2.5:7b` · 웹 데모: Gradio

## 구조
```
config.py          모델 이름, 최저시급, 세율 등 설정값
rag.py             문서 → 청크 → 임베딩(bge-m3) → 코사인 검색 (임베딩 없으면 키워드 검색)
tools.py           도구 5개 + 금액 검증 가드
agent.py           단일 에이전트 루프, Ollama 호출, 개인정보 가림 (graph.py 가 부품으로 사용)
graph.py           LangGraph 멀티 에이전트 (라우터 · 머니 코치 · 상품 매칭 · 사람 확인)
crew_report.py     CrewAI 월간 재무 리포트 (에이전트 3명, MCP 도구, 금액·기간 가드)
mcp_server.py      MCP 서버 (FastMCP, stdio) — tools.py 를 표준 도구로 내보내는 '도구 창고'
mcp_client.py      MCP 클라이언트 — 서버를 켜고 연결을 유지하며 list_tools / call_tool
app.py             Gradio 화면 (왼쪽 상담 / 오른쪽 실행 로그 / 확인 버튼)
ui_theme.py        SF 네온 디자인 (CSS·헤더)
data/docs/*.md     RAG 문서 (공공 안내 자료를 팀이 정리 + 가상 상품 설명서)
data/products.json 가상 은행 적금·예금 상품 표
tests/             LLM 없이 도는 테스트 (계산값·검색·개인정보·루프)
docs/              제안서, 시나리오, 보안·윤리, AI 활용 기록
(수업 자료 PDF·노트북은 저작권 때문에 저장소에 넣지 않음 — 각자 LMS 에서 받기)
```

## 실행 방법 (Windows, 내 PC — 더블클릭)
1. [Ollama](https://ollama.com)와 Python 3.10 이상을 설치한다.
2. **`setup.bat`** 더블클릭 — 가상환경(.venv)·패키지 설치, 모델 받기(약 10GB), 전용 모델 `alba-agent` 만들기, 테스트까지 한 번에. (처음 한 번만)
3. **`run.bat`** 더블클릭 — 브라우저에 `http://localhost:7860` 이 열린다. 끄려면 검은 창을 닫는다.

전용 모델 `alba-agent` = qwen3:14b + temperature 0 + 문맥 8192 (`ollama/Modelfile`). VRAM 16GB 기준.
8GB GPU 라면 run.bat 실행 전에 `set CHAT_MODEL=qwen2.5:7b`.

### 인터넷으로 공유하기 (휴대폰·팀원·교수님)
**`share.bat`** 더블클릭 → 창에 `https://....trycloudflare.com` 주소가 나온다 (로그인 없이 바로 사용).
- 비밀번호를 걸려면 명령창에서 `share.bat lock` → 아이디 `alba` + 실행할 때마다 바뀌는 비밀번호.
- Cloudflare 임시 터널을 쓴다 (계정 불필요, 처음 한 번 `winget install --id Cloudflare.cloudflared`).
- 실행할 때마다 주소가 바뀐다. 창을 닫으면 주소가 사라진다. 주소는 믿을 수 있는 사람에게만.
- 접속한 사람마다 대화 기억이 따로 관리된다 (`gr.State`).
- Gradio 기본 공유(`--share`, *.gradio.live)는 Windows 스마트 앱 컨트롤이 켜진 PC에서 막혀서 이 방식을 쓴다.

## 실행 방법 (GPU 서버)
```bash
ollama pull qwen3:14b
ollama pull bge-m3
ollama create alba-agent -f ollama/Modelfile
pip install -r requirements.txt
python tests/test_offline.py      # LLM 없이 계산·검색 테스트
python tests/run_scenarios.py     # 실제 모델로 시연 시나리오 7개 (결과 예: tests/scenario_result_qwen2.5.txt)
python app.py
```
브라우저에서 `http://<서버주소>:7860` 접속. 모델을 바꾸려면 `CHAT_MODEL=exaone3.5:7.8b python app.py` (Windows PowerShell은 `$env:CHAT_MODEL="exaone3.5:7.8b"`).

## 데이터 안내
- 은행 상품(`products.json`, `04_가상은행_상품설명서.md`)은 **시연용 가상 데이터**다. 실제 은행·상품이 아니다.
- 법·제도 문서는 고용노동부·국세청·금융감독원 공개 안내를 팀이 쉬운 말로 정리한 것이다. 2026년 최저시급 10,320원 기준.
- 사용자 개인정보는 수집·저장하지 않는다. 대화는 메모리에만 있고 서버를 끄면 사라진다.
