from __future__ import annotations

from core.state import GradingState
from core.models import ConceptMastery

DIFFICULTY_ORDER = ["하", "중", "상"]

def _upgrade(d: str) -> str:
    """난이도 한 단계 상향."""
    idx = DIFFICULTY_ORDER.index(d) if d in DIFFICULTY_ORDER else 1
    return DIFFICULTY_ORDER[min(idx + 1, 2)]

def _downgrade(d: str) -> str:
    """난이도 한 단계 하향."""
    idx = DIFFICULTY_ORDER.index(d) if d in DIFFICULTY_ORDER else 1
    return DIFFICULTY_ORDER[max(idx - 1, 0)]

def _get_prerequisite_concepts(concept: str, concept_graph: dict) -> list[str]:
    """개념 그래프에서 선행개념 조회."""
    return concept_graph.get(concept, [])

CONCEPT_GRAPH: dict[str, list[str]] = {
    "Dijkstra":              ["BFS", "우선순위 큐", "그래프 기초"],
    "Dynamic Programming":   ["재귀", "메모이제이션"],
    "B+ Tree":               ["B-Tree", "이진 탐색 트리"],
    "최소 신장 트리(MST)":    ["그래프 기초", "Union-Find"],
    "네트워크 플로우":         ["BFS", "그래프 기초"],
    "운영체제 스케줄링":       ["프로세스 개념", "큐"],
    "페이지 교체 알고리즘":    ["가상 메모리", "운영체제 스케줄링"],
}

def adjust_difficulty(state: GradingState) -> dict:
    """
    적응형 난이도 조정 로직.
    """
    grade = state["grade_result"]
    mastery_map: dict[str, ConceptMastery] = dict(state.get("concept_mastery", {}))
    concept = state["problem"].question[:20]

    m = mastery_map.get(concept, ConceptMastery(concept=concept))
    is_correct = grade and grade.final_score >= grade.max_score

    m.attempts += 1
    if is_correct:
        m.correct += 1
        m.consecutive_correct += 1
        m.consecutive_wrong = 0
    else:
        m.consecutive_wrong += 1
        m.consecutive_correct = 0
    m.mastery_score = m.correct / m.attempts
    mastery_map[concept] = m

    if m.consecutive_correct >= 2:
        next_concept = concept
        next_difficulty = _upgrade(m.current_difficulty)
        print(f"[adjust] 연속 정답 2회 → 난이도 상향: {m.current_difficulty} → {next_difficulty}")
    elif m.consecutive_wrong >= 2:
        prereqs = _get_prerequisite_concepts(concept, CONCEPT_GRAPH)
        if prereqs:
            next_concept = prereqs[0]
            next_difficulty = "하"
            print(f"[adjust] 연속 오답 2회 → 선행개념으로 회귀: {next_concept} / 하")
        else:
            next_concept = concept
            next_difficulty = _downgrade(m.current_difficulty)
            print(f"[adjust] 연속 오답 2회 → 난이도 하향: {m.current_difficulty} → {next_difficulty}")
    else:
        next_concept = concept
        next_difficulty = m.current_difficulty
        print(f"[adjust] 유지: {concept} / {next_difficulty}")

    return {
        "concept_mastery": mastery_map,
        "next_concept": next_concept,
        "next_difficulty": next_difficulty,
    }
