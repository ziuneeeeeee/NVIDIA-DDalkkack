"""
type_mapping.py
──────────────
[팀원 1: 개념 추출] -> [팀원 2: 유형 매핑] -> [팀원 3/4: 문제/루브릭 생성]
파이프라인에서 팀원 2 담당 단계.

concept_bank.json (팀원 1 산출물)을 입력받아, 각 개념을 아래 4개 카테고리 중
하나로 매핑하고 mapped_concepts.json 형태로 반환한다.

  CALCULATION      계산/추적형 - 구체적 수치·공식·변수·예시 데이터 표가 있을 때만
  MULTIPLE_CHOICE  객관식 4지선다 - 여러 특징/종류가 나열되어 비교 대조가 가능할 때
  TRUE_FALSE       참/거짓 단답형 - 2~3줄 이하의 짧은 단순 정의·사실
  DESCRIPTIVE      서술형 - 인과관계·복합 메커니즘 설명이 필요할 때

25개 개념 배치를 한 번의 LLM 호출로 함께 분류해, 목표 비율(객관식 40%,
참/거짓 30%, 서술형+계산형 30%)에서 크게 벗어나지 않도록 균형을 맞춘다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.clients import get_openai_client

MODEL = "gpt-4o"

MappedCategory = Literal["CALCULATION", "MULTIPLE_CHOICE", "TRUE_FALSE", "DESCRIPTIVE"]

TARGET_RATIO = {
    "MULTIPLE_CHOICE": 0.4,
    "TRUE_FALSE": 0.3,
    "DESCRIPTIVE_OR_CALCULATION": 0.3,   # DESCRIPTIVE + CALCULATION 합산 목표
}

MAPPING_SYSTEM_PROMPT = """\
너는 교육용 문제 매핑 전문가이다. 제공된 핵심 개념과 텍스트의 '정보 구성 특징'을
분석하여 가장 학습 효과가 높은 문제 유형을 매핑하라.

# [문제 유형 결정 매트릭스]
1. 계산 / 추적형 (CALCULATION)
   - 조건: 청크 텍스트에 구체적인 수치, 공식, 변수(예: ms, Burst Time 등),
     예시 데이터 표(Table)가 포함되어 있을 때.
2. 객관식 4지선다형 (MULTIPLE_CHOICE)
   - 조건: 청크 텍스트에 특정 개념의 장단점, 특징, 여러 가지 종류(리스트 형태)가
     나열되어 비교 대조가 가능할 때.
3. 참/거짓 단답형 (TRUE_FALSE)
   - 조건: 청크 텍스트가 2~3줄 이하로 짧고, 단순 정의나 사실(Fact) 전달 위주일 때.
4. 서술형 (DESCRIPTIVE)
   - 조건: 인과관계 설명이 필요하거나, 여러 메커니즘이 순차적으로 맞물려 일어나는
     복잡한 작동 이론일 때.

# [제약 조건]
- 텍스트 안에 '계산할 수 있는 실제 수치나 표'가 없는데 무리하게 '계산/추적형'으로
  분류해서는 안 된다. 텍스트에 기반한 문제만 출제할 수 있도록 보수적으로 매핑하라.
- 전체 개념의 유형 비율이 한쪽으로 쏠리지 않도록 균형을 맞춰라.
  (목표: 객관식 40%, 참/거짓 30%, 서술형+계산형 합산 30%)
- 반드시 입력으로 주어진 모든 concept_id에 대해 하나씩만 분류 결과를 반환하라.
"""


class ConceptClassification(BaseModel):
    concept_id: str
    mapped_category: MappedCategory
    mapping_reason: str


class BatchClassificationResult(BaseModel):
    classifications: list[ConceptClassification]


def _build_user_prompt(concepts: list[dict]) -> str:
    lines = [f"개념 총 {len(concepts)}개. 각각을 분류하라.\n"]
    for c in concepts:
        lines.append(
            f"- concept_id: {c['concept_id']}\n"
            f"  concept_name: {c['concept_name']}\n"
            f"  concept_summary: {c.get('concept_summary', '')}\n"
            f"  source_context: {c.get('source_context', '')}\n"
        )
    return "\n".join(lines)


def map_concepts_to_types(concepts: list[dict]) -> list[dict]:
    """concept_bank.json의 개념 리스트를 받아 mapped_category/mapping_reason이
    추가된 mapped_concepts 리스트를 반환한다. (팀원 3/4에게 그대로 전달되는 포맷)"""
    if not concepts:
        return []

    client = get_openai_client()
    response = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": MAPPING_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(concepts)},
        ],
        response_format=BatchClassificationResult,
    )
    result = response.choices[0].message.parsed
    by_id = {c.concept_id: c for c in result.classifications}

    mapped_concepts = []
    for concept in concepts:
        cls = by_id.get(concept["concept_id"])
        if cls is None:
            raise ValueError(f"LLM이 concept_id '{concept['concept_id']}'에 대한 분류를 반환하지 않았습니다.")
        mapped_concepts.append({
            **concept,
            "mapped_category": cls.mapped_category,
            "mapping_reason": cls.mapping_reason,
        })
    return mapped_concepts
