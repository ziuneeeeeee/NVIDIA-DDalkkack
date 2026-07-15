import concurrent.futures
import json
import os
import tempfile
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from core.models import Problem
from main import run_generation, run_grading
from scripts.ingest import ingest as run_ingest, load_pdf, IngestError
from nodes.concept_extraction import extract_concepts_from_pdf
from nodes.type_mapping import map_concepts_to_types
from nodes.retrieve import configure_index
from core.exam_spec import build_exam_specs
import core.rooms as rooms

app = FastAPI(title="Study Helper API")

# Add CORS middleware to allow React frontend to communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the exact domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerateRequest(BaseModel):
    concept: str
    target_difficulty: str = "중"

class GradeRequest(BaseModel):
    problem: dict
    student_answer: str

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Study Helper API is running."}

@app.post("/generate_problem")
def api_generate_problem(req: GenerateRequest):
    try:
        problem = run_generation(req.concept, req.target_difficulty)
        if not problem:
            raise HTTPException(status_code=400, detail="문제 생성에 실패했습니다. 유효하지 않은 개념이거나 내용이 부족할 수 있습니다.")
        return {"problem": problem}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

PDF_EXTENSIONS = {".pdf"}
AUDIO_EXTENSIONS = {".mp3", ".mpeg", ".mpga", ".m4a", ".wav"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

CONCEPT_BANK_PATH = "data/concept_bank.json"

@app.post("/ingest")
def api_ingest(file: UploadFile = File(...)):
    """강의자료 PDF, 녹음, 또는 녹화강의 영상을 업로드받아 RAG 인덱스
    (ChromaDB + BM25)를 새로 구축한다. PDF는 추가로 핵심 개념도 자동
    추출해 data/concept_bank.json으로 저장한다 (팀원2 유형 매핑의 입력).
    영상은 오디오 트랙만 자동 추출해 녹음파일과 동일하게 처리한다."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext in PDF_EXTENSIONS:
        kind = "pdf"
    elif ext in AUDIO_EXTENSIONS:
        kind = "audio"
    elif ext in VIDEO_EXTENSIONS:
        kind = "video"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다: '{ext or '(확장자 없음)'}'. "
                   f"PDF, 녹음 파일(mp3/mpeg/mpga/m4a/wav), 영상(mp4/mov/mkv/avi/webm)만 업로드하세요.",
        )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(file.file.read())
            tmp_path = tmp.name

        if kind == "pdf":
            summary = run_ingest(pdf_path=tmp_path)
            pages = load_pdf(tmp_path)
            concepts = extract_concepts_from_pdf(pages, file.filename)
            os.makedirs(os.path.dirname(CONCEPT_BANK_PATH), exist_ok=True)
            with open(CONCEPT_BANK_PATH, "w", encoding="utf-8") as f:
                json.dump(concepts, f, ensure_ascii=False, indent=2)
            summary["concept_count"] = len(concepts)
        elif kind == "audio":
            summary = run_ingest(audio_path=tmp_path)
        else:
            summary = run_ingest(video_path=tmp_path)

        summary["source_path"] = file.filename  # 임시 경로 대신 원본 파일명으로 치환
        return summary

    except IngestError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


CATEGORY_TO_KOREAN_TYPE = {
    "MULTIPLE_CHOICE": "객관식",
    "TRUE_FALSE": "참거짓",
    "DESCRIPTIVE": "서술형",
    "CALCULATION": "단답형",
}
MAX_ROOM_EXAM_QUESTIONS = 20


class RoomCreateRequest(BaseModel):
    name: str

class RoomRenameRequest(BaseModel):
    name: str

class RoomQuestionRequest(BaseModel):
    target_difficulty: str = "중"


@app.post("/rooms")
def api_create_room(req: RoomCreateRequest):
    return rooms.create_room(req.name)

@app.get("/rooms")
def api_list_rooms():
    return {"rooms": rooms.list_rooms()}

@app.get("/rooms/{room_id}")
def api_get_room(room_id: str):
    try:
        return rooms.get_room(room_id)
    except rooms.RoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.patch("/rooms/{room_id}")
def api_rename_room(room_id: str, req: RoomRenameRequest):
    try:
        return rooms.rename_room(room_id, req.name)
    except rooms.RoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/rooms/{room_id}/ingest")
def api_room_ingest(room_id: str, file: UploadFile = File(...)):
    """방에 강의자료(PDF/녹음/영상)를 업로드한다. 이 방의 RAG 인덱스에
    이어붙이고(append), 추출된 개념은 이름 기준으로 기존 개념과 병합한
    뒤 팀원2 유형 매핑까지 자동으로 다시 실행한다."""
    try:
        room = rooms.get_room(room_id)
    except rooms.RoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext in PDF_EXTENSIONS:
        kind = "pdf"
    elif ext in AUDIO_EXTENSIONS:
        kind = "audio"
    elif ext in VIDEO_EXTENSIONS:
        kind = "video"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다: '{ext or '(확장자 없음)'}'. "
                   f"PDF, 녹음 파일(mp3/mpeg/mpga/m4a/wav), 영상(mp4/mov/mkv/avi/webm)만 업로드하세요.",
        )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(file.file.read())
            tmp_path = tmp.name

        source_tag = f"u{len(room['uploads'])}"
        ingest_kwargs = dict(
            collection_name="lecture_notes",
            chroma_path=rooms.room_chroma_path(room_id),
            bm25_path=rooms.room_bm25_path(room_id),
            append=True,
            source_tag=source_tag,
        )
        if kind == "pdf":
            summary = run_ingest(pdf_path=tmp_path, **ingest_kwargs)
        elif kind == "audio":
            summary = run_ingest(audio_path=tmp_path, **ingest_kwargs)
        else:
            summary = run_ingest(video_path=tmp_path, **ingest_kwargs)

        pages = summary.pop("pages")
        new_concepts = extract_concepts_from_pdf(pages, file.filename)
        merged_bank = rooms.merge_concepts(room_id, new_concepts)

        # 병합된 전체 개념을 다시 유형 매핑 (비용은 적음: 방당 개념 수가 적게 유지됨)
        mapped = map_concepts_to_types(merged_bank)
        rooms.set_mapped_concepts(room_id, mapped)

        summary["source_path"] = file.filename
        summary["new_concept_count"] = len(new_concepts)
        summary["total_concept_count"] = len(merged_bank)
        rooms.record_upload(room_id, {
            "filename": file.filename,
            "source_type": summary["source_type"],
            "page_count": summary["page_count"],
            "chunk_count": summary["chunk_count"],
            "new_concept_count": summary["new_concept_count"],
        })
        return summary

    except IngestError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _generate_from_room(room_id: str, specs: list[tuple[str, str, str]]) -> list[Problem]:
    """specs: [(concept_name, difficulty, mapped_category), ...].
    방의 RAG 인덱스를 활성화한 뒤 병렬로 문제를 생성한다."""
    room = rooms.get_room(room_id)
    configure_index(rooms.room_chroma_path(room_id), rooms.room_bm25_path(room_id))

    problems_by_index: dict[int, Problem] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(specs), 5) or 1) as executor:
        futures = {
            executor.submit(
                run_generation, concept, difficulty, CATEGORY_TO_KOREAN_TYPE.get(category, "객관식")
            ): i
            for i, (concept, difficulty, category) in enumerate(specs)
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                problems_by_index[futures[future]] = result
    return [problems_by_index[i] for i in sorted(problems_by_index)]


@app.post("/rooms/{room_id}/simple_check")
def api_room_simple_check(room_id: str, req: RoomQuestionRequest):
    """단순 개념 확인: 이 방의 핵심개념 하나당 문제 하나씩, 개수 선택 없이
    전부 생성한다. 모의고사와 성격이 겹치지 않도록, 팀원2의 콘텐츠 기반
    유형(서술형/계산형 등)은 쓰지 않고 객관식/참거짓(OX)만 번갈아
    사용한다 — 빠르게 훑는 단순 확인용이라는 목적에 맞춘 것."""
    try:
        room = rooms.get_room(room_id)
    except rooms.RoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not room["mapped_concepts"]:
        raise HTTPException(status_code=400, detail="이 방에 아직 분석된 핵심개념이 없습니다. 먼저 자료를 업로드하세요.")

    quick_check_categories = ["MULTIPLE_CHOICE", "TRUE_FALSE"]
    specs = [
        (c["concept_name"], req.target_difficulty, quick_check_categories[i % 2])
        for i, c in enumerate(room["mapped_concepts"])
    ]
    problems = _generate_from_room(room_id, specs)
    if not problems:
        raise HTTPException(status_code=400, detail="문제 생성에 실패했습니다.")
    return {"problems": problems}


@app.post("/rooms/{room_id}/mock_exam")
def api_room_mock_exam(room_id: str, req: RoomQuestionRequest):
    """모의고사: 개수 선택 없이 min(핵심개념 수, 20)으로 자동 결정. 중요도
    가중 배분 + 하/중/상 난이도 순환은 core/exam_spec.py 로직을 그대로 쓴다."""
    try:
        room = rooms.get_room(room_id)
    except rooms.RoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not room["mapped_concepts"]:
        raise HTTPException(status_code=400, detail="이 방에 아직 분석된 핵심개념이 없습니다. 먼저 자료를 업로드하세요.")

    question_count = min(len(room["mapped_concepts"]), MAX_ROOM_EXAM_QUESTIONS)
    try:
        exam_specs = build_exam_specs(room["mapped_concepts"], question_count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    specs = [(s.concept_name, s.difficulty, s.mapped_category) for s in exam_specs]
    problems = _generate_from_room(room_id, specs)
    if not problems:
        raise HTTPException(status_code=400, detail="모의고사 생성에 실패했습니다.")
    return {"problems": problems}


@app.post("/grade_answer")
def api_grade_answer(req: GradeRequest):
    try:
        # Reconstruct Problem object from dict
        # We need to ensure the dict matches Problem model fields
        problem_obj = Problem(**req.problem)
        result = run_grading(problem_obj, req.student_answer)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from core.exam import generate_mock_exam, grade_mock_exam

class MockExamGenerateRequest(BaseModel):
    topic_range: str
    num_questions: int = Field(default=5, ge=2, le=20)
    target_difficulty: str = "중"

class MockExamGradeRequest(BaseModel):
    problems: list[dict]
    student_answers: list[str]

@app.post("/generate_mock_exam")
def api_generate_mock_exam(req: MockExamGenerateRequest):
    try:
        problems = generate_mock_exam(req.topic_range, req.num_questions, req.target_difficulty)
        if not problems:
            raise HTTPException(status_code=400, detail="모의고사 생성에 실패했습니다.")
        return {"problems": problems}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/grade_mock_exam")
def api_grade_mock_exam(req: MockExamGradeRequest):
    try:
        problem_objs = [Problem(**p) for p in req.problems]
        result = grade_mock_exam(problem_objs, req.student_answers)
        return {"result": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
