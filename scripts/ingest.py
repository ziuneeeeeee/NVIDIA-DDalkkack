"""
ingest.py
──────────
강의자료 PDF를 RAG용 DB에 인덱싱하는 스크립트.

사용법:
  python ingest.py --pdf 강의자료.pdf
  python ingest.py --pdf slides.pdf --collection lecture_notes

흐름:
  PDF 로드 → 페이지별 텍스트 추출
  → 청크 분할 (400단어, 80단어 오버랩)
  → OpenAI 임베딩 생성 (text-embedding-3-small)
  → ChromaDB에 벡터 저장
  → BM25 인덱스 빌드 & pickle 저장
"""

from __future__ import annotations

import argparse
import os
import pickle
import sys

# Windows 콘솔에서 이모지 출력 시 cp949 에러 방지
sys.stdout.reconfigure(encoding='utf-8')

# 프로젝트 루트(core 등이 있는 상위 디렉터리)를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from pypdf import PdfReader
from rank_bm25 import BM25Okapi

from core.clients import get_openai_client

# ── 설정 ─────────────────────────────────────────────────────────
CHROMA_PATH      = "./chroma_db"
BM25_PATH        = "./bm25_index.pkl"
COLLECTION_NAME  = "lecture_notes"
EMBEDDING_MODEL  = "text-embedding-3-small"
CHUNK_SIZE       = 400   # 청크 당 단어 수
CHUNK_OVERLAP    = 80    # 인접 청크 오버랩 단어 수
MIN_CHUNK_WORDS  = 20    # 이보다 짧은 청크는 버림
EMBED_BATCH_SIZE = 100   # 임베딩 API 배치 크기


# ──────────────────────────────────────────────────────────────────
# Step 1. PDF 로드
# ──────────────────────────────────────────────────────────────────

def load_pdf(path: str) -> list[dict]:
    """PDF 페이지별로 텍스트 추출."""
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append({"page": i, "text": text})
    print(f"  PDF 로드 완료: {len(pages)}페이지 (전체 {len(reader.pages)}페이지 중 텍스트 있는 페이지)")
    return pages


# ──────────────────────────────────────────────────────────────────
# Step 2. 청크 분할
# ──────────────────────────────────────────────────────────────────

def chunk_pages(pages: list[dict]) -> list[dict]:
    """슬라이딩 윈도우로 청크 분할."""
    chunks = []
    step = max(CHUNK_SIZE - CHUNK_OVERLAP, 1)
    for page in pages:
        words = page["text"].split()
        for i in range(0, max(len(words) - CHUNK_OVERLAP, 1), step):
            chunk_words = words[i : i + CHUNK_SIZE]
            if len(chunk_words) < MIN_CHUNK_WORDS:
                continue
            chunks.append({
                "text":     " ".join(chunk_words),
                "page":     page["page"],
                "chunk_id": f"p{page['page']}_c{i}",
            })
    print(f"  청크 분할 완료: {len(chunks)}개 (CHUNK_SIZE={CHUNK_SIZE}, OVERLAP={CHUNK_OVERLAP})")
    return chunks


# ──────────────────────────────────────────────────────────────────
# Step 3. 임베딩 생성
# ──────────────────────────────────────────────────────────────────

def build_embeddings(texts: list[str], client) -> list[list[float]]:
    """OpenAI Embeddings API로 벡터 생성 (배치 처리)."""
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        all_embeddings.extend([r.embedding for r in response.data])
        done = min(i + EMBED_BATCH_SIZE, len(texts))
        print(f"  임베딩 진행: {done}/{len(texts)}")
    return all_embeddings


# ──────────────────────────────────────────────────────────────────
# Step 4. ChromaDB 저장
# ──────────────────────────────────────────────────────────────────

def store_chroma(
    chunks: list[dict],
    embeddings: list[list[float]],
    collection_name: str,
) -> None:
    """ChromaDB PersistentClient에 청크 + 임베딩 저장."""
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    # 기존 컬렉션 삭제 후 재생성 (재인덱싱 시 중복 방지)
    try:
        chroma_client.delete_collection(collection_name)
        print(f"  기존 컬렉션 '{collection_name}' 삭제")
    except Exception:
        pass
    collection = chroma_client.create_collection(collection_name)
    collection.add(
        embeddings=embeddings,
        documents=[c["text"]     for c in chunks],
        ids=      [c["chunk_id"] for c in chunks],
        metadatas=[{"page": c["page"]} for c in chunks],
    )
    print(f"  ChromaDB 저장 완료 → {CHROMA_PATH}")


# ──────────────────────────────────────────────────────────────────
# Step 5. BM25 인덱스 저장
# ──────────────────────────────────────────────────────────────────

def store_bm25(chunks: list[dict]) -> None:
    """BM25Okapi 인덱스 + 코퍼스를 pickle로 저장."""
    tokenized = [c["text"].split() for c in chunks]
    bm25 = BM25Okapi(tokenized)
    payload = {
        "bm25":   bm25,
        "corpus": [c["text"] for c in chunks],
        "chunks": chunks,
    }
    with open(BM25_PATH, "wb") as f:
        pickle.dump(payload, f)
    print(f"  BM25 인덱스 저장 완료 → {BM25_PATH}")


# ──────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────

def ingest(pdf_path: str, collection_name: str = COLLECTION_NAME) -> None:
    if not os.path.exists(pdf_path):
        print(f"❌ 파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)

    print(f"\n📄 인덱싱 시작: {pdf_path}")
    client = get_openai_client()

    print("\n[1/4] PDF 로드 중...")
    pages = load_pdf(pdf_path)

    print("\n[2/4] 청크 분할 중...")
    chunks = chunk_pages(pages)
    if not chunks:
        print("❌ 추출된 텍스트가 없습니다. PDF에 텍스트 레이어가 있는지 확인하세요.")
        sys.exit(1)

    print("\n[3/4] 임베딩 생성 중...")
    embeddings = build_embeddings([c["text"] for c in chunks], client)

    print("\n[4/4] DB 저장 중...")
    store_chroma(chunks, embeddings, collection_name)
    store_bm25(chunks)

    print(f"\n✅ 인덱싱 완료! 총 {len(chunks)}개 청크가 저장되었습니다.")
    print("   이제 'python main.py' 또는 'uvicorn api:app --reload'를 실행하세요.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="강의자료 PDF를 RAG용 DB에 인덱싱합니다.")
    parser.add_argument("--pdf",        required=True, help="인덱싱할 PDF 파일 경로")
    parser.add_argument("--collection", default=COLLECTION_NAME, help="ChromaDB 컬렉션 이름")
    args = parser.parse_args()
    ingest(args.pdf, args.collection)
