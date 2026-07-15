"""
nodes/objective_grading.py 테스트. 실제 LLM 호출(_semantic_match)은
모킹해서, "언제 의미 판정으로 넘어가는지" 분기 로직만 검증한다.
"""

import nodes.objective_grading as og
from core.models import Problem
from core.state import initial_state


def _state(problem_type: str, correct: str, student: str) -> dict:
    problem = Problem(problem_id="p1", type=problem_type, question="q", answer=correct)
    return initial_state(problem=problem, student_answer=student)


def test_exact_match_gives_full_score_without_calling_semantic_match(monkeypatch):
    def fail_if_called(*a, **kw):
        raise AssertionError("완전일치인데 의미 판정을 호출하면 안 된다 (비용 낭비)")
    monkeypatch.setattr(og, "_semantic_match", fail_if_called)

    result = og.grade_objective(_state("단답형", "정답입니다", "정답입니다"))["grade_result"]
    assert result.final_score == 10.0
    assert "완전일치" in result.per_criterion[0]["reason"]


def test_multiple_choice_mismatch_scores_zero_without_semantic_fallback(monkeypatch):
    def fail_if_called(*a, **kw):
        raise AssertionError("객관식은 의미 판정으로 넘어가면 안 된다")
    monkeypatch.setattr(og, "_semantic_match", fail_if_called)

    result = og.grade_objective(_state("객관식", "B", "A"))["grade_result"]
    assert result.final_score == 0.0


def test_true_false_mismatch_scores_zero_without_semantic_fallback(monkeypatch):
    def fail_if_called(*a, **kw):
        raise AssertionError("참거짓은 의미 판정으로 넘어가면 안 된다")
    monkeypatch.setattr(og, "_semantic_match", fail_if_called)

    result = og.grade_objective(_state("참거짓", "참", "거짓"))["grade_result"]
    assert result.final_score == 0.0


def test_short_answer_mismatch_falls_back_to_semantic_match_and_can_still_score_full(monkeypatch):
    monkeypatch.setattr(og, "_semantic_match", lambda q, c, s: (True, "핵심 의미가 동일함"))

    result = og.grade_objective(_state(
        "단답형",
        "입력 데이터가 모델의 네트워크를 통과하면서 각 계층에서의 출력을 계산하는 것.",
        "입력 데이터를 바탕으로 뉴런의 연산을 거쳐 최종 예측값을 출력하는 것",
    ))["grade_result"]

    assert result.final_score == 10.0
    assert "의미 판정" in result.per_criterion[0]["reason"]


def test_short_answer_mismatch_falls_back_and_can_still_score_zero(monkeypatch):
    monkeypatch.setattr(og, "_semantic_match", lambda q, c, s: (False, "핵심 내용이 다름"))

    result = og.grade_objective(_state("단답형", "12", "10"))["grade_result"]
    assert result.final_score == 0.0
