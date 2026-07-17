import os
import random
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, '.env'))
persona_env = os.path.join(base_dir, '..', '..', 'persona-math-mvp', '.env')
if os.path.exists(persona_env):
    load_dotenv(persona_env)

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from core.question_bank import QuestionBank
from core.exam import MockExamGenerator
from core.adaptive import AdaptiveLearning
from core.tutor import explain_solution, generate_hints, grade_with_ai
from core.mcq import extract_mcq_options
from core import db
from core.persona import run_persona
from core import tutor_agent
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

images_dir = os.path.join(base_dir, 'data', 'images')
if os.path.isdir(images_dir):
    app.mount("/images", StaticFiles(directory=images_dir), name="images")

corpus_path = os.path.join(base_dir, 'data', 'corpus_all_grades.json')
qb = QuestionBank(corpus_path)
exam_gen = MockExamGenerator(qb)
adaptive = AdaptiveLearning()
db.init_db()


def _pick_focus_topic(user_id: str, grade: str) -> Optional[Dict[str, Any]]:
    """취약 토픽(mastery가 낮을수록)에 가중치를 둬서 하나를 무작위로 고른다.

    topic_key만 넘기면 해당 난이도에 그 세부주제 문제가 없을 때 검색이 조용히
    완전 무작위로 풀려버리므로, sector2도 함께 반환해 넓은 범위로 폴백하게 한다.
    """
    report = db.get_topic_report(user_id, grade)
    candidates = [r for r in report if r['attempt_count'] >= 1]
    if not candidates:
        return None
    weights = [max(0.05, 1 - r['mastery']) for r in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


class ExamGenerateReq(BaseModel):
    grade: str
    topic_name: Optional[str] = None
    sector2: Optional[str] = None
    sector1: Optional[str] = None

class AnswerItem(BaseModel):
    question_id: str
    user_answer: str
    correct_answer: str
    question_text: Optional[str] = None

class ExamGradeReq(BaseModel):
    answers: List[AnswerItem]
    # 성취도 추이용 점수 스냅샷(exam_sessions)에만 쓰인다. topic_mastery는 건드리지 않는다.
    user_id: Optional[str] = None
    grade: Optional[str] = None

class SingleLearningNextReq(BaseModel):
    grade: str
    topic_name: Optional[str] = None
    current_difficulty: int
    user_id: Optional[str] = None
    focus_weak: bool = False

class SingleGradeReq(BaseModel):
    user_answer: str
    correct_answer: str
    current_mastery: float
    current_difficulty: int
    question_text: Optional[str] = None
    question_id: Optional[str] = None
    grade: Optional[str] = None
    topic_name: Optional[str] = None
    sector1: Optional[str] = None
    sector2: Optional[str] = None
    hint_used: bool = False
    user_id: Optional[str] = None

class ExplainReq(BaseModel):
    correct_answer: str
    current_mastery: float
    question_text: Optional[str] = None
    user_id: Optional[str] = None

class TopicCheckReq(BaseModel):
    grade: str
    topic_name: Optional[str] = None

class PersonaRunReq(BaseModel):
    name: str
    ability: float
    grade: str
    learning_count: int = 20
    topic_name: Optional[str] = None
    mode: str = "simulated"  # "simulated"(확률 모델, 즉시) | "llm"(LLM 학생 에이전트, 수 분 소요)

def _with_options(q):
    if q is None:
        return None
    return {**q, "options": extract_mcq_options(q.get("question_text"))}

@app.post("/topic/check")
def check_topic(req: TopicCheckReq):
    return {"matched": qb.has_keyword_match(req.grade, req.topic_name)}

@app.post("/mock_exam/generate")
def generate_mock_exam(req: ExamGenerateReq):
    questions = exam_gen.generate(req.grade, req.topic_name, req.sector2, req.sector1)
    return {"questions": [_with_options(q) for q in questions]}

@app.post("/mock_exam/grade")
def grade_mock_exam(req: ExamGradeReq):
    results = []
    correct_count = 0
    breakdown: Dict[str, Dict[str, int]] = {}
    for ans in req.answers:
        is_correct, meta = grade_with_ai(ans.question_text, ans.user_answer, ans.correct_answer)
        db.log_llm(req.user_id, "grade", ans.question_id, meta["prompt"], meta["response"],
                   meta["prompt_tokens"], meta["completion_tokens"], meta["model"])
        if is_correct:
            correct_count += 1
        results.append({
            "question_id": ans.question_id,
            "is_correct": is_correct
        })
        question = qb.get_by_id(ans.question_id)
        if question:
            topic = question.get('topic_name') or question.get('sector2') or '기타'
            slot = breakdown.setdefault(topic, {"correct": 0, "total": 0})
            slot["total"] += 1
            slot["correct"] += int(is_correct)

    score = (correct_count / len(req.answers) * 100) if req.answers else 0

    if req.user_id and req.grade and req.answers:
        db.record_exam_session(req.user_id, req.grade, score, len(req.answers), correct_count, breakdown)

    return {"results": results, "score": score, "total": 100}

@app.post("/single_learning/next")
def get_next_question(req: SingleLearningNextReq):
    topic_name = req.topic_name
    sector2 = None
    focus_topic = None
    if req.focus_weak and not topic_name and req.user_id:
        picked = _pick_focus_topic(req.user_id, req.grade)
        if picked:
            focus_topic = picked["topic_key"]
            topic_name = focus_topic
            sector2 = picked.get("sector2")

    q = qb.search(grade=req.grade, topic_name=topic_name, sector2=sector2, difficulty=req.current_difficulty, count=1)
    question = q[0] if q else None

    # 이 문제가 속한 개념의 누적 이해도(DB)를 함께 내려줘서, 화면의 "이해도"가
    # 세션 임시값이 아니라 항상 topic_mastery 하나만 가리키게 한다.
    topic_mastery = 0.5
    if question and req.user_id:
        row = db.get_topic_mastery(req.user_id, req.grade, db.topic_key_for(question))
        if row is not None:
            topic_mastery = row["mastery"]

    return {
        "question": _with_options(question),
        "focus_topic": focus_topic,
        "topic_mastery": topic_mastery,
    }

@app.post("/single_learning/grade")
def grade_single(req: SingleGradeReq):
    is_correct, meta = grade_with_ai(req.question_text, req.user_answer, req.correct_answer)
    db.log_llm(req.user_id, "grade", req.question_id, meta["prompt"], meta["response"],
               meta["prompt_tokens"], meta["completion_tokens"], meta["model"])
    new_mastery = adaptive.update_mastery(req.current_mastery, is_correct)

    prev_streak = 0
    topic_stats = None
    next_topic = None
    agent_reasoning = None
    used_agent = False

    if req.grade:
        question = {
            "id": req.question_id,
            "topic_name": req.topic_name,
            "sector1": req.sector1,
            "sector2": req.sector2,
            "difficulty": req.current_difficulty,
        }
        topic_stats = db.record_attempt(
            user_id=req.user_id or "anonymous",
            question=question,
            grade=req.grade,
            is_correct=is_correct,
            hint_used=req.hint_used,
            mastery_before=req.current_mastery,
            mastery_after=new_mastery,
        )
        prev_streak = topic_stats["prev_streak"]

        # 다음 난이도/개념을 규칙(±1) 대신 학생 프로필 전체를 보는 에이전트가 판단하게 한다.
        # LLM을 못 쓰거나 응답이 이상하면 조용히 규칙 기반으로 폴백한다.
        topic_report = db.get_topic_report(req.user_id or "anonymous", req.grade)
        recent = db.get_recent_attempts(req.user_id or "anonymous", req.grade, limit=5)
        decision, ameta = tutor_agent.decide_next(
            question, is_correct, req.current_difficulty, prev_streak,
            topic_report, recent, req.hint_used)

        if decision:
            used_agent = True
            next_difficulty = decision["next_difficulty"]
            next_topic = decision["next_topic"]
            agent_reasoning = decision["reasoning"]
            db.log_llm(req.user_id, "tutor_agent", req.question_id, ameta["prompt"], ameta["response"],
                       ameta["prompt_tokens"], ameta["completion_tokens"], ameta["model"])
            print(f"[tutor_agent] user={req.user_id!r} topic={question.get('topic_name')!r} "
                  f"is_correct={is_correct} streak={prev_streak} => difficulty "
                  f"{req.current_difficulty}->{next_difficulty}"
                  + (f", switch to {next_topic!r}" if next_topic else "")
                  + f" | {agent_reasoning}")
        else:
            next_difficulty = adaptive.next_difficulty(req.current_difficulty, is_correct, streak=prev_streak)
            print(f"[tutor_agent] SKIPPED (LLM unavailable) -> rule-based fallback: "
                  f"difficulty {req.current_difficulty}->{next_difficulty}")
    else:
        next_difficulty = adaptive.next_difficulty(req.current_difficulty, is_correct, streak=prev_streak)

    return {
        "is_correct": is_correct,
        "new_mastery": new_mastery,
        "next_difficulty": next_difficulty,
        "next_topic": next_topic,
        "agent_reasoning": agent_reasoning,
        "used_agent": used_agent,
        "streak": topic_stats["streak"] if topic_stats else (1 if is_correct else -1),
        "topic_mastery": topic_stats["mastery"] if topic_stats else None,
    }

@app.post("/single_learning/explain")
def explain_single(req: ExplainReq):
    explanation, meta = explain_solution(req.correct_answer, req.current_mastery, req.question_text)
    db.log_llm(req.user_id, "explain", None, meta["prompt"], meta["response"],
               meta["prompt_tokens"], meta["completion_tokens"], meta["model"])
    return {"explanation": explanation}

@app.get("/single_learning/hint")
def get_hint(answer_text: str, question_text: Optional[str] = None, user_id: Optional[str] = None):
    hints, meta = generate_hints(answer_text, question_text)
    db.log_llm(user_id, "hint", None, meta["prompt"], meta["response"],
               meta["prompt_tokens"], meta["completion_tokens"], meta["model"])
    return {"hints": hints}

@app.get("/report/topic-mastery")
def report_topic_mastery(user_id: str, grade: Optional[str] = None):
    return {"topics": db.get_topic_report(user_id, grade)}

@app.get("/review/wrong-questions")
def review_wrong_questions(user_id: str, grade: Optional[str] = None, limit: int = 50):
    rows = db.get_wrong_question_ids(user_id, grade, limit)
    by_id = {q["id"]: q for q in qb.get_by_ids([r["question_id"] for r in rows])}
    ordered = [_with_options(by_id[r["question_id"]]) for r in rows if r["question_id"] in by_id]
    return {"questions": ordered}

@app.get("/review/due")
def review_due(user_id: str, grade: Optional[str] = None, limit: int = 5):
    return {"topics": db.get_due_topics(user_id, grade, limit)}

# ---------- 관리자 ----------

# gpt-4o-mini 기준 100만 토큰당 달러 단가 (입력/출력)
_PRICE_IN_PER_M = 0.15
_PRICE_OUT_PER_M = 0.60

@app.get("/admin/overview")
def admin_overview():
    usage = db.get_llm_usage_summary()
    total_prompt = sum(u["prompt_tokens"] or 0 for u in usage)
    total_completion = sum(u["completion_tokens"] or 0 for u in usage)
    est_cost_usd = total_prompt * _PRICE_IN_PER_M / 1e6 + total_completion * _PRICE_OUT_PER_M / 1e6
    users = db.list_users()
    return {
        "usage_by_kind": usage,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "estimated_cost_usd": round(est_cost_usd, 4),
        "user_count": len(users),
        "total_attempts": sum(u["attempt_count"] for u in users),
        "tutor_agent": db.get_tutor_agent_stats(),
    }

@app.get("/admin/users")
def admin_users():
    return {"users": db.list_users()}

@app.get("/admin/llm-logs")
def admin_llm_logs(user_id: Optional[str] = None, limit: int = 100):
    return {"logs": db.get_llm_logs(user_id, limit)}

@app.get("/admin/exam-sessions")
def admin_exam_sessions(user_id: Optional[str] = None, grade: Optional[str] = None):
    return {"sessions": db.get_exam_sessions(user_id, grade)}

@app.get("/admin/personas")
def admin_personas():
    personas = db.list_personas()
    for p in personas:
        p["exam_sessions"] = db.get_exam_sessions(p["user_id"])
    return {"personas": personas}

@app.post("/admin/persona/run")
def admin_persona_run(req: PersonaRunReq):
    result = run_persona(
        qb, exam_gen,
        name=req.name,
        ability=max(0.02, min(0.98, req.ability)),
        grade=req.grade,
        learning_count=max(1, min(100, req.learning_count)),
        topic_name=req.topic_name,
        mode=req.mode if req.mode in ("simulated", "llm") else "simulated",
    )
    return result
