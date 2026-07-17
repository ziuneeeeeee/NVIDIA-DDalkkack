"""가상 학생(페르소나) 시뮬레이터.

흐름: 모의고사 1차 → 학습모드 N문제(실제 적응형 파이프라인 사용) → 모의고사 2차.
전 과정이 실제 사용자와 같은 테이블(attempts/topic_mastery/exam_sessions)에 기록되어,
관리자 페이지에서 성취도 변화와 난이도 궤적을 그대로 볼 수 있다.

정오답 판정: LLM 채점 없이 확률 모델로 결정한다.
- 페르소나 실력(ability 0~1)을 난이도 1~5 척도(skill = 1 + ability*4)로 환산
- 정답 확률 = 로지스틱(skill - 문제 난이도): 자기 수준과 같은 난이도면 50%,
  한 단계 쉬우면 ~75%, 한 단계 어려우면 ~25%
- 학습모드에서 문제를 풀 때마다 ability가 조금씩 상승(학습 효과 모사)
"""
import math
import random
import time

from . import db
from .adaptive import AdaptiveLearning
from .student_agent import answer_question, is_available as llm_available
from .tutor import grade_with_ai, explain_solution

LEARNING_GAIN_PER_QUESTION = 0.008  # 학습모드 1문제당 실력 상승폭 (simulated 모드)


def _p_correct(ability: float, difficulty) -> float:
    skill = 1 + ability * 4
    diff = int(difficulty) if difficulty else 3
    return 1 / (1 + math.exp(-1.1 * (skill - diff)))


def _take_exam(user_id: str, grade: str, ability: float, exam_gen, topic_name=None, rng=None):
    rng = rng or random
    questions = exam_gen.generate(grade, topic_name)
    correct = 0
    breakdown: dict = {}
    for q in questions:
        topic = q.get('topic_name') or q.get('sector2') or '기타'
        is_correct = rng.random() < _p_correct(ability, q.get('difficulty'))
        if is_correct:
            correct += 1
        slot = breakdown.setdefault(topic, {"correct": 0, "total": 0})
        slot["total"] += 1
        slot["correct"] += int(is_correct)
    score = round(correct / len(questions) * 100, 1) if questions else 0
    db.record_exam_session(user_id, grade, score, len(questions), correct, breakdown)
    return score


def _log(user_id, kind, question_id, meta):
    if meta:
        db.log_llm(user_id, kind, question_id, meta["prompt"], meta["response"],
                   meta["prompt_tokens"], meta["completion_tokens"], meta["model"])


def _answer_llm(user_id, question, ability, memory):
    """LLM 학생이 문제를 실제로 읽고 답안 텍스트를 생성 → 실제 채점 파이프라인으로 채점."""
    ans, meta = answer_question(question, ability, memory)
    if ans is None:
        return None
    _log(user_id, "persona_answer", question.get('id'), meta)
    is_correct, gmeta = grade_with_ai(question.get('question_text'), ans, question.get('answer_text'))
    _log(user_id, "grade", question.get('id'), gmeta)
    return is_correct


def _take_exam_llm(user_id, grade, ability, exam_gen, topic_name, memory):
    questions = exam_gen.generate(grade, topic_name)
    correct = 0
    breakdown: dict = {}
    for q in questions:
        topic = q.get('topic_name') or q.get('sector2') or '기타'
        is_correct = _answer_llm(user_id, q, ability, memory)
        if is_correct is None:  # LLM 실패 시 확률 모델로 폴백
            is_correct = random.random() < _p_correct(ability, q.get('difficulty'))
        if is_correct:
            correct += 1
        slot = breakdown.setdefault(topic, {"correct": 0, "total": 0})
        slot["total"] += 1
        slot["correct"] += int(is_correct)
    score = round(correct / len(questions) * 100, 1) if questions else 0
    db.record_exam_session(user_id, grade, score, len(questions), correct, breakdown)
    return score


def run_persona(qb, exam_gen, name: str, ability: float, grade: str,
                learning_count: int = 20, topic_name=None, seed=None, mode: str = "simulated"):
    rng = random.Random(seed) if seed is not None else random
    adaptive = AdaptiveLearning()

    if mode == "llm" and not llm_available():
        mode = "simulated"  # API 키 없으면 조용히 빠른 모드로

    user_id = f"persona:{name}-{int(time.time())}"
    ability_start = ability
    db.create_persona(user_id, name, ability, learning_count)

    memory: list[str] = []  # LLM 모드: 틀린 문제의 해설이 쌓여 다음 풀이에 반영됨

    if mode == "llm":
        score_before = _take_exam_llm(user_id, grade, ability, exam_gen, topic_name, memory)
    else:
        score_before = _take_exam(user_id, grade, ability, exam_gen, topic_name, rng)

    difficulty = 3
    trajectory = [difficulty]
    learned = 0
    for _ in range(learning_count):
        q = qb.search(grade=grade, topic_name=topic_name, difficulty=difficulty, count=1)
        if not q:
            break
        question = q[0]

        if mode == "llm":
            is_correct = _answer_llm(user_id, question, ability, memory)
            if is_correct is None:
                is_correct = rng.random() < _p_correct(ability, question.get('difficulty'))
        else:
            is_correct = rng.random() < _p_correct(ability, question.get('difficulty'))

        stats = db.record_attempt(
            user_id=user_id,
            question=question,
            grade=grade,
            is_correct=is_correct,
            mastery_before=None,
            mastery_after=None,
        )
        difficulty = adaptive.next_difficulty(difficulty, is_correct, streak=stats['prev_streak'])
        trajectory.append(difficulty)

        if mode == "llm":
            if not is_correct:
                # 틀리면 실제 튜터 해설을 받아서 학생 에이전트의 기억에 추가 (학습 루프)
                explanation, emeta = explain_solution(
                    question.get('answer_text'), stats['mastery'], question.get('question_text'))
                _log(user_id, "explain", question.get('id'), emeta)
                memory.append(explanation[:300])
        else:
            ability = min(0.98, ability + LEARNING_GAIN_PER_QUESTION)
        learned += 1

    if mode == "llm":
        score_after = _take_exam_llm(user_id, grade, ability, exam_gen, topic_name, memory)
    else:
        score_after = _take_exam(user_id, grade, ability, exam_gen, topic_name, rng)

    return {
        "user_id": user_id,
        "name": name,
        "grade": grade,
        "mode": mode,
        "ability_start": ability_start,
        "ability_end": round(ability, 3),
        "learning_count": learned,
        "lessons_learned": len(memory),
        "score_before": score_before,
        "score_after": score_after,
        "score_delta": round(score_after - score_before, 1),
        "difficulty_trajectory": trajectory,
    }
