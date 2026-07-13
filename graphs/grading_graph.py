from __future__ import annotations

from langgraph.graph import StateGraph, END

from core.state import GradingState
from nodes.parse_problem import parse_problem
from nodes.retrieve import retrieve
from nodes.rubric import get_or_create_rubric
from nodes.objective_grading import grade_objective
from nodes.essay_grading import critique_strict, critique_lenient, critique_keyword
from nodes.judge import judge_grading
from nodes.code_grading import grade_code
from nodes.diagnose import diagnose

def route_by_type(state: GradingState) -> str:
    t = state["problem"].type
    if t in ("객관식", "단답형"):
        return "objective"
    elif t == "서술형":
        return "essay"
    elif t == "코딩형":
        return "code"
    raise ValueError(f"알 수 없는 문제 유형: {t}")

def build_grading_graph() -> StateGraph:
    g = StateGraph(GradingState)

    # ── 노드 등록 ────────────────────────────────────────────────
    g.add_node("parse_problem", parse_problem)
    g.add_node("retrieve", retrieve)
    g.add_node("get_rubric", get_or_create_rubric)

    # 채점 노드들
    g.add_node("grade_objective", grade_objective)          # 객관식/단답형
    g.add_node("critique_strict", critique_strict)          # 서술형 - 근거중심
    g.add_node("critique_lenient", critique_lenient)        # 서술형 - 의미이해
    g.add_node("critique_keyword", critique_keyword)        # 서술형 - 핵심키워드
    g.add_node("judge_grading", judge_grading)              # 서술형 - 편차 조율
    g.add_node("grade_code", grade_code)                    # 코딩형

    g.add_node("diagnose", diagnose)

    # ── 공통 전처리 경로 ─────────────────────────────────────────
    g.set_entry_point("parse_problem")
    g.add_edge("parse_problem", "retrieve")
    g.add_edge("retrieve", "get_rubric")

    # ── 유형별 분기 ─────────────────────────────────────
    g.add_conditional_edges(
        "get_rubric",
        route_by_type,
        {
            "objective": "grade_objective",
            "essay":     "critique_strict",   # 서술형: 3종 critique 순차 실행
            "code":      "grade_code",
        },
    )

    # ── 서술형 채점 순서 ─────────────────────────────────────────
    g.add_edge("critique_strict", "critique_lenient")
    g.add_edge("critique_lenient", "critique_keyword")
    g.add_edge("critique_keyword", "judge_grading")

    # ── 채점 → 진단 → END ───────────────────────────────
    for grade_node in ("grade_objective", "judge_grading", "grade_code"):
        g.add_edge(grade_node, "diagnose")

    g.add_edge("diagnose", END)

    return g.compile()

grading_graph = build_grading_graph()
