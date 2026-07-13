from __future__ import annotations
from typing import Optional
from typing_extensions import TypedDict
from core.models import (
    Problem, RubricCriterion, CritiqueResult, GradeResult,
    DiagnosisResult, ConceptMastery
)

class GradingState(TypedDict):
    # ── 입력 ───────────────────────────────────
    problem: Problem
    student_answer: str

    # ── RAG 결과 ───────────────────────────────
    context: str                            # 강의자료에서 검색된 근거 청크

    # ── 루브릭 ─────────────────────────────────
    rubric: list[RubricCriterion]           # 캐시 or 새로 생성된 루브릭

    # ── 채점 ───────────────────────────────────
    critiques: list[CritiqueResult]         # strict/lenient/keyword 채점 결과
    grade_result: Optional[GradeResult]     # Judge 최종 결과

    # ── 진단 & 적응형 조정 ─────────────────────
    diagnosis: Optional[DiagnosisResult]
    next_concept: str
    next_difficulty: str

    # ── 이력 ───────────────────────────────────
    concept_mastery: dict[str, ConceptMastery]
    session_history: list[dict]
    problem_count: int                      # 세션 내 풀이한 문제 수

def initial_state(problem: Problem, student_answer: str) -> GradingState:
    """새 채점 요청을 처음 시작할 때 사용하는 초기 상태."""
    return GradingState(
        problem=problem,
        student_answer=student_answer,
        context="",
        rubric=[],
        critiques=[],
        grade_result=None,
        diagnosis=None,
        next_concept="",
        next_difficulty="중",
        concept_mastery={},
        session_history=[],
        problem_count=0,
    )

class GenerationState(TypedDict):
    concept: str
    target_difficulty: str
    context: str

    draft_problem: Optional[dict]
    validation_feedback: str
    difficulty_feedback: str
    
    is_accepted: bool
    final_problem: Optional[Problem]
    retry_count: int
    error_message: str

def initial_generation_state(concept: str, target_difficulty: str, context: str) -> GenerationState:
    return GenerationState(
        concept=concept,
        target_difficulty=target_difficulty,
        context=context,
        draft_problem=None,
        validation_feedback="",
        difficulty_feedback="",
        is_accepted=False,
        final_problem=None,
        retry_count=0,
        error_message="",
    )
