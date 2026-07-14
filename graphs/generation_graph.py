from langgraph.graph import StateGraph, END
from core.state import GenerationState
from nodes.generation import (
    classify_question_type_node,
    generate_problem_node,
    verify_problem_node,
    judge_difficulty_node,
    conclude_problem_node
)

def should_continue(state: GenerationState) -> str:
    if state.get("is_accepted"):
        return END
    if state.get("retry_count", 0) >= 3:
        # 최대 재시도 횟수 초과 시 종료 (실제로는 fallback 문제 리턴 등 처리 가능)
        print("⚠️ 최대 재시도 횟수 초과로 문제 생성을 종료합니다.")
        return END
    return "generate"

def build_generation_graph() -> StateGraph:
    g = StateGraph(GenerationState)
    
    from nodes.retrieve import retrieve
    g.add_node("retrieve", retrieve)
    g.add_node("classify_type", classify_question_type_node)
    g.add_node("generate", generate_problem_node)
    g.add_node("verify", verify_problem_node)
    g.add_node("judge", judge_difficulty_node)
    g.add_node("conclude", conclude_problem_node)

    g.set_entry_point("retrieve")

    g.add_edge("retrieve", "classify_type")
    g.add_edge("classify_type", "generate")
    g.add_edge("generate", "verify")
    g.add_edge("generate", "judge")
    # 검증과 난이도 평가는 동일한 초안을 독립적으로 평가한다. 두 평가가
    # 모두 끝난 뒤에만 최종 판정이 실행되도록 합류 지점을 명시한다.
    g.add_edge(["verify", "judge"], "conclude")
    
    g.add_conditional_edges(
        "conclude",
        should_continue,
        {
            END: END,
            "generate": "generate"
        }
    )
    
    return g.compile()

generation_graph = build_generation_graph()
