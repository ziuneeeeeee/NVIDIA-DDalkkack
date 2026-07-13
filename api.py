import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any

from core.models import Problem
from main import run_generation, run_grading

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
    num_questions: int = 5
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
