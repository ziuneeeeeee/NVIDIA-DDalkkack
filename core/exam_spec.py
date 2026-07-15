"""
exam_spec.py
─────────────
mapped_concepts(팀원2 산출물: nodes/type_mapping.py)를 받아 실제 시험지의
문항 스펙(개념·난이도·유형)을 조립한다.

문항 수·난이도 배분 방식은 다른 팀원이 독자적으로 구현한 로직(중요도
가중 최대잉여법 + 난이도 순환)을 그대로 포팅했다. 다만 유형(카테고리)은
그 팀원 버전처럼 난이도별 고정 풀에서 순환 선택하지 않고, 팀원2가 이미
콘텐츠 기반으로 정한 mapped_category를 그대로 사용한다 — 난이도와 유형은
서로 독립적으로 결정된다는 팀 합의를 반영한 것이다.
"""

from __future__ import annotations

from dataclasses import dataclass

_IMPORTANCE_WEIGHT = {"core": 3, "important": 2, "supplementary": 1}
_IMPORTANCE_RANK = {"core": 0, "important": 1, "supplementary": 2}

# 한 Concept에 여러 문제가 배정되면 하→중→상 순으로 돌아 서로 다른 학습 단계를 낸다.
_DIFFICULTY_CYCLE = ["하", "중", "상"]


@dataclass(frozen=True)
class ExamSpec:
    concept_id: str
    concept_name: str
    mapped_category: str
    difficulty: str
    mapping_reason: str


def _importance_of(concept: dict) -> str:
    value = concept.get("importance", "important")
    return value if value in _IMPORTANCE_WEIGHT else "important"


def allocate_question_counts(concepts: list[dict], question_count: int) -> list[int]:
    """Case 1(개념 수 < 문제 수): 전 개념 최소 1문제 + importance 가중 비례로
    나머지 배분. 최대잉여법(Largest-Remainder)으로 합계가 정확히
    question_count가 되게 한다."""
    n = len(concepts)
    if n == 0:
        return []
    extra = question_count - n
    counts = [1] * n
    if extra <= 0:
        return counts

    weights = [_IMPORTANCE_WEIGHT[_importance_of(c)] for c in concepts]
    total_w = sum(weights) or n
    raw = [extra * w / total_w for w in weights]
    floor = [int(x) for x in raw]
    remainder = extra - sum(floor)
    order = sorted(
        range(n),
        key=lambda i: (-(raw[i] - floor[i]), _IMPORTANCE_RANK.get(_importance_of(concepts[i]), 1), i),
    )
    for i in order[:remainder]:
        floor[i] += 1
    return [counts[i] + floor[i] for i in range(n)]


def build_exam_specs(mapped_concepts: list[dict], question_count: int) -> list[ExamSpec]:
    """
    - 개념 수 >= 문제 수 : importance 상위 개념을 골라 1문제씩(Case 2).
    - 개념 수 <  문제 수 : 같은 개념을 여러 번 사용, importance가 높은
                            개념에 더 많은 문제를 배분(Case 1).
    각 문제에는 난이도(하/중/상)를 순환 배정한다. 유형은 팀원2가 이미
    콘텐츠 기반으로 정한 mapped_category를 그대로 사용한다 (난이도가
    바뀌어도 같은 개념의 유형은 바뀌지 않음).
    """
    if not mapped_concepts:
        raise ValueError("mapped_concepts가 비어 있습니다. 먼저 개념 매핑(map_concepts_to_types)을 실행하세요.")
    if question_count < 1:
        raise ValueError("요청 문제 수는 1 이상이어야 합니다.")
    missing_category = [c["concept_id"] for c in mapped_concepts if not c.get("mapped_category")]
    if missing_category:
        raise ValueError(f"mapped_category가 없는 개념이 있습니다: {missing_category}")

    ranked = sorted(
        range(len(mapped_concepts)),
        key=lambda i: (_IMPORTANCE_RANK.get(_importance_of(mapped_concepts[i]), 1), i),
    )

    if question_count <= len(mapped_concepts):
        sequence = [(idx, 1) for idx in ranked[:question_count]]
    else:
        per = allocate_question_counts(mapped_concepts, question_count)
        sequence = [(idx, per[idx]) for idx in ranked]

    offset_of = {idx: pos for pos, idx in enumerate(ranked)}

    specs: list[ExamSpec] = []
    for idx, count in sequence:
        concept = mapped_concepts[idx]
        for slot in range(count):
            difficulty = _DIFFICULTY_CYCLE[(slot + offset_of[idx]) % len(_DIFFICULTY_CYCLE)]
            specs.append(ExamSpec(
                concept_id=concept["concept_id"],
                concept_name=concept["concept_name"],
                mapped_category=concept["mapped_category"],
                difficulty=difficulty,
                mapping_reason=concept.get("mapping_reason", ""),
            ))
    return specs
