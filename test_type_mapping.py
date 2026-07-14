"""
type_mapping.py의 결정론적 배정 로직 테스트.
LLM 호출 없이(=API 키 불필요) 순수 함수만 검증한다.
"""

import random
from collections import Counter

import pytest

import nodes.type_mapping as type_mapping
from nodes.type_mapping import (
    CATEGORY_TARGET_COUNTS,
    ConceptScore,
    DIFFICULTY_TARGET_COUNTS,
    TARGET_TOTAL,
    assign_by_quota,
    finalize_category,
    map_concepts_to_types,
    scale_quota,
)


def test_scale_quota_returns_target_as_is_when_total_matches():
    assert scale_quota(CATEGORY_TARGET_COUNTS, TARGET_TOTAL) == CATEGORY_TARGET_COUNTS


def test_scale_quota_sum_always_matches_actual_total():
    for n in [0, 1, 4, 7, 13, 20, 25, 47]:
        scaled = scale_quota(CATEGORY_TARGET_COUNTS, n)
        assert sum(scaled.values()) == n
        scaled_diff = scale_quota(DIFFICULTY_TARGET_COUNTS, n)
        assert sum(scaled_diff.values()) == n


def test_scale_quota_no_negative_counts():
    for n in [0, 1, 3]:
        scaled = scale_quota(DIFFICULTY_TARGET_COUNTS, n)
        assert all(v >= 0 for v in scaled.values())


def test_assign_by_quota_matches_quota_exactly():
    quota = {"A": 2, "B": 1}
    items = [
        ("c1", {"A": 90, "B": 10}),
        ("c2", {"A": 80, "B": 20}),
        ("c3", {"A": 70, "B": 95}),
    ]
    result = assign_by_quota(items, quota)
    counts = Counter(result.values())
    assert counts["A"] == 2
    assert counts["B"] == 1
    assert set(result.keys()) == {"c1", "c2", "c3"}


def test_assign_by_quota_prefers_higher_scores_when_quota_allows():
    quota = {"A": 1, "B": 1}
    items = [
        ("c1", {"A": 100, "B": 0}),
        ("c2", {"A": 0, "B": 100}),
    ]
    result = assign_by_quota(items, quota)
    assert result["c1"] == "A"
    assert result["c2"] == "B"


def test_assign_by_quota_bumps_loser_when_top_choice_quota_full():
    # c1, c2 모두 A를 가장 선호하지만 A 정원은 1명뿐 -> 점수가 낮은 쪽이 B로 밀려남
    quota = {"A": 1, "B": 1}
    items = [
        ("c1", {"A": 100, "B": 10}),
        ("c2", {"A": 90, "B": 20}),
    ]
    result = assign_by_quota(items, quota)
    assert result["c1"] == "A"
    assert result["c2"] == "B"


def test_finalize_category_forces_descriptive_when_calc_ineligible():
    # calculation_score가 아무리 높아도 calc_eligible=False면 CALCULATION이 될 수 없다
    result = finalize_category(
        bucket="DESCRIPTIVE_OR_CALCULATION",
        calc_eligible=False,
        calculation_score=99,
        descriptive_score=10,
    )
    assert result == "DESCRIPTIVE"


def test_finalize_category_picks_calculation_when_eligible_and_higher():
    result = finalize_category(
        bucket="DESCRIPTIVE_OR_CALCULATION",
        calc_eligible=True,
        calculation_score=80,
        descriptive_score=40,
    )
    assert result == "CALCULATION"


def test_finalize_category_passes_through_non_combined_bucket():
    assert finalize_category("MULTIPLE_CHOICE", True, 0, 0) == "MULTIPLE_CHOICE"
    assert finalize_category("TRUE_FALSE", True, 0, 0) == "TRUE_FALSE"


def test_target_counts_sum_to_20():
    assert sum(CATEGORY_TARGET_COUNTS.values()) == TARGET_TOTAL == 20
    assert sum(DIFFICULTY_TARGET_COUNTS.values()) == TARGET_TOTAL == 20


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


# ── 20개 규모 종단 검증 (LLM 호출은 합성 점수로 대체) ───────────────

def _synthetic_scores(concepts: list[dict]) -> dict[str, ConceptScore]:
    rng = random.Random(42)
    scores = {}
    for c in concepts:
        calc_eligible = rng.random() < 0.3
        scores[c["concept_id"]] = ConceptScore(
            concept_id=c["concept_id"],
            calc_eligible=calc_eligible,
            calculation_score=rng.randint(0, 100) if calc_eligible else rng.randint(0, 20),
            multiple_choice_score=rng.randint(0, 100),
            true_false_score=rng.randint(0, 100),
            descriptive_score=rng.randint(0, 100),
            mapping_reason="테스트용 합성 근거",
            easy_score=rng.randint(0, 100),
            medium_score=rng.randint(0, 100),
            hard_score=rng.randint(0, 100),
            difficulty_reason="테스트용 합성 근거",
        )
    return scores


def test_map_concepts_to_types_hits_exact_20_target_with_synthetic_scores(monkeypatch):
    concepts = [_fake_concept(i) for i in range(20)]
    monkeypatch.setattr(type_mapping, "_score_all_concepts", _synthetic_scores)

    mapped = map_concepts_to_types(concepts)

    assert len(mapped) == 20
    category_counts = Counter(m["mapped_category"] for m in mapped)
    difficulty_counts = Counter(m["difficulty"] for m in mapped)

    assert category_counts["MULTIPLE_CHOICE"] == 8
    assert category_counts["TRUE_FALSE"] == 6
    assert category_counts["CALCULATION"] + category_counts["DESCRIPTIVE"] == 6

    assert difficulty_counts["쉬움"] == 6
    assert difficulty_counts["보통"] == 10
    assert difficulty_counts["어려움"] == 4

    # 원본 필드가 보존되는지도 함께 확인
    assert mapped[0]["concept_name"] == "개념 0"
    assert "mapping_reason" in mapped[0]
    assert "difficulty_reason" in mapped[0]
