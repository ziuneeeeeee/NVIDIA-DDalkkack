from __future__ import annotations
import re
from core.state import GradingState
from core.models import GradeResult

def _normalize(text: str) -> str:
    """공백·대소문자 정규화 + 괄호·특수문자 제거."""
    text = text.strip().lower()
    text = re.sub(r"[^\w가-힣]", "", text)
    return text

def grade_objective(state: GradingState) -> dict:
    """객관식/단답형: 문자열 정규화 비교. LLM 불필요."""
    correct = state["problem"].answer or ""
    student = state["student_answer"]
    is_correct = _normalize(correct) == _normalize(student)

    print(f"[grade_objective] 정답='{correct}' | 학생='{student}' → {'✅' if is_correct else '❌'}")

    result = GradeResult(
        final_score=10.0 if is_correct else 0.0,
        max_score=10.0,
        per_criterion=[{
            "point_name": "정답 일치 여부",
            "earned_score": 10.0 if is_correct else 0.0,
            "reason": f"정답: {correct} / 학생 답: {student}",
        }],
        confidence="high",
        needs_human_review=False,
        grader_agreement="자동 판정 (LLM 불필요)",
    )
    return {"grade_result": result, "critiques": []}
