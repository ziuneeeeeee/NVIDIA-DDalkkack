"""
main.py
────────
수강과목 학습도우미 — 채점 시스템 실행 진입점.

MD 섹션 10 개발 순서:
  (1) 파이썬 스크립트로 파이프라인 완성 ← 이 파일
  (2) FastAPI 엔드포인트로 감싸기 (api.py)
  (3) JS 프론트 연결

사용 예:
  python main.py

MD 섹션 8: 채점 일관성 확보
  - Temperature=0 고정 (모든 채점 LLM 호출 시)
  - 동일 (문제, 답안) 해시 → 캐싱으로 재채점 없이 동일 결과 반환
"""

from __future__ import annotations

import hashlib
import sys

# Windows 콘솔에서 이모지 출력 시 cp949 에러 방지
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()  # .env 파일에서 환경변수 로드 (OPENAI_API_KEY 등)

from graphs.grading_graph import grading_graph
from graphs.generation_graph import generation_graph
from core.models import Problem
from core.state import initial_state, initial_generation_state


# ──────────────────────────────────────────────
# 채점 결과 캐시 (MD 섹션 8.2)
# ──────────────────────────────────────────────

_grading_cache: dict[str, dict] = {}


def _get_cache_key(problem_id: str, student_answer: str) -> str:
    """동일 (문제, 답안) 조합의 캐시 키 생성 (MD 8.2)."""
    return hashlib.sha256(f"{problem_id}:{student_answer}".encode()).hexdigest()





def run_grading(problem: Problem, student_answer: str) -> dict:
    """
    문제 하나에 대한 채점 파이프라인 실행 (캐싱 포함).

    MD 8.2: 동일 (문제, 답안) 재입력 시 재호출 없이 동일 결과 반환.
    """
    cache_key = _get_cache_key(problem.problem_id, student_answer)
    if cache_key in _grading_cache:
        print(f"[main] 캐시 히트 — 재채점 없이 결과 반환")
        return _grading_cache[cache_key]

    state = initial_state(problem=problem, student_answer=student_answer)
    result = grading_graph.invoke(state)
    _grading_cache[cache_key] = result
    return result


def print_grade_result(result: dict) -> None:
    """채점 결과를 사람이 읽기 좋게 출력 (MD 5.3 최종 출력 형태)."""
    grade = result.get("grade_result")
    if not grade:
        print("❗ 채점 결과 없음")
        return

    print(f"\n{'='*60}")
    print(f"  최종 점수 : {grade.final_score:.1f} / {grade.max_score:.1f}점")
    print(f"  신뢰도    : {grade.confidence}")

    if grade.needs_human_review:
        print(f"  ⚠️  채점자 간 편차가 큽니다 → 사람 검토 권장")
    print(f"  채점 동의 : {grade.grader_agreement}")

    if result.get("rubric"):
        print(f"\n  [생성된 채점 기준 (루브릭)]")
        for c in result["rubric"]:
            print(f"    • {c.point_name} ({c.max_score}점): {c.description}")

    if grade.per_criterion:
        print(f"\n  [항목별 감점 및 평가 내역]")
        for item in grade.per_criterion[:5]:  # 최대 5개 출력
            if isinstance(item, dict):
                print(f"    • {item}")

    diagnosis = result.get("diagnosis")
    if diagnosis:
        print(f"\n  [오답 원인 진단]")
        print(f"    유형     : {diagnosis.error_type}")
        print(f"    부족 개념 : {diagnosis.weak_concept}")
        print(f"    설명     : {diagnosis.detail}")

    print(f"\n  [다음 추천 학습]")
    print(f"    개념    : {result.get('next_concept', '-')}")
    print(f"    난이도   : {result.get('next_difficulty', '-')}")
    print(f"{'='*60}\n")


def run_generation(concept: str, target_difficulty: str = "중", question_type: str = "") -> Problem | None:
    print(f"\n[{concept}] 개념에 대한 문제 생성을 시작합니다 (난이도: {target_difficulty})...")
    state = initial_generation_state(
        concept=concept, target_difficulty=target_difficulty, context="", question_type=question_type
    )
    result = generation_graph.invoke(state)
    if result.get("is_accepted") and result.get("final_problem"):
        print("✅ 문제 생성이 완료되었습니다.")
        return result["final_problem"]
    else:
        print("❌ 문제 생성에 실패했습니다.")
        return None

def main() -> None:
    print("=" * 60)
    print("  수강과목 학습도우미 — 멀티에이전트 문제 생성 및 채점 시스템")
    print("  생성: Generator -> Validator -> Difficulty -> Concluder")
    print("  채점: Strict / Lenient / Keyword 에이전트 교차검증")
    print("=" * 60)

    while True:
        concept = input("\n학습할 개념을 입력하세요 (종료: q): ").strip()
        if concept.lower() == "q":
            print("세션 종료")
            break
        if not concept:
            continue

        problem = run_generation(concept)
        if not problem:
            continue

        print(f"\n[새로운 문제] ({problem.type})")
        print(f"  {problem.question}")

        student_answer = input("  답안 입력 (건너뛰기: q): ").strip()
        if student_answer.lower() == "q":
            continue

        result = run_grading(problem, student_answer)
        print_grade_result(result)


if __name__ == "__main__":
    main()
