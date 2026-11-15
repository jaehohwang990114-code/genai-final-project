# 💸 알바머니 도우미

아르바이트하는 대학생이 **"이번 달 알바비가 맞게 들어왔나?"**와 **"남는 돈을 어디에 모을까?"**를 혼자 확인할 수 있게 돕는 AI 에이전트.
로컬 LLM(Ollama)이 질문을 보고 도구를 골라 실행하고, 안내 문서를 근거로 답한다.

## 사용한 기술 (2개)
| 기술 | 프로젝트에서 하는 일 | 코드 |
|---|---|---|
| **RAG** | 주휴수당·최저임금·3.3% 세금·적금 기초·가상 상품 설명서·금융사기 문서를 검색해 답의 근거로 사용 | `rag.py`, `tools.search_guide` |
| **도구 호출** | 알바비(기본급+주휴수당−3.3%) 계산, 적금 만기 계산, 조건에 맞는 적금 상품 비교 | `tools.py`, `agent.run_agent` |

로컬 LLM: Ollama `qwen2.5:7b` (기본) 또는 `exaone3.5:7.8b` · 웹 데모: Gradio

## 구조
```
config.py          모델 이름, 최저시급, 세율 등 설정값
rag.py             문서 → 청크 → 임베딩(bge-m3) → 코사인 검색 (임베딩 없으면 키워드 검색)
tools.py           도구 4개 (search_guide, calc_alba_pay, calc_savings, compare_savings_products)
agent.py           시스템 프롬프트 + 도구 호출 루프 + 대화 기억 + 개인정보 가림
app.py             Gradio 화면 (왼쪽 상담 / 오른쪽 도구 실행 로그)
data/docs/*.md     RAG 문서 (공공 안내 자료를 팀이 정리 + 가상 상품 설명서)
data/products.json 가상 은행 적금·예금 상품 표
tests/             LLM 없이 도는 테스트 (계산값·검색·개인정보·루프)
docs/              제안서, 시나리오, 보안·윤리, AI 활용 기록
```

## 실행 방법 (GPU 서버)
```bash
ollama pull qwen2.5:7b
ollama pull bge-m3
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
