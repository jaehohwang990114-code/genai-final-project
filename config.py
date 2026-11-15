"""프로젝트 설정 — 바꿀 값은 전부 여기 한 곳에 모아 둔다."""
import os

# ── 로컬 LLM (Ollama) ─────────────────────────────────────────────
# GPU 서버에서 `ollama serve` 가 떠 있어야 한다. 주소가 다르면 환경변수로 바꾼다.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# 도구 호출(tool calling)을 지원하는 모델이어야 한다.
#   qwen2.5:7b   — 도구 호출이 안정적 (기본값)
#   exaone3.5:7.8b — 한국어 말투가 자연스러움. 도구 호출이 불안정하면 qwen 으로 되돌린다.
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen2.5:7b")

# RAG 임베딩 모델. 없으면 rag.py 가 자동으로 '글자 겹침' 검색으로 바꿔 동작한다.
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")

# ── 계산 기준값 ───────────────────────────────────────────────────
# 2026년 최저시급 (고용노동부 고시). 발표 전에 minimumwage.go.kr 에서 한 번 더 확인할 것.
MIN_WAGE = 10_320
MIN_WAGE_YEAR = 2026

TAX_33 = 0.033          # 프리랜서·사업소득 원천징수: 소득세 3% + 지방소득세 0.3%
INTEREST_TAX = 0.154    # 일반 이자소득세: 소득세 14% + 지방소득세 1.4%
WEEKS_PER_MONTH = 365 / 7 / 12   # 한 달 평균 주 수 ≈ 4.345

# ── 에이전트 ─────────────────────────────────────────────────────
MAX_ITERS = 5           # 도구 호출 반복 상한 (무한 루프 방지)
TOP_K = 3               # RAG 검색 결과 개수
