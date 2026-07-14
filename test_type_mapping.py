"""
type_mapping.py의 순수 로직 테스트.
LLM 호출 없이(=API 키 불필요) 배정 로직만 검증한다.
"""

import random

import pytest

import nodes.type_mapping as type_mapping
from nodes.type_mapping import (
    MAX_TOTAL,
    ConceptScore,
    map_concepts_to_types,
    pick_category,
    pick_difficulty,
    select_concepts,
)


def _score(concept_id: str, **overrides) -> ConceptScore:
    base = dict(
        concept_id=concept_id,
        calc_eligible=False,
        calculation_score=0,
        multiple_choice_score=0,
        true_false_score=0,
        descriptive_score=0,
        mapping_reason="테스트용 근거",
        easy_score=0,
        medium_score=0,
        hard_score=0,
        difficulty_reason="테스트용 근거",
        importance_score=50,
    )
    base.update(overrides)
    return ConceptScore(**base)


# ── pick_category ────────────────────────────────────────────────

def test_pick_category_picks_highest_score():
    s = _score("c1", multiple_choice_score=90, true_false_score=10, descriptive_score=20)
    category, runner_up, confidence = pick_category(s)
    assert category == "MULTIPLE_CHOICE"
    assert confidence == "high"


def test_pick_category_ignores_calculation_when_not_eligible():
    # calculation_score가 제일 높아도 calc_eligible=False면 후보에서 제외
    s = _score("c1", calc_eligible=False, calculation_score=99, descriptive_score=40, multiple_choice_score=30)
    category, _, _ = pick_category(s)
    assert category == "DESCRIPTIVE"


def test_pick_category_allows_calculation_when_eligible():
    s = _score("c1", calc_eligible=True, calculation_score=99, descriptive_score=40)
    category, _, _ = pick_category(s)
    assert category == "CALCULATION"


def test_pick_category_low_confidence_when_scores_close():
    s = _score("c1", multiple_choice_score=55, true_false_score=50, descriptive_score=10)
    category, runner_up, confidence = pick_category(s)
    assert category == "MULTIPLE_CHOICE"
    assert runner_up == "TRUE_FALSE"
    assert confidence == "low"


def test_pick_category_high_confidence_when_scores_far_apart():
    s = _score("c1", multiple_choice_score=90, true_false_score=20, descriptive_score=10)
    _, _, confidence = pick_category(s)
    assert confidence == "high"


# ── pick_difficulty ──────────────────────────────────────────────

def test_pick_difficulty_picks_highest_score():
    s = _score("c1", easy_score=20, medium_score=80, hard_score=30)
    assert pick_difficulty(s) == "보통"


# ── select_concepts (핵심도 상위 max_total개 선택, 아니면 전부) ────

def test_select_concepts_returns_all_when_at_or_under_max():
    concepts = [{"concept_id": f"c{i}", "concept_name": f"n{i}"} for i in range(5)]
    scores = {c["concept_id"]: _score(c["concept_id"], importance_score=i) for i, c in enumerate(concepts)}
    result = select_concepts(concepts, scores, max_total=20)
    assert result == concepts  # 순서까지 그대로 유지


def test_select_concepts_caps_at_max_and_keeps_top_importance():
    concepts = [{"concept_id": f"c{i}", "concept_name": f"n{i}"} for i in range(25)]
    # c0..c24, importance_score는 concept_id 뒤 숫자와 동일하게 (c24가 가장 중요)
    scores = {c["concept_id"]: _score(c["concept_id"], importance_score=i) for i, c in enumerate(concepts)}
    result = select_concepts(concepts, scores, max_total=20)
    assert len(result) == 20
    result_ids = {c["concept_id"] for c in result}
    expected_ids = {f"c{i}" for i in range(5, 25)}  # 상위 20개 (importance 5~24)
    assert result_ids == expected_ids


def test_select_concepts_preserves_original_order_after_capping():
    concepts = [{"concept_id": f"c{i}", "concept_name": f"n{i}"} for i in range(25)]
    scores = {c["concept_id"]: _score(c["concept_id"], importance_score=i) for i, c in enumerate(concepts)}
    result = select_concepts(concepts, scores, max_total=20)
    ids = [c["concept_id"] for c in result]
    assert ids == sorted(ids, key=lambda cid: int(cid[1:]))  # 원래 순서(c5, c6, ... c24) 유지


# ── 입력 검증 ────────────────────────────────────────────────────

def _fake_concept(i: int, **overrides) -> dict:
    base = {"concept_id": f"c{i}", "concept_name": f"개념 {i}", "concept_summary": "설명"}
    base.update(overrides)
    return base


def test_map_concepts_to_types_rejects_missing_required_field():
    concepts = [{"concept_id": "c1"}]  # concept_name 누락
    with pytest.raises(ValueError, match="필수 필드"):
        map_concepts_to_types(concepts)


def test_map_concepts_to_types_rejects_duplicate_concept_id():
    concepts = [_fake_concept(1), _fake_concept(1)]  # 둘 다 concept_id='c1'
    with pytest.raises(ValueError, match="중복"):
        map_concepts_to_types(concepts)


def test_map_concepts_to_types_validates_before_calling_llm(monkeypatch):
    def fail_if_called(_concepts):
        raise AssertionError("검증 실패 시 LLM 호출까지 가면 안 된다 (비용 낭비)")

    monkeypatch.setattr(type_mapping, "_score_all_concepts", fail_if_called)
    with pytest.raises(ValueError):
        map_concepts_to_types([{"concept_id": "c1"}])


# ── map_concepts_to_types 종단 테스트 (LLM 호출은 합성 점수로 대체) ─

def _synthetic_scores(concepts: list[dict]) -> dict[str, ConceptScore]:
    rng = random.Random(42)
    scores = {}
    for i, c in enumerate(concepts):
        calc_eligible = rng.random() < 0.3
        scores[c["concept_id"]] = _score(
            c["concept_id"],
            calc_eligible=calc_eligible,
            calculation_score=rng.randint(0, 100) if calc_eligible else rng.randint(0, 20),
            multiple_choice_score=rng.randint(0, 100),
            true_false_score=rng.randint(0, 100),
            descriptive_score=rng.randint(0, 100),
            easy_score=rng.randint(0, 100),
            medium_score=rng.randint(0, 100),
            hard_score=rng.randint(0, 100),
            importance_score=i,  # 뒤로 갈수록 중요한 개념
        )
    return scores


def test_map_concepts_to_types_uses_all_concepts_when_under_max(monkeypatch):
    concepts = [_fake_concept(i) for i in range(12)]
    monkeypatch.setattr(type_mapping, "_score_all_concepts", _synthetic_scores)

    mapped = map_concepts_to_types(concepts)

    assert len(mapped) == 12  # 20개로 억지로 안 채움
    assert {m["concept_id"] for m in mapped} == {c["concept_id"] for c in concepts}


def test_map_concepts_to_types_caps_at_20_when_over(monkeypatch):
    concepts = [_fake_concept(i) for i in range(30)]
    monkeypatch.setattr(type_mapping, "_score_all_concepts", _synthetic_scores)

    mapped = map_concepts_to_types(concepts)

    assert len(mapped) == MAX_TOTAL == 20
    # importance_score = 인덱스이므로, 상위 20개는 인덱스 10~29
    kept_ids = {m["concept_id"] for m in mapped}
    assert kept_ids == {f"c{i}" for i in range(10, 30)}


def test_map_concepts_to_types_output_has_no_fixed_ratio_bias(monkeypatch):
    # 모든 개념이 명백히 서술형 성격이면, 비율 강제 없이 전부 DESCRIPTIVE로 몰려야 한다.
    concepts = [_fake_concept(i) for i in range(10)]

    def all_descriptive_scores(cs):
        return {
            c["concept_id"]: _score(c["concept_id"], descriptive_score=90, multiple_choice_score=10, true_false_score=5)
            for c in cs
        }

    monkeypatch.setattr(type_mapping, "_score_all_concepts", all_descriptive_scores)
    mapped = map_concepts_to_types(concepts)
    assert all(m["mapped_category"] == "DESCRIPTIVE" for m in mapped)
