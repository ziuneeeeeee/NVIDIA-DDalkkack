"""
nodes/diagnose.py
──────────────────
오답/감점 원인 진단 노드. (실제 OpenAI API 연결)

MD 섹션 9.1:
  - 원인 분류: 개념 자체를 모름 / 계산 실수 / 문제 이해 오류 / 유사 개념과 혼동
  - 난이도 조정은 규칙(adjust_difficulty), 원인 진단은 LLM — 역할 분리 원칙
"""

from __future__ import annotations

from core.clients import get_openai_client
from core.state import GradingState
from core.models import DiagnosisResult

MODEL = "gpt-4o"

DIAGNOSE_SYSTEM = """
당신은 학습 진단 전문가입니다.
채점 결과에서 감점된 항목들을 분석하여 학생의 오류 원인을 정확히 분류하세요.

오류 원인 분류 기준:
- 개념 자체를 모름  : 해당 개념이 답안에 전혀 없거나 완전히 잘못 이해된 경우
- 계산 실수         : 개념은 알지만 수치 계산이나 논리 전개에서 실수한 경우
- 문제 이해 오류    : 문제가 요구하는 것을 다르게 해석한 경우
- 유사 개념과 혼동  : 비슷한 개념(BFS vs DFS, 스택 vs 큐 등)을 혼동한 경우
"""


def diagnose(state: GradingState) -> dict:
    """
    오답/감점 원인 진단. 만점이면 스킵.

    Returns:
        {"diagnosis": DiagnosisResult | None}
    """
    grade = state["grade_result"]

    if grade and grade.final_score >= grade.max_score:
        print("[diagnose] 만점 → 진단 스킵")
        return {"diagnosis": None}

    print("[diagnose] 감점 원인 분석 중 (gpt-4o)...")
    client = get_openai_client()

    per_criterion_text = "\n".join(
        str(item) for item in (grade.per_criterion if grade else [])
    )

    response = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": DIAGNOSE_SYSTEM},
            {"role": "user", "content": (
                f"문제: {state['problem'].question}\n\n"
                f"채점 결과 (항목별 내역):\n{per_criterion_text}\n\n"
                f"학생 답안: {state['student_answer']}\n\n"
                "위 내용을 바탕으로 감점 원인을 진단하라."
            )},
        ],
        response_format=DiagnosisResult,
    )

    diagnosis = response.choices[0].message.parsed
    print(f"[diagnose] 원인: {diagnosis.error_type} — {diagnosis.weak_concept}")
    return {"diagnosis": diagnosis}
