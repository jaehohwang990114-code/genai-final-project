"""RAG — 팀이 모은 안내 문서를 검색해 답변의 근거로 쓴다.

흐름: ① 문서 읽기 → ② '## 소제목' 단위로 자르기(청크) → ③ 청크마다 임베딩 벡터 만들기
      → ④ 질문도 벡터로 바꿔 코사인 유사도가 높은 청크 top_k 개 돌려주기

임베딩 모델(Ollama bge-m3)이 없으면 ③④ 대신 '글자 2개 묶음(바이그램) 겹침' 점수로 검색한다.
→ 서버에 임베딩 모델이 없어도 시연이 멈추지 않게 하기 위한 안전장치.
"""
import sys
from pathlib import Path

import numpy as np
import requests

import config

DOCS_DIR = Path(__file__).parent / "data" / "docs"


# ① + ② 문서를 읽어 청크로 자르기 ────────────────────────────────
def load_chunks(docs_dir=DOCS_DIR):
    """각 .md 파일을 '## ' 소제목 단위로 잘라 [{'source', 'title', 'text'}] 로 돌려준다."""
    chunks = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        doc_title = path.stem
        for part in path.read_text(encoding="utf-8").split("\n## ")[1:]:   # 첫 조각은 문서 제목·출처라 건너뜀
            title, _, body = part.partition("\n")
            chunks.append({"source": doc_title, "title": title.strip(), "text": body.strip()})
    return chunks


# ③ 임베딩 ──────────────────────────────────────────────────────
def embed(texts):
    """Ollama 임베딩 API 로 문장 리스트 → (개수, 차원) 행렬. 정규화해서 내적 = 코사인 유사도."""
    res = requests.post(f"{config.OLLAMA_URL}/api/embed",
                        json={"model": config.EMBED_MODEL, "input": texts}, timeout=120)
    res.raise_for_status()
    vecs = np.array(res.json()["embeddings"], dtype=np.float32)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


def _bigrams(text):
    s = "".join(text.split())                      # 띄어쓰기 무시 ('주휴 수당' == '주휴수당')
    return {s[i:i + 2] for i in range(len(s) - 1)}


class Retriever:
    def __init__(self, docs_dir=DOCS_DIR, use_embedding=True):
        self.chunks = load_chunks(docs_dir)
        self.vectors = None
        self.mode = "keyword"
        if use_embedding:
            try:
                self.vectors = embed([f"{c['title']}\n{c['text']}" for c in self.chunks])
                self.mode = f"embedding({config.EMBED_MODEL})"
            except Exception as e:                  # 서버·모델이 없으면 키워드 검색으로
                print(f"[RAG] 임베딩 사용 불가 → 키워드 검색으로 대체합니다. ({e.__class__.__name__})", file=sys.stderr)
        print(f"[RAG] 청크 {len(self.chunks)}개 준비 완료, 검색 방식: {self.mode}", file=sys.stderr)   # stderr: MCP 서버(stdio)의 통신을 방해하지 않게

    # ④ 검색 ────────────────────────────────────────────────────
    def search(self, query, top_k=config.TOP_K, min_score=None):
        """질문과 가장 비슷한 청크 top_k 개를 [(점수, 청크)] 로. 점수가 너무 낮으면 버린다."""
        if self.vectors is not None:
            scores = self.vectors @ embed([query])[0]
            min_score = 0.45 if min_score is None else min_score
        else:
            q = _bigrams(query)
            scores = np.array([len(q & _bigrams(c["title"] + c["text"])) / (len(q) or 1)
                               for c in self.chunks])
            min_score = 0.2 if min_score is None else min_score
        order = np.argsort(-scores)[:top_k]
        return [(float(scores[i]), self.chunks[i]) for i in order if scores[i] >= min_score]


if __name__ == "__main__":                          # python rag.py 로 단독 확인
    r = Retriever()
    for q in ["주휴수당 받으려면 몇 시간 일해야 해?", "적금 이자가 왜 적어?", "오늘 날씨 어때?"]:
        print("\nQ:", q)
        hits = r.search(q)
        for score, c in hits:
            print(f"  {score:.2f} [{c['source']}] {c['title']}")
        if not hits:
            print("  (근거 문서 없음)")
