"""
nodes/retrieve.py
──────────────────
강의자료에서 문제 관련 근거를 검색하는 RAG 노드.

하이브리드 검색 흐름 (MD 3.3):
  1) BM25 검색       → top-5 청크 (키워드 매칭)
  2) 벡터 검색       → top-5 청크 (의미적 유사도)
  3) 중복 제거 병합
  4) 크로스인코더 재순위화 → top-3 청크
  5) context 문자열로 합치기

사전 조건:
  ingest.py 를 먼저 실행해 chroma_db/ 와 bm25_index.pkl 을 생성해야 한다.
  python ingest.py --pdf 강의자료.pdf
"""

from __future__ import annotations

import os
import pickle

import chromadb
from sentence_transformers import CrossEncoder

from core.clients import get_openai_client
from core.state import GradingState

# ── 설정 ─────────────────────────────────────────────────────────
CHROMA_PATH     = "./chroma_db"
BM25_PATH       = "./bm25_index.pkl"
COLLECTION_NAME = "lecture_notes"
EMBEDDING_MODEL = "text-embedding-3-small"
TOP_K           = 8   # BM25 / 벡터 각각 상위 K개
TOP_N           = 3   # 재순위화 후 최종 N개

# ── 지연 로딩 (첫 retrieve 호출 시 1회만 초기화) ─────────────────
_resources: dict | None = None


def configure_index(chroma_path: str, bm25_path: str, collection_name: str = COLLECTION_NAME) -> None:
    """RAG가 검색할 인덱스를 다른 경로(예: 방(room)별 인덱스)로 전환한다.
    다음 retrieve() 호출부터 새 경로에서 다시 로드하도록 캐시를 비운다."""
    global CHROMA_PATH, BM25_PATH, COLLECTION_NAME, _resources
    CHROMA_PATH = chroma_path
    BM25_PATH = bm25_path
    COLLECTION_NAME = collection_name
    _resources = None


def _load_resources() -> dict:
    global _resources
    if _resources is not None:
        return _resources

    if not os.path.exists(BM25_PATH):
        raise FileNotFoundError(
            "RAG 인덱스가 없습니다. "
            "먼저 'python ingest.py --pdf 강의자료.pdf'를 실행하세요."
        )

    print("[retrieve] RAG 리소스 초기화 중...")

    with open(BM25_PATH, "rb") as f:
        bm25_data = pickle.load(f)

    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = chroma_client.get_collection(COLLECTION_NAME)
    reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    _resources = {
        "bm25":       bm25_data["bm25"],
        "corpus":     bm25_data["corpus"],
        "collection": collection,
        "reranker":   reranker,
    }
    print("[retrieve] RAG 리소스 초기화 완료 ✅")
    return _resources


def get_topic_overview(topic_range: str, top_k: int = 15) -> str:
    """
    특정 범위(topic_range)에 대한 강의자료 개관을 BM25로 넓게 훑어 반환.
    Orchestrator가 실제 자료에 근거해 개념을 뽑도록 근거 텍스트를 제공하는 용도.
    """
    try:
        res = _load_resources()
    except FileNotFoundError as e:
        print(f"[retrieve] ⚠️  {e}")
        return f"[인덱싱 필요] '{topic_range[:40]}...'에 관한 강의자료 내용."

    bm25_scores = res["bm25"].get_scores(topic_range.split())
    top_idx = sorted(
        range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True
    )[:top_k]
    chunks = [res["corpus"][i] for i in top_idx]
    return "\n\n---\n\n".join(chunks)


def retrieve(state: dict) -> dict:
    """
    하이브리드 RAG 검색 (BM25 + 벡터 + 크로스인코더 재순위화).

    Returns:
        {"context": str}
    """
    if "problem" in state and state["problem"]:
        question = state["problem"].question
    elif "concept" in state:
        question = state["concept"]
    else:
        question = ""


    # RAG 인덱스 없으면 PLACEHOLDER로 대체
    try:
        res = _load_resources()
    except FileNotFoundError as e:
        print(f"[retrieve] ⚠️  {e}")
        context = f"[인덱싱 필요] '{question[:40]}...'에 관한 강의자료 내용."
        return {"context": context}

    print(f"[retrieve] 검색 중: '{question[:40]}...'")
    client = get_openai_client()

    # ── 1) BM25 키워드 검색 ───────────────────────────────────────
    bm25_scores = res["bm25"].get_scores(question.split())
    bm25_top_idx = sorted(
        range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True
    )[:TOP_K]
    bm25_docs = [res["corpus"][i] for i in bm25_top_idx]

    # ── 2) 벡터 검색 ─────────────────────────────────────────────
    emb = client.embeddings.create(model=EMBEDDING_MODEL, input=[question])
    query_vec = emb.data[0].embedding
    vec_result = res["collection"].query(
        query_embeddings=[query_vec], n_results=TOP_K
    )
    vec_docs = vec_result["documents"][0]

    # ── 3) 중복 제거 병합 ─────────────────────────────────────────
    candidates = list(dict.fromkeys(bm25_docs + vec_docs))

    # ── 4) 크로스인코더 재순위화 ──────────────────────────────────
    pairs = [(question, doc) for doc in candidates]
    scores = res["reranker"].predict(pairs)
    ranked_idx = sorted(
        range(len(scores)), key=lambda i: scores[i], reverse=True
    )[:TOP_N]
    reranked = [candidates[i] for i in ranked_idx]

    context = "\n\n---\n\n".join(reranked)
    print(f"[retrieve] 검색 완료: {len(reranked)}개 청크 반환")
    return {"context": context}
