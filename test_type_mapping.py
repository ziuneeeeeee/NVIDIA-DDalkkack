"""
type_mapping.py의 순수 로직 테스트.
LLM 호출 없이(=API 키 불필요) 매핑 로직만 검증한다.
"""

import pytest

import nodes.type_mapping as type_mapping
from nodes.type_mapping import ConceptScore, map_concepts_to_types, pick_category


def _score(concept_id: str, **overrides) -> ConceptScore:
    base = dict(
        concept_id=concept_id,
        calc_eligible=False,
        calculation_score=0,
        multiple_choice_score=0,
        true_false_score=0,
        descriptive_score=0,
        mapping_reason="테스트용 근거",
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

def test_map_concepts_to_types_never_drops_or_pads_input(monkeypatch):
    """팀원1이 이미 선별해서 보내주므로, 몇 개가 오든(20개 초과 포함) 그대로
    전부 매핑해야 한다. 개수를 자르거나 채우지 않는다."""
    concepts = [_fake_concept(i) for i in range(37)]

    def fake_scores(cs):
        return {
            c["concept_id"]: _score(c["concept_id"], multiple_choice_score=80, true_false_score=10, descriptive_score=10)
            for c in cs
        }

    monkeypatch.setattr(type_mapping, "_score_all_concepts", fake_scores)
    mapped = map_concepts_to_types(concepts)

    assert len(mapped) == 37
    assert {m["concept_id"] for m in mapped} == {c["concept_id"] for c in concepts}


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


def test_map_concepts_to_types_preserves_original_fields_and_order(monkeypatch):
    concepts = [_fake_concept(i, source_title=f"slide{i}") for i in range(3)]

    def fake_scores(cs):
        return {c["concept_id"]: _score(c["concept_id"], multiple_choice_score=50) for c in cs}

    monkeypatch.setattr(type_mapping, "_score_all_concepts", fake_scores)
    mapped = map_concepts_to_types(concepts)

    assert [m["concept_id"] for m in mapped] == ["c0", "c1", "c2"]
    assert mapped[1]["source_title"] == "slide1"
    assert "difficulty" not in mapped[0]  # 난이도는 팀원2 책임 범위 아님
