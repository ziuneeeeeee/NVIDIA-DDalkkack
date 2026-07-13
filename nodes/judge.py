from __future__ import annotations
import statistics
from core.state import GradingState
from core.models import GradeResult, CritiqueResult

def _aggregate_criterion_feedback(critiques: list[CritiqueResult]) -> list[dict]:
    """항목별로 채점자들의 점수/근거를 집계하여 프론트엔드 형식에 맞춤."""
    if not critiques:
        return []
        
    # 중앙값에 가장 가까운 총점을 가진 critique를 대표(median)로 선택
    sorted_critiques = sorted(critiques, key=lambda c: c.total_score)
    median_critique = sorted_critiques[len(sorted_critiques)//2]
    
    per_criterion = []
    for r in median_critique.breakdown:
        per_criterion.append({
            "point_name": r.point_name,
            "earned_score": r.score_earned,
            "reason": f"[{median_critique.critic} 에이전트 기준] {r.reason}"
        })
    return per_criterion

def judge_grading(state: GradingState) -> dict:
    """
    채점자 간 점수 종합:
    - 중앙값 채택 (극단값에 강건)
    - 편차 > max_score*30% → needs_human_review=True
    """
    critiques = state["critiques"]
    max_score = float(sum(c.max_score for c in state["rubric"])) or 10.0

    scores = [c.total_score for c in critiques]
    variance = max(scores) - min(scores) if scores else 0
    final_score = statistics.median(scores) if scores else 0.0
    needs_review = variance > (max_score * 0.3)

    print(
        f"[judge_grading] 점수: {scores} → 중앙값={final_score} | "
        f"편차={variance:.1f} | 사람검토={'필요' if needs_review else '불필요'}"
    )

    result = GradeResult(
        final_score=final_score,
        max_score=max_score,
        per_criterion=_aggregate_criterion_feedback(critiques),
        confidence="low" if needs_review else "high",
        needs_human_review=needs_review,
        grader_agreement=(
            f"채점자 {len(critiques)}명 점수: {scores}, 중앙값 채택"
            + (" ⚠️ 편차 큼 → 사람 검토 권장" if needs_review else "")
        ),
    )
    return {"grade_result": result}
