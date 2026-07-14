"""
api.py
───────
FastAPI 백엔드 엔드포인트.

MD 섹션 10 기반:
  - FastAPI(백엔드) + vanilla JS(프론트) + Tailwind(디자인) 조합
  - LangGraph 로직(LLM 호출, 상태 관리)은 반드시 서버에서 실행
  - 프론트는 결과 표시와 입력 수집만 담당

개발 순서 (MD 10):
  (1) 파이썬 스크립트로 파이프라인 완성 (main.py)
  (2) FastAPI 엔드포인트로 감싸기 (이 파일)
  (3) JS 프론트 연결

실행:
  uvicorn api:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from graphs.grading_graph import grading_graph as graph
from core.models import Problem
from core.state import initial_state


app = FastAPI(
    title="수강과목 학습도우미 — 채점 API",
    description="멀티에이전트 채점 시스템 (strict/lenient/keyword + Judge)",
    version="1.0.0",
)

# CORS 설정 (JS 프론트에서 fetch() 사용 시 필요)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # TODO: 배포 시 특정 도메인으로 제한
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# 요청/응답 스키마
# ──────────────────────────────────────────────

class GradeRequest(BaseModel):
    """
    MD 10: async def grade_answer(req: GradeRequest) 기반

    problem_id   : 문제 고유 ID (루브릭 캐싱 키로 사용)
    problem_type : "참거짓" | "객관식" | "단답형" | "서술형" | "코딩형"
    question     : 문제 텍스트
    student_answer: 학생 답안
    model_answer : 서술형 모범답안 (선택, 있으면 루브릭 생성에 활용)
    answer       : 참거짓/객관식/단답형 정답 (선택)
    """
    problem_id: str
    problem_type: str
    question: str
    student_answer: str
    model_answer: str | None = None
    answer: str | None = None


class CriterionFeedback(BaseModel):
    point_name: str
    results: list[dict]


class GradeResponse(BaseModel):
    """
    MD 5.3 최종 출력 형태 기반:
      - final_score, max_score: 점수
      - confidence: "high" | "low"
      - needs_human_review: 편차 클 때 True
      - grader_agreement: 채점자 점수 분포 설명
      - per_criterion: 항목별 채점 결과
      - diagnosis: 오답 원인 진단
      - next_concept, next_difficulty: 다음 추천 학습 방향
    """
    final_score: float
    max_score: float
    confidence: str
    needs_human_review: bool
    grader_agreement: str
    per_criterion: list[dict]
    diagnosis: dict | None
    next_concept: str
    next_difficulty: str


# ──────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────

@app.post("/grade-answer", response_model=GradeResponse)
async def grade_answer(req: GradeRequest):
    """
    학생 답안을 채점하고 결과를 반환한다.

    MD 10:
      result = await run_grading_pipeline(req.problem_id, req.student_answer)
      return result

    흐름:
      parse_problem → retrieve → get_rubric → [유형 분기]
      → diagnose → adjust → recommend
    """
    try:
        problem = Problem(
            problem_id=req.problem_id,
            type=req.problem_type,    # type: ignore[arg-type]
            question=req.question,
            answer=req.answer,
            model_answer=req.model_answer,
        )
        state = initial_state(problem=problem, student_answer=req.student_answer)

        # TODO: async 지원 — LangGraph의 ainvoke() 사용 권장
        result = graph.invoke(state)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    grade = result.get("grade_result")
    diagnosis = result.get("diagnosis")

    return GradeResponse(
        final_score=grade.final_score if grade else 0.0,
        max_score=grade.max_score if grade else 0.0,
        confidence=grade.confidence if grade else "low",
        needs_human_review=grade.needs_human_review if grade else False,
        grader_agreement=grade.grader_agreement if grade else "",
        per_criterion=grade.per_criterion if grade else [],
        diagnosis=diagnosis.model_dump() if diagnosis else None,
        next_concept=result.get("next_concept", ""),
        next_difficulty=result.get("next_difficulty", "중"),
    )


@app.get("/health")
async def health():
    """헬스체크 엔드포인트."""
    return {"status": "ok", "version": "1.0.0"}
