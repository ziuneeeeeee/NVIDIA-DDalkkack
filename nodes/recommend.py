from __future__ import annotations
from core.state import GradingState

def recommend_next_problem(state: GradingState) -> dict:
    """
    다음 문제는 생성 아닌 기존 문제 풀에서 RAG 검색으로 추천.
    """
    concept = state["next_concept"]
    difficulty = state["next_difficulty"]
    print(f"[recommend] 다음 문제 검색: 개념={concept}, 난이도={difficulty}")

    return {"problem_count": state.get("problem_count", 0) + 1}
