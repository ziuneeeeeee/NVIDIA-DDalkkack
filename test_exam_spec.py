"""
core/exam_spec.py 테스트. LLM 호출 없이 순수 배분 로직만 검증한다.
"""

from collections import Counter

import pytest

from core.exam_spec import allocate_question_counts, build_exam_specs


def _concept(cid: str, category: str = "DESCRIPTIVE", importance: str = "important") -> dict:
    return {
        "concept_id": cid,
        "concept_name": f"개념 {cid}",
        "mapped_category": category,
        "mapping_reason": "테스트용 근거",
        "importance": importance,
    }


def test_allocate_question_counts_sums_to_target():
    concepts = [_concept(f"c{i}") for i in range(5)]
    counts = allocate_question_counts(concepts, 12)
    assert sum(counts) == 12
    assert all(c >= 1 for c in counts)  # 모든 개념 최소 1문제


def test_allocate_question_counts_favors_higher_importance():
    concepts = [_concept("core", importance="core"), _concept("supp", importance="supplementary")]
    counts = allocate_question_counts(concepts, 10)
    core_count = counts[0]
    supp_count = counts[1]
    assert core_count > supp_count


def test_build_exam_specs_uses_all_concepts_when_fewer_than_target():
    concepts = [_concept(f"c{i}") for i in range(3)]
    specs = build_exam_specs(concepts, question_count=9)
    assert len(specs) == 9
    concept_ids_used = {s.concept_id for s in specs}
    assert concept_ids_used == {"c0", "c1", "c2"}  # 3개 모두 재사용됨


def test_build_exam_specs_picks_top_importance_when_more_concepts_than_target():
    concepts = [
        _concept("core1", importance="core"),
        _concept("core2", importance="core"),
        _concept("supp1", importance="supplementary"),
        _concept("supp2", importance="supplementary"),
    ]
    specs = build_exam_specs(concepts, question_count=2)
    assert len(specs) == 2
    assert {s.concept_id for s in specs} == {"core1", "core2"}


def test_build_exam_specs_cycles_difficulty_across_repeated_concept():
    concepts = [_concept("c0")]
    specs = build_exam_specs(concepts, question_count=3)
    difficulties = [s.difficulty for s in specs]
    assert set(difficulties) == {"하", "중", "상"}  # 3문제 모두 다른 난이도


def test_build_exam_specs_keeps_mapped_category_fixed_per_concept_across_difficulty():
    # 같은 개념이 여러 난이도로 반복돼도 유형(mapped_category)은 바뀌지 않는다
    concepts = [_concept("c0", category="MULTIPLE_CHOICE")]
    specs = build_exam_specs(concepts, question_count=3)
    assert all(s.mapped_category == "MULTIPLE_CHOICE" for s in specs)


def test_build_exam_specs_rejects_empty_input():
    with pytest.raises(ValueError):
        build_exam_specs([], question_count=5)


def test_build_exam_specs_rejects_missing_mapped_category():
    concepts = [{"concept_id": "c0", "concept_name": "개념"}]  # mapped_category 없음
    with pytest.raises(ValueError, match="mapped_category"):
        build_exam_specs(concepts, question_count=1)
