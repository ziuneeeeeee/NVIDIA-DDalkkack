"""
type_mapping.py
──────────────
[팀원 1: 개념 추출] -> [팀원 2: 유형/난이도 매핑] -> [팀원 3/4: 문제/루브릭 생성]
파이프라인에서 팀원 2 담당 단계.

concept_bank.json (팀원 1 산출물)을 입력받아, 각 개념에
  - mapped_category: CALCULATION / MULTIPLE_CHOICE / TRUE_FALSE / DESCRIPTIVE
  - difficulty: 쉬움 / 보통 / 어려움
을 매핑하고 mapped_concepts.json 형태로 반환한다.

설계 방식: LLM은 개념별로 "각 카테고리/난이도에 얼마나 적합한지" 점수만 매기고,
실제 몇 개를 어떤 카테고리/난이도로 확정할지는 코드가 목표 개수(quota)에
정확히 맞춰 결정론적으로 배정한다. (LLM에게 비율을 프롬프트로 "부탁"만 하면
개념 수가 늘어날수록 쉽게 어긋나기 때문에, 배정은 코드가 강제한다.)

시험지 구성 목표 (총 20문제 고정):
  난이도  쉬움 6 / 보통 10 / 어려움 4   (30% / 50% / 20%)
  유형    객관식 8 / 참거짓 6 / 서술형+계산형 6   (40% / 30% / 30%)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.clients import get_openai_client

MODEL = "gpt-4o"

MappedCategory = Literal["CALCULATION", "MULTIPLE_CHOICE", "TRUE_FALSE", "DESCRIPTIVE"]
Difficulty = Literal["쉬움", "보통", "어려움"]

# ── 시험지 구성 목표 (20문제 고정) ─────────────────────────────────
TARGET_TOTAL = 20
CATEGORY_TARGET_COUNTS = {
    "MULTIPLE_CHOICE": 8,
    "TRUE_FALSE": 6,
    "DESCRIPTIVE_OR_CALCULATION": 6,   # DESCRIPTIVE + CALCULATION 합산
}
DIFFICULTY_TARGET_COUNTS = {
    "쉬움": 6,
    "보통": 10,
    "어려움": 4,
}

# 한 번의 LLM 호출로 채점하기에 안전한 최대 개념 수 (컨텍스트/출력 신뢰도 확보용)
CHUNK_SIZE = 25

SCORING_SYSTEM_PROMPT = """\
너는 교육용 문제 매핑 전문가이다. 각 개념의 '정보 구성 특징'을 분석하여,
아래 4개 문제 유형과 3개 난이도 각각에 그 개념이 얼마나 적합한지 0~100점으로
점수를 매겨라. 최종 배정은 네가 아니라 별도 로직이 목표 개수에 맞춰 결정하므로,
너는 오직 '적합도 점수'만 최대한 정확하게 매기면 된다.

# [문제 유형 점수 기준]
- calculation_score: 구체적인 수치, 공식, 변수(예: ms, Burst Time 등), 예시 데이터
  표(Table)가 텍스트에 실제로 있을 때만 높게. 계산할 근거가 텍스트에 없다면
  반드시 낮은 점수(20 이하)를 줘라. calc_eligible이 false이면 이 문제는 계산형으로
  절대 출제될 수 없다는 뜻이니 신중하게 판단하라.
- multiple_choice_score: 하나의 주제 아래 여러 특징/종류가 나열되어 비교 대조가
  가능할 때 높게.
- true_false_score: 텍스트가 2~3줄 이하로 짧고 단순 정의·사실 전달 위주일 때 높게.
- descriptive_score: 인과관계 설명이 필요하거나 여러 메커니즘이 순차적으로
  맞물려 일어나는 복잡한 작동 이론일 때 높게.

# [난이도 점수 기준]
- easy_score: 강의자료의 핵심 키워드·정의를 정확히 기억하고 있는지만 확인하면
  되는 단순한 개념일 때 높게.
- medium_score: 이론의 메커니즘이나 인과관계를 이해하고 적용할 수 있는지
  평가해야 하는 개념일 때 높게.
- hard_score: 여러 개념을 복합적으로 활용해야 하거나 예외 상황을 해결해야
  하는, 변별력이 필요한 개념일 때 높게.

모든 reasoning 텍스트(mapping_reason, difficulty_reason)는 반드시 한국어로 작성하라.
입력으로 주어진 모든 concept_id에 대해 빠짐없이 점수를 반환하라.
"""


class ConceptScore(BaseModel):
    concept_id: str
    calc_eligible: bool
    calculation_score: int
    multiple_choice_score: int
    true_false_score: int
    descriptive_score: int
    mapping_reason: str
    easy_score: int
    medium_score: int
    hard_score: int
    difficulty_reason: str


class BatchScoreResult(BaseModel):
    scores: list[ConceptScore]


def _build_user_prompt(concepts: list[dict]) -> str:
    lines = [f"개념 총 {len(concepts)}개. 각각에 점수를 매겨라.\n"]
    for c in concepts:
        lines.append(
            f"- concept_id: {c['concept_id']}\n"
            f"  concept_name: {c['concept_name']}\n"
            f"  concept_summary: {c.get('concept_summary', '')}\n"
            f"  source_context: {c.get('source_context', '')}\n"
        )
    return "\n".join(lines)


def _score_chunk(chunk: list[dict]) -> list[ConceptScore]:
    client = get_openai_client()
    response = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(chunk)},
        ],
        response_format=BatchScoreResult,
    )
    return response.choices[0].message.parsed.scores


def _score_all_concepts(concepts: list[dict]) -> dict[str, ConceptScore]:
    """개념이 많을 경우 CHUNK_SIZE 단위로 나눠 여러 번 호출해 컨텍스트/출력
    신뢰도 문제를 피한다. 배정(quota)은 이후 전체를 합쳐 한 번에 수행한다."""
    scores: dict[str, ConceptScore] = {}
    for i in range(0, len(concepts), CHUNK_SIZE):
        chunk = concepts[i:i + CHUNK_SIZE]
        for s in _score_chunk(chunk):
            scores[s.concept_id] = s

    missing = [c["concept_id"] for c in concepts if c["concept_id"] not in scores]
    if missing:
        raise ValueError(f"LLM이 다음 concept_id에 대한 점수를 반환하지 않았습니다: {missing}")
    return scores


# ── 결정론적 배정 로직 (LLM 호출 없이 순수 함수 -> 테스트 용이) ──────

def scale_quota(target_counts: dict[str, int], actual_total: int) -> dict[str, int]:
    """target_counts는 TARGET_TOTAL 기준 목표 개수. 실제 개념 수가 다르면
    비율을 유지한 채 정수로 스케일링한다 (최대 나머지법으로 합계를 정확히 맞춤)."""
    target_total = sum(target_counts.values())
    if actual_total == target_total:
        return dict(target_counts)
    if actual_total <= 0:
        return {k: 0 for k in target_counts}

    raw = {k: v * actual_total / target_total for k, v in target_counts.items()}
    floors = {k: int(raw[k]) for k in target_counts}
    remainder = actual_total - sum(floors.values())
    fracs_desc = sorted(target_counts.keys(), key=lambda k: raw[k] - floors[k], reverse=True)
    for k in fracs_desc[:remainder]:
        floors[k] += 1
    return floors


def assign_by_quota(
    items: list[tuple[str, dict[str, float]]],
    quotas: dict[str, int],
) -> dict[str, str]:
    """items: [(id, {label: score}), ...]. 각 id를 정확히 하나의 label에 배정하되,
    label별 배정 개수가 quotas와 정확히 일치하도록 한다.
    (score가 높은 (id, label) 조합부터 그리디로 확정하는 근사 최대가중치 매칭.)
    sum(quotas) == len(items) 이어야 한다."""
    quotas = dict(quotas)
    items_by_id = dict(items)
    assigned: dict[str, str] = {}

    pairs = [
        (score, id_, label)
        for id_, scores in items
        for label, score in scores.items()
    ]
    pairs.sort(key=lambda p: p[0], reverse=True)

    for score, id_, label in pairs:
        if id_ in assigned or quotas.get(label, 0) <= 0:
            continue
        assigned[id_] = label
        quotas[label] -= 1

    # 위 그리디로 못 채운 id가 남으면(동점 처리 등), 남은 quota가 있는 label 중
    # 해당 id의 점수가 가장 높은 label에 강제 배정한다.
    for id_, scores in items:
        if id_ in assigned:
            continue
        remaining_labels = [l for l, q in quotas.items() if q > 0]
        if not remaining_labels:
            raise ValueError("quota 총합이 item 개수와 일치하지 않습니다.")
        best_label = max(remaining_labels, key=lambda l: scores.get(l, 0))
        assigned[id_] = best_label
        quotas[best_label] -= 1

    return assigned


def finalize_category(
    bucket: str,
    calc_eligible: bool,
    calculation_score: int,
    descriptive_score: int,
) -> MappedCategory:
    """DESCRIPTIVE_OR_CALCULATION 버킷으로 배정된 개념을 실제 CALCULATION/DESCRIPTIVE
    중 하나로 확정한다. calc_eligible이 False면 무조건 DESCRIPTIVE (보수적 처리)."""
    if bucket != "DESCRIPTIVE_OR_CALCULATION":
        return bucket  # type: ignore[return-value]
    if calc_eligible and calculation_score >= descriptive_score:
        return "CALCULATION"
    return "DESCRIPTIVE"


def map_concepts_to_types(concepts: list[dict], target_total: int = TARGET_TOTAL) -> list[dict]:
    """concept_bank.json의 개념 리스트를 받아 mapped_category/difficulty가
    추가된 mapped_concepts 리스트를 반환한다. (팀원 3/4에게 그대로 전달되는 포맷)

    target_total은 기본 20으로 고정되어 있으며, 실제로 들어온 concepts 개수가
    이와 다르면 목표 비율(40/30/30, 30/50/20%)을 유지한 채 자동으로 스케일링한다.
    """
    if not concepts:
        return []

    scores = _score_all_concepts(concepts)

    category_quota = scale_quota(CATEGORY_TARGET_COUNTS, len(concepts))
    difficulty_quota = scale_quota(DIFFICULTY_TARGET_COUNTS, len(concepts))

    category_items = []
    difficulty_items = []
    for c in concepts:
        s = scores[c["concept_id"]]
        calc_score = s.calculation_score if s.calc_eligible else 0
        category_items.append((c["concept_id"], {
            "MULTIPLE_CHOICE": s.multiple_choice_score,
            "TRUE_FALSE": s.true_false_score,
            "DESCRIPTIVE_OR_CALCULATION": max(s.descriptive_score, calc_score),
        }))
        difficulty_items.append((c["concept_id"], {
            "쉬움": s.easy_score,
            "보통": s.medium_score,
            "어려움": s.hard_score,
        }))

    category_bucket = assign_by_quota(category_items, category_quota)
    difficulty_assignment = assign_by_quota(difficulty_items, difficulty_quota)

    mapped_concepts = []
    for c in concepts:
        cid = c["concept_id"]
        s = scores[cid]
        calc_score = s.calculation_score if s.calc_eligible else 0
        bucket = category_bucket[cid]
        final_category = finalize_category(bucket, s.calc_eligible, calc_score, s.descriptive_score)

        # 경계 케이스 신호: 점수상 1순위 카테고리와 실제 배정이 다르면 낮은 확신도로 표시
        candidate_scores = {
            "MULTIPLE_CHOICE": s.multiple_choice_score,
            "TRUE_FALSE": s.true_false_score,
            "DESCRIPTIVE": s.descriptive_score,
            "CALCULATION": calc_score,
        }
        top_category = max(candidate_scores, key=lambda k: candidate_scores[k])
        confidence = "high" if top_category == final_category else "low"

        entry = {
            **c,
            "mapped_category": final_category,
            "mapping_reason": s.mapping_reason,
            "confidence": confidence,
            "difficulty": difficulty_assignment[cid],
            "difficulty_reason": s.difficulty_reason,
        }
        if confidence == "low":
            entry["runner_up_category"] = top_category
        mapped_concepts.append(entry)

    return mapped_concepts
