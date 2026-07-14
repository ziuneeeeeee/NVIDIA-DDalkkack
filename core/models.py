from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

class RubricCriterion(BaseModel):
    point_name: str = Field(..., description="채점 항목명 (예: '자료구조 차이')")
    max_score: int = Field(..., description="해당 항목 배점")
    description: str = Field(..., description="이 항목에서 무엇을 확인하는지")
    source_reference: str = Field(..., description="이 채점 기준의 근거가 되는 강의자료 위치")

class Problem(BaseModel):
    problem_id: str
    type: Literal["참거짓", "객관식", "단답형", "서술형", "코딩형"]
    question: str
    answer: Optional[str] = None
    model_answer: Optional[str] = None
    test_cases: Optional[list[dict]] = None
    rubric: Optional[list[RubricCriterion]] = None

class CriterionResult(BaseModel):
    point_name: str
    score_earned: int
    reason: str

class CritiqueResult(BaseModel):
    critic: Literal["strict", "lenient", "keyword"]
    total_score: int
    breakdown: list[CriterionResult]

class GradeResult(BaseModel):
    final_score: float
    max_score: float
    per_criterion: list[dict]
    confidence: Literal["high", "low"]
    needs_human_review: bool
    grader_agreement: str

class ConceptMastery(BaseModel):
    concept: str
    attempts: int = 0
    correct: int = 0
    current_difficulty: Literal["하", "중", "상"] = "중"
    consecutive_correct: int = 0
    consecutive_wrong: int = 0
    mastery_score: float = 0.0

class DiagnosisResult(BaseModel):
    error_type: Literal["개념 자체를 모름", "계산 실수", "문제 이해 오류", "유사 개념과 혼동"]
    weak_concept: str
    detail: str
