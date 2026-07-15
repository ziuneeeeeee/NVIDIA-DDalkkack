from __future__ import annotations
import re
from pydantic import BaseModel
from core.clients import get_openai_client
from core.state import GradingState
from core.models import GradeResult

SEMANTIC_MODEL = "gpt-4o-mini"


def _normalize(text: str) -> str:
    """공백·대소문자 정규화 + 괄호·특수문자 제거."""
    text = text.strip().lower()
    text = re.sub(r"[^\w가-힣]", "", text)
    return text


class _SemanticMatch(BaseModel):
    is_equivalent: bool
    reason: str


def _semantic_match(question: str, correct: str, student: str) -> tuple[bool, str]:
    """단답형은 정답이 짧은 단어/구절이어도 학생이 문장으로 풀어 쓰는 경우가 흔해서,
    문자열 완전일치만으로는 의미가 맞는 답도 0점 처리되는 문제가 있었다. 정확히
    일치하지 않을 때만(비용 절감) gpt-4o-mini로 의미상 동일한지 한 번 더 판단한다."""
    client = get_openai_client()
    response = client.beta.chat.completions.parse(
        model=SEMANTIC_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 단답형 채점 보조원입니다. 표현이나 문장 길이가 달라도 "
                    "핵심 의미·사실이 같으면 동일하다고 판단하세요. 정답에 없는 "
                    "핵심 내용을 학생 답이 빠뜨렸거나, 정답과 반대/다른 내용이면 "
                    "동일하지 않다고 판단하세요."
                ),
            },
            {
                "role": "user",
                "content": f"문제: {question}\n정답: {correct}\n학생 답: {student}\n\n두 답이 의미상 같은가요?",
            },
        ],
        response_format=_SemanticMatch,
    )
    res = response.choices[0].message.parsed
    return res.is_equivalent, res.reason


def grade_objective(state: GradingState) -> dict:
    """참거짓/객관식/단답형 채점.
    참거짓·객관식은 보기가 정해져 있어 문자열 정규화 완전일치로 판정한다(LLM 불필요).
    단답형은 완전일치가 아니면 gpt-4o-mini로 의미상 동일한지 한 번 더 확인한다
    (표현만 다르고 핵심 키워드가 사실상 같은 경우 0점 처리되는 것을 방지)."""
    problem = state["problem"]
    correct = problem.answer or ""
    student = state["student_answer"]
    exact_match = _normalize(correct) == _normalize(student)

    if exact_match:
        is_correct = True
        grader_agreement = "자동 판정 (문자열 완전일치, LLM 불필요)"
        reason = f"정답: {correct} / 학생 답: {student} (완전일치)"
    elif problem.type == "단답형":
        is_correct, semantic_reason = _semantic_match(problem.question, correct, student)
        grader_agreement = f"자동 판정 (완전일치 실패 → 의미 판정, {SEMANTIC_MODEL})"
        reason = f"정답: {correct} / 학생 답: {student} / 의미 판정 근거: {semantic_reason}"
    else:
        is_correct = False
        grader_agreement = "자동 판정 (문자열 완전일치, LLM 불필요)"
        reason = f"정답: {correct} / 학생 답: {student} (불일치)"

    print(f"[grade_objective] {problem.type} | 정답='{correct}' | 학생='{student}' → {'✅' if is_correct else '❌'}")

    result = GradeResult(
        final_score=10.0 if is_correct else 0.0,
        max_score=10.0,
        per_criterion=[{
            "point_name": "정답 일치 여부",
            "earned_score": 10.0 if is_correct else 0.0,
            "reason": reason,
        }],
        confidence="high",
        needs_human_review=False,
        grader_agreement=grader_agreement,
    )
    return {"grade_result": result, "critiques": []}
