from __future__ import annotations
from pydantic import BaseModel
from core.clients import get_openai_client
from core.state import GradingState
from core.models import CritiqueResult, CriterionResult, RubricCriterion

MODEL_HEAVY = "gpt-4o"
MODEL_LIGHT = "gpt-4o-mini"

class _CritiqueOutput(BaseModel):
    total_score: int
    breakdown: list[CriterionResult]

def _grade_with_rubric(
    question: str,
    rubric: list[RubricCriterion],
    answer: str,
    instruction: str,
    critic_name: str,
    model: str,
) -> CritiqueResult:
    """공통 채점 함수 — Structured Output으로 항목별 점수 반환."""
    criteria_text = "\n".join(
        f"- {c.point_name} (최대 {c.max_score}점): {c.description}"
        for c in rubric
    )
    prompt = (
        f"문제: {question}\n\n"
        f"채점 기준:\n{criteria_text}\n\n"
        f"학생 답안: {answer}\n\n"
        f"채점 지침: {instruction}\n\n"
        "각 채점 기준 항목에 대해 획득 점수(score_earned)와 판단 근거(reason)를 제시하라. "
        "score_earned는 0 이상 max_score 이하여야 한다. "
        "판단 근거(reason)는 반드시 한국어(Korean)로 상세히 작성하라."
    )

    print(f"[critique:{critic_name}] 채점 중 ({model})...")
    client = get_openai_client()
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": "당신은 시험 채점 전문가입니다. 반드시 구조화된 형식으로 응답하세요."},
            {"role": "user",   "content": prompt},
        ],
        response_format=_CritiqueOutput,
    )
    parsed = response.choices[0].message.parsed

    rubric_map = {c.point_name: c.max_score for c in rubric}
    clipped_breakdown = []
    for r in parsed.breakdown:
        cap = rubric_map.get(r.point_name, r.score_earned)
        clipped_breakdown.append(CriterionResult(
            point_name=r.point_name,
            score_earned=min(r.score_earned, cap),
            reason=r.reason,
        ))

    return CritiqueResult(
        critic=critic_name,  # type: ignore[arg-type]
        total_score=sum(r.score_earned for r in clipped_breakdown),
        breakdown=clipped_breakdown,
    )

def critique_strict(state: GradingState) -> dict:
    """근거중심: 강의자료 문자 그대로 대조."""
    result = _grade_with_rubric(
        question=state["problem"].question,
        rubric=state["rubric"],
        answer=state["student_answer"],
        instruction=(
            "루브릭 항목이 답안에 정확한 용어로 명시된 경우에만 점수를 부여하라. "
            f"강의자료 근거를 반드시 참조하라:\n{state['context'][:600]}"
        ),
        critic_name="strict",
        model=MODEL_HEAVY,
    )
    return {"critiques": state.get("critiques", []) + [result]}

def critique_lenient(state: GradingState) -> dict:
    """의미이해: 정확한 용어 아니어도 의미상 맞으면 인정."""
    result = _grade_with_rubric(
        question=state["problem"].question,
        rubric=state["rubric"],
        answer=state["student_answer"],
        instruction="정확한 용어가 아니어도 의미상 해당 내용을 담고 있으면 점수를 부여하라.",
        critic_name="lenient",
        model=MODEL_HEAVY,
    )
    return {"critiques": state.get("critiques", []) + [result]}

def critique_keyword(state: GradingState) -> dict:
    """핵심키워드: 필수 키워드 포함 여부만 체크."""
    result = _grade_with_rubric(
        question=state["problem"].question,
        rubric=state["rubric"],
        answer=state["student_answer"],
        instruction="루브릭에 명시된 핵심 키워드·개념 포함 여부만으로 신속하게 판단하라.",
        critic_name="keyword",
        model=MODEL_LIGHT,
    )
    return {"critiques": state.get("critiques", []) + [result]}
