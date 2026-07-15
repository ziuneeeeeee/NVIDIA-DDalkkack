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
