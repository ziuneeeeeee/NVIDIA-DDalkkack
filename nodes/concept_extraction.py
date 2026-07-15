"""
concept_extraction.py
──────────────────────
PDF에서 핵심 개념을 추출해 concept_bank.json(팀원2 입력 스키마)을 만든다.

원래 팀원1 담당이지만 팀원1 브랜치가 아직 없어서, 다른 팀원이 독자적으로
만든 Concept Graph 추출 로직(Map-Reduce, importance 등급, 선수/관련 개념)을
포팅해 팀원2 스키마(concept_bank.json: concept_id/concept_name/
concept_summary/source_title/source_pages/source_context)에 얹었다.

정책 (포팅 원본과 동일):
  - 개념 개수를 강제하지 않는다. 문서가 실제로 담고 있는 만큼만 추출한다.
  - MAP(gpt-4o-mini, 청크별 병렬 후보 추출) → REDUCE(gpt-4o, 통합·구조화)
"""

from __future__ import annotations

import concurrent.futures
from typing import Literal

from pydantic import BaseModel

from core.clients import get_openai_client

Importance = Literal["core", "important", "supplementary"]
VALID_IMPORTANCE: set[str] = {"core", "important", "supplementary"}

CHUNK_CHAR_LIMIT = 12_000
MAP_MODEL = "gpt-4o-mini"
REDUCE_MODEL = "gpt-4o"
MAP_MAX_WORKERS = 5
REDUCE_MAX_TOKENS = 8_000


# ── OpenAI Structured Outputs 전송용 모델 ────────────────────────
# (strict json_schema는 minItems/maxItems/ge 같은 제약을 지원하지 않아
#  전송용 모델에는 절대 넣지 않는다. 저장용 검증은 별도로 한다.)

class CandidateConcept(BaseModel):
    name: str
    summary: str
    page_start: int
    page_end: int
    key_facts: list[str]


class CandidateConceptBatch(BaseModel):
    concepts: list[CandidateConcept]


class DraftConcept(BaseModel):
    name: str
    summary: str
    importance: Literal["core", "important", "supplementary"]
    page_start: int
    page_end: int
    learning_objectives: list[str]
    key_facts: list[str]
    prerequisites: list[str]
    related_concepts: list[str]


class ConceptGraphDraft(BaseModel):
    concepts: list[DraftConcept]


def _parsed_or_error(response, context: str):
    choice = response.choices[0]
    message = choice.message
    if getattr(message, "refusal", None):
        raise ValueError(f"{context}: 모델이 요청을 거부했습니다 ({message.refusal}).")
    if choice.finish_reason == "length":
        raise ValueError(f"{context}: 출력이 max_tokens로 잘렸습니다.")
    if message.parsed is None:
        raise ValueError(f"{context}: 구조화된 결과를 파싱하지 못했습니다.")
    return message.parsed


# ── PDF 페이지 → 청크 (약 12,000자 단위, 페이지 경계 보존) ────────

def _page_chunks(pages: list[dict]) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    current_pages: list[int] = []
    current_text: list[str] = []
    current_size = 0

    for page in pages:
        page_number, text = page["page"], page["text"]
        if current_text and current_size + len(text) > CHUNK_CHAR_LIMIT:
            chunks.append((current_pages[0], current_pages[-1], "\n\n".join(current_text)))
            current_pages, current_text, current_size = [], [], 0
        current_pages.append(page_number)
        current_text.append(f"[Page {page_number}]\n{text}")
        current_size += len(text)

    if current_text:
        chunks.append((current_pages[0], current_pages[-1], "\n\n".join(current_text)))
    return chunks


# ── MAP: 청크별 후보 개념 추출 (병렬) ─────────────────────────────

def _extract_candidates_for_chunk(chunk: tuple[int, int, str]) -> list[CandidateConcept]:
    start_page, end_page, text = chunk
    client = get_openai_client()
    response = client.beta.chat.completions.parse(
        model=MAP_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract teachable concepts from course material. Return only concepts "
                    "explicitly supported by the supplied pages. Keep original technical terminology."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Extract up to 8 distinct, important concepts from pages {start_page}-{end_page}. "
                    "For each, provide a concise summary, exact page range, and 1-3 key facts.\n\n"
                    f"{text}"
                ),
            },
        ],
        response_format=CandidateConceptBatch,
    )
    parsed = _parsed_or_error(response, f"후보 추출(p.{start_page}-{end_page})")
    return parsed.concepts


def _extract_candidates(chunks: list[tuple[int, int, str]]) -> list[CandidateConcept]:
    candidates: list[CandidateConcept] = []
    errors: list[str] = []
    max_workers = min(MAP_MAX_WORKERS, max(1, len(chunks)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_extract_candidates_for_chunk, chunk): chunk for chunk in chunks}
        for future in concurrent.futures.as_completed(futures):
            try:
                candidates.extend(future.result())
            except Exception as error:  # 청크 하나 실패해도 전체를 죽이지 않는다
                chunk = futures[future]
                errors.append(f"p.{chunk[0]}-{chunk[1]}: {error}")

    if not candidates:
        detail = " / ".join(errors) if errors else "후보 없음"
        raise ValueError(f"PDF에서 분석 가능한 개념 후보를 찾지 못했습니다. ({detail})")
    return candidates


# ── REDUCE: 후보 → 최종 개념 목록 (개수 강제 없음) ────────────────

def _reduce_to_draft(source_name: str, candidates: list[CandidateConcept]) -> list[DraftConcept]:
    import json as _json
    candidate_text = _json.dumps([c.model_dump() for c in candidates], ensure_ascii=False)
    client = get_openai_client()
    response = client.beta.chat.completions.parse(
        model=REDUCE_MODEL,
        max_tokens=REDUCE_MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a curriculum designer.\n"
                    "Extract every essential learning concept required to understand this document.\n"
                    "Each concept must represent one teachable learning unit.\n"
                    "Do not split concepts unnecessarily. Do not merge unrelated concepts.\n"
                    "The number of concepts should naturally depend on the document "
                    "(it may be few or many — do not target a fixed count).\n\n"
                    "Work only from the provided candidates: do not invent concepts or facts, and "
                    "preserve page ranges from the candidates. For each concept give a concise summary, "
                    "1-4 learning_objectives, and 1-5 source-supported key_facts. Fill prerequisites and "
                    "related_concepts with the NAMES of other concepts in your own output (empty lists if "
                    "none).\n\n"
                    "For each concept also assign an 'importance' GRADE (not a numeric score), one of:\n"
                    "  - 'core': indispensable; the document cannot be understood without it.\n"
                    "  - 'important': strongly supports the core concepts.\n"
                    "  - 'supplementary': helpful context, examples, or side notes.\n"
                    "Every field is required for every concept."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Source: {source_name}\n\nCandidates:\n{candidate_text}\n\n"
                    "Return the learning concepts this document actually teaches — as many as the "
                    "material genuinely requires, no more and no fewer."
                ),
            },
        ],
        response_format=ConceptGraphDraft,
    )
    parsed = _parsed_or_error(response, "개념 통합")
    return parsed.concepts


# ── 정규화: concept_bank.json 스키마(+확장 필드)로 변환 ───────────
#   허용: 이름 중복 제거, 페이지 범위 clamp, importance 보정, dangling edge 제거
#   금지: 개수 맞추기 위한 추가/삭제

def _clamp_pages(start: int, end: int, max_page: int) -> tuple[int, int]:
    start = max(1, min(int(start or 1), max_page))
    end = max(1, min(int(end or start), max_page))
    if end < start:
        start, end = end, start
    return start, end


def _norm_importance(value: str) -> str:
    v = (value or "").strip().lower()
    return v if v in VALID_IMPORTANCE else "important"


def _normalize_to_concept_bank(
    source_name: str,
    drafts: list[DraftConcept],
    max_page: int,
) -> list[dict]:
    ordered: list[DraftConcept] = []
    seen: set[str] = set()
    for draft in drafts:
        key = draft.name.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            ordered.append(draft)

    if not ordered:
        raise ValueError("PDF에서 유효한 개념을 하나도 만들지 못했습니다.")

    valid_names = {item.name.casefold().strip() for item in ordered}

    def _edges(names: list[str], self_name: str) -> list[str]:
        result, dedup = [], set()
        for name in names:
            key = (name or "").casefold().strip()
            if key and key != self_name.casefold().strip() and key in valid_names and key not in dedup:
                dedup.add(key)
                result.append(name)
        return result

    concept_bank: list[dict] = []
    for index, item in enumerate(ordered):
        page_start, page_end = _clamp_pages(item.page_start, item.page_end, max_page)
        objectives = [t for t in item.learning_objectives if t and t.strip()][:4] or [f"{item.name} 이해하기"]
        facts = [t for t in item.key_facts if t and t.strip()][:5] or [item.summary.strip() or item.name]

        concept_bank.append({
            # ── 팀원2(type_mapping.py) 기존 필수 스키마 ──
            "concept_id": f"concept_{index:04d}",
            "concept_name": item.name.strip(),
            "concept_summary": item.summary.strip(),
            "source_title": source_name,
            "source_pages": list(range(page_start, page_end + 1)),
            "source_context": " ".join(facts),   # 분류 근거로 쓸 수 있는 사실 텍스트
            # ── ㅇㅇ 팀원 버전에서 가져온 확장 필드 ──
            "importance": _norm_importance(getattr(item, "importance", "important")),
            "learning_objectives": objectives,
            "key_facts": facts,
            "prerequisites": _edges(item.prerequisites, item.name),
            "related_concepts": _edges(item.related_concepts, item.name),
        })
    return concept_bank


def extract_concepts_from_pdf(pages: list[dict], source_name: str) -> list[dict]:
    """PDF 페이지 리스트(scripts/ingest.load_pdf 결과)를 받아 concept_bank.json
    형식(list[dict])으로 핵심 개념을 추출한다. 개수는 강제하지 않는다."""
    if not pages:
        raise ValueError("추출할 페이지가 없습니다.")
    max_page = max(p["page"] for p in pages)
    candidates = _extract_candidates(_page_chunks(pages))
    drafts = _reduce_to_draft(source_name, candidates)
    return _normalize_to_concept_bank(source_name, drafts, max_page)
