"""
nodes/rubric.py
────────────────
루브릭 생성 및 검증 노드. (실제 OpenAI API 연결)

MD 섹션 4 기반:
  - generate_rubric        : gpt-4o로 루브릭 생성 (MD 4.2)
  - run_rubric_verification: 4종 검증 에이전트 (MD 4.3)
  - get_or_create_rubric   : 캐시 → 없으면 생성+검증 (MD 4.4)
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from core.clients import get_openai_client
from core.state import GradingState
from core.models import RubricCriterion

MODEL_HEAVY = "gpt-4o"        # 루브릭 생성
MODEL_LIGHT = "gpt-4o-mini"   # 루브릭 검증 (저비용)

_rubric_cache: dict[str, list[RubricCriterion]] = {}


# ── 구조화 출력용 래퍼 (OpenAI는 리스트 직접 불가) ─────────────────
class RubricList(BaseModel):
    criteria: list[RubricCriterion]


class VerificationResult(BaseModel):
    passed: bool
    issue: str   # 통과 시 "" / 실패 시 문제 설명


# ──────────────────────────────────────────────────────────────────
# 루브릭 생성 (MD 4.2)
# ──────────────────────────────────────────────────────────────────

def generate_rubric(
    problem: str,
    model_answer: str | None,
    context: str,
) -> list[RubricCriterion]:
    """gpt-4o로 루브릭 항목 생성 (Structured Output)."""
    client = get_openai_client()
    if model_answer:
        user_msg = (
            f"문제: {problem}\n"
            f"모범답안: {model_answer}\n"
            f"강의자료 근거:\n{context}\n\n"
            "모범답안을 채점 가능한 항목들로 분해하라. "
            "각 항목은 point_name, max_score, description, source_reference를 포함해야 한다. "
            "총 배점은 10점이 되도록 구성하라. 모든 항목의 내용은 반드시 한국어(Korean)로 작성하라."
        )
    else:
        user_msg = (
            f"문제: {problem}\n"
            f"강의자료 근거:\n{context}\n\n"
            "강의자료 근거에 기반해 이 문제가 요구하는 핵심 채점 포인트를 추론하여 루브릭을 구성하라. "
            "각 항목은 point_name, max_score, description, source_reference를 포함해야 한다. "
            "총 배점은 10점이 되도록 구성하라. 모든 항목의 내용은 반드시 한국어(Korean)로 작성하라."
        )

    print("[generate_rubric] 루브릭 생성 중 (gpt-4o)...")
    response = client.beta.chat.completions.parse(
        model=MODEL_HEAVY,
        messages=[
            {"role": "system", "content": "당신은 대학교 시험 채점 기준표(루브릭) 전문가입니다. 반드시 구조화된 형식으로 응답하세요."},
            {"role": "user",   "content": user_msg},
        ],
        response_format=RubricList,
    )
    rubric = response.choices[0].message.parsed.criteria
    print(f"[generate_rubric] {len(rubric)}개 채점 항목 생성 완료")
    return rubric


# ──────────────────────────────────────────────────────────────────
# 루브릭 검증 (MD 4.3)
# ──────────────────────────────────────────────────────────────────

VERIFICATION_AGENTS = [
    ("완전성",     "모범답안/강의자료의 핵심 내용이 루브릭에 모두 반영되었는가? 빠진 핵심 채점 포인트가 있으면 passed=false로 표시하라."),
    ("배타성",     "채점 항목끼리 내용이 중복되지 않는가? 두 항목이 실질적으로 같은 것을 평가한다면 passed=false로 표시하라."),
    ("근거일치성", "각 항목이 실제 강의자료에 근거를 두는가? 강의자료에 없는 내용이 채점 기준으로 들어갔다면 passed=false로 표시하라."),
    ("배점타당성", "배점 분배가 문제의 강조점과 맞는가? 중요한 항목에 배점이 너무 낮거나 높다면 passed=false로 표시하라."),
]


def run_rubric_verification(
    rubric: list[RubricCriterion],
    problem: str,
    context: str,
) -> list[RubricCriterion]:
    """4종 검증 에이전트 실행. 실패 시 경고 출력 후 계속 진행."""
    client = get_openai_client()
    rubric_text = "\n".join(
        f"- {c.point_name} ({c.max_score}점): {c.description} [근거: {c.source_reference}]"
        for c in rubric
    )
    for agent_name, check_point in VERIFICATION_AGENTS:
        print(f"[rubric_verify:{agent_name}] 검증 중...")
        response = client.beta.chat.completions.parse(
            model=MODEL_LIGHT,
            messages=[
                {"role": "system", "content": f"당신은 루브릭 {agent_name} 검증 전문가입니다."},
                {"role": "user", "content": (
                    f"문제: {problem}\n"
                    f"루브릭:\n{rubric_text}\n"
                    f"강의자료 근거:\n{context[:800]}\n\n"
                    f"검증 기준: {check_point}"
                )},
            ],
            response_format=VerificationResult,
        )
        result = response.choices[0].message.parsed
        if result.passed:
            print(f"[rubric_verify:{agent_name}] ✅ 통과")
        else:
            print(f"[rubric_verify:{agent_name}] ⚠️  경고: {result.issue}")
            # 경고만 출력하고 계속 진행 (반려 시 재생성은 추후 구현)

    return rubric


# ──────────────────────────────────────────────────────────────────
# 메인 노드 (MD 4.4)
# ──────────────────────────────────────────────────────────────────

def get_or_create_rubric(state: GradingState) -> dict:
    """
    루브릭 캐시 조회 → 없으면 생성+검증 → 캐싱.
    서술형 이외 유형은 루브릭 불필요 → 빈 리스트 반환.
    """
    problem = state["problem"]

    if problem.type != "서술형":
        print(f"[get_rubric] {problem.type} 유형 → 루브릭 불필요")
        return {"rubric": []}

    if problem.problem_id in _rubric_cache:
        print(f"[get_rubric] 캐시 히트 — problem_id={problem.problem_id}")
        return {"rubric": _rubric_cache[problem.problem_id]}

    print(f"[get_rubric] 캐시 미스 — 루브릭 신규 생성")
    rubric = generate_rubric(
        problem=problem.question,
        model_answer=problem.model_answer,
        context=state["context"],
    )
    rubric = run_rubric_verification(rubric, problem.question, state["context"])
    _rubric_cache[problem.problem_id] = rubric
    return {"rubric": rubric}
