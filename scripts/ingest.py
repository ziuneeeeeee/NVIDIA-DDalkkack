"""
ingest.py
──────────
강의자료 PDF, 녹음 파일, 또는 녹화강의 영상을 RAG용 DB에 인덱싱하는 스크립트.

사용법:
  python ingest.py --pdf 강의자료.pdf
  python ingest.py --audio 강의녹음.m4a
  python ingest.py --video 강의녹화.mp4
  python ingest.py --pdf slides.pdf --collection lecture_notes

흐름 (PDF):
  PDF 로드 → 페이지별 텍스트 추출
  → 청크 분할 (400단어, 80단어 오버랩)
  → OpenAI 임베딩 생성 (text-embedding-3-small)
  → ChromaDB에 벡터 저장
  → BM25 인덱스 빌드 & pickle 저장

흐름 (녹음/영상):
  (영상이면 ffmpeg로 오디오 트랙만 추출 → 이후 녹음과 동일)
  Whisper로 전사(timestamp 포함) → 3분 구간별로 페이지처럼 묶음
  → 이후 PDF와 동일하게 청크 분할 → 임베딩 → 저장
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


class IngestError(Exception):
    """인덱싱 중 사용자에게 그대로 보여줘야 하는 오류 (API/CLI 공용)."""


# ── 설정 ─────────────────────────────────────────────────────────
CHROMA_PATH      = "./chroma_db"
BM25_PATH        = "./bm25_index.pkl"
COLLECTION_NAME  = "lecture_notes"
EMBEDDING_MODEL  = "text-embedding-3-small"
CHUNK_SIZE       = 400   # 청크 당 단어 수
CHUNK_OVERLAP    = 80    # 인접 청크 오버랩 단어 수
MIN_CHUNK_WORDS  = 20    # 이보다 짧은 청크는 버림
EMBED_BATCH_SIZE = 100   # 임베딩 API 배치 크기
AUDIO_PAGE_WINDOW_SECONDS = 180   # 녹음을 몇 초 단위로 묶어 "페이지"처럼 취급할지
WHISPER_MODEL    = "whisper-1"
# OpenAI 오디오 전사 API 업로드 용량 제한 (초과 시 명확한 에러로 안내)
MAX_AUDIO_BYTES  = 25 * 1024 * 1024


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
# Step 1-b. 녹화강의 영상 → 오디오 트랙 추출 (ffmpeg)
# ──────────────────────────────────────────────────────────────────

def extract_audio_from_video(video_path: str) -> str:
    """영상에서 오디오 트랙만 ffmpeg로 추출해 임시 mp3 파일 경로를 반환한다.
    이후 load_audio()에 그대로 넘기면 녹음파일과 동일하게 처리된다."""
    import shutil
    import subprocess
    import tempfile as _tempfile

    if shutil.which("ffmpeg") is None:
        raise IngestError(
            "영상에서 소리를 추출하려면 ffmpeg가 필요한데 이 컴퓨터에 설치돼 있지 않습니다. "
            "https://ffmpeg.org 에서 설치한 뒤 다시 시도하세요."
        )

    audio_path = _tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "4", audio_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise IngestError(f"영상에서 오디오를 추출하지 못했습니다: {result.stderr[-800:]}")
    return audio_path


# ──────────────────────────────────────────────────────────────────
# Step 1-c. 녹음 파일 로드 (Whisper 전사)
# ──────────────────────────────────────────────────────────────────

def _format_timestamp(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def _group_segments_into_pages(segments, window_seconds: int = AUDIO_PAGE_WINDOW_SECONDS) -> list[dict]:
    """Whisper verbose_json 세그먼트를 시간 구간별로 묶어 PDF의 '페이지'와
    동일한 구조({"page": ..., "text": ...})로 변환한다. page 필드에는
    실제 페이지 번호 대신 타임스탬프 구간 문자열이 들어간다."""
    pages: list[dict] = []
    window_start = 0.0
    buffer: list[str] = []

    def _get(seg, key):
        return seg[key] if isinstance(seg, dict) else getattr(seg, key)

    for seg in segments:
        start, text = _get(seg, "start"), _get(seg, "text")
        if buffer and (start - window_start) >= window_seconds:
            pages.append({"page": _format_timestamp(window_start), "text": " ".join(buffer).strip()})
            window_start = start
            buffer = []
        buffer.append(text.strip())
    if buffer:
        pages.append({"page": _format_timestamp(window_start), "text": " ".join(buffer).strip()})
    return pages


def load_audio(path: str, client) -> list[dict]:
    """녹음 파일을 Whisper API로 전사하고, 시간 구간별 '페이지' 리스트로 변환."""
    size = os.path.getsize(path)
    if size > MAX_AUDIO_BYTES:
        raise IngestError(
            f"파일이 너무 큽니다 ({size / 1024 / 1024:.1f}MB). "
            f"OpenAI 오디오 전사 API는 25MB까지만 지원합니다. "
            f"파일을 나누거나 더 낮은 비트레이트로 변환한 뒤 다시 시도하세요."
        )

    with open(path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=f,
            response_format="verbose_json",
        )

    segments = transcript.segments if hasattr(transcript, "segments") else transcript["segments"]
    pages = _group_segments_into_pages(segments)
    total_seconds = getattr(transcript, "duration", None)
    duration_str = f"{total_seconds:.0f}초" if total_seconds else "알 수 없음"
    print(f"  녹음 전사 완료: {len(pages)}개 구간 (재생시간 {duration_str})")
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

def ingest(
    pdf_path: str | None = None,
    collection_name: str = COLLECTION_NAME,
    audio_path: str | None = None,
    video_path: str | None = None,
) -> dict:
    """PDF, 오디오, 또는 영상을 인덱싱한다. 성공 시 요약 dict를 반환한다
    (API 응답으로 그대로 쓸 수 있도록)."""
    cleanup_path = None
    if video_path:
        print("\n[0/4] 영상에서 오디오 트랙 추출 중...")
        audio_path = extract_audio_from_video(video_path)
        cleanup_path = audio_path

    source_path = pdf_path or audio_path or video_path
    if not source_path or not os.path.exists(pdf_path or video_path or audio_path):
        raise IngestError(f"파일을 찾을 수 없습니다: {source_path}")

    try:
        print(f"\n📄 인덱싱 시작: {video_path or source_path}")
        client = get_openai_client()

        if audio_path:
            print("\n[1/4] 녹음 전사 중... (파일 길이에 따라 시간이 걸릴 수 있습니다)")
            pages = load_audio(audio_path, client)
            source_type = "video" if video_path else "audio"
        else:
            print("\n[1/4] PDF 로드 중...")
            pages = load_pdf(pdf_path)
            source_type = "pdf"

        print("\n[2/4] 청크 분할 중...")
        chunks = chunk_pages(pages)
        if not chunks:
            raise IngestError("추출된 텍스트가 없습니다. 파일에 인식 가능한 내용이 있는지 확인하세요.")

        print("\n[3/4] 임베딩 생성 중...")
        embeddings = build_embeddings([c["text"] for c in chunks], client)

        print("\n[4/4] DB 저장 중...")
        store_chroma(chunks, embeddings, collection_name)
        store_bm25(chunks)

        print(f"\n✅ 인덱싱 완료! 총 {len(chunks)}개 청크가 저장되었습니다.")

        return {
            "source_type": source_type,
            "source_path": video_path or source_path,
            "page_count": len(pages),
            "chunk_count": len(chunks),
            "collection": collection_name,
        }
    finally:
        # 영상에서 추출한 임시 오디오 파일 정리
        if cleanup_path and os.path.exists(cleanup_path):
            os.remove(cleanup_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="강의자료 PDF, 녹음, 또는 영상을 RAG용 DB에 인덱싱합니다.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf",   help="인덱싱할 PDF 파일 경로")
    source.add_argument("--audio", help="인덱싱할 녹음 파일 경로 (mp3/m4a/wav 등, 25MB 이하)")
    source.add_argument("--video", help="인덱싱할 녹화강의 영상 경로 (오디오만 자동 추출)")
    parser.add_argument("--collection", default=COLLECTION_NAME, help="ChromaDB 컬렉션 이름")
    args = parser.parse_args()
    try:
        ingest(pdf_path=args.pdf, collection_name=args.collection, audio_path=args.audio, video_path=args.video)
        print("   이제 'python main.py' 또는 'uvicorn api:app --reload'를 실행하세요.\n")
    except IngestError as e:
        print(f"❌ {e}")
        sys.exit(1)
