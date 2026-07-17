import json
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / 'data' / 'sudal.db'

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    grade TEXT NOT NULL,
    topic_key TEXT NOT NULL,
    sector1 TEXT,
    sector2 TEXT,
    difficulty INTEGER,
    is_correct INTEGER NOT NULL,
    hint_used INTEGER NOT NULL DEFAULT 0,
    mastery_before REAL,
    mastery_after REAL,
    answered_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_attempts_user_correct ON attempts(user_id, is_correct);
CREATE INDEX IF NOT EXISTS idx_attempts_user_topic ON attempts(user_id, topic_key);

CREATE TABLE IF NOT EXISTS topic_mastery (
    user_id TEXT NOT NULL,
    grade TEXT NOT NULL,
    topic_key TEXT NOT NULL,
    sector1 TEXT,
    sector2 TEXT,
    mastery REAL NOT NULL DEFAULT 0.5,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    last_reviewed_at REAL,
    next_review_at REAL,
    PRIMARY KEY (user_id, grade, topic_key)
);

CREATE TABLE IF NOT EXISTS llm_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    kind TEXT NOT NULL,
    question_id TEXT,
    prompt TEXT,
    response TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    model TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_logs_user ON llm_logs(user_id);

CREATE TABLE IF NOT EXISTS exam_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    grade TEXT NOT NULL,
    score REAL NOT NULL,
    total_questions INTEGER NOT NULL,
    correct_count INTEGER NOT NULL,
    topic_breakdown TEXT,
    taken_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exam_sessions_user ON exam_sessions(user_id);

CREATE TABLE IF NOT EXISTS personas (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ability REAL NOT NULL,
    learning_questions INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def topic_key_for(question: dict) -> str:
    """토픽 식별 키: topic_name이 있으면 그걸, 없으면 sector2로 대체."""
    return question.get('topic_name') or question.get('sector2') or question.get('sector1') or 'unknown'


def get_topic_mastery(user_id: str, grade: str, topic_key: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM topic_mastery WHERE user_id=? AND grade=? AND topic_key=?",
            (user_id, grade, topic_key)
        ).fetchone()


def _next_review_delay(mastery: float) -> float:
    """마스터리 수준에 따른 다음 복습까지의 간격(초). 간이 SM-2 방식."""
    day = 86400
    if mastery >= 0.85:
        return 5 * day
    if mastery >= 0.65:
        return 2 * day
    if mastery >= 0.4:
        return 1 * day
    return 0  # 즉시 재복습 대상


def record_attempt(
    user_id: str,
    question: dict,
    grade: str,
    is_correct: bool,
    hint_used: bool = False,
    mastery_before: float | None = None,
    mastery_after: float | None = None,
    alpha: float = 0.3,
):
    """정오답 기록 + 토픽별 mastery/연속기록/복습 스케줄을 함께 갱신한다.

    streak는 부호 있는 값으로 관리한다: 양수는 연속 정답 횟수, 음수는 연속 오답
    횟수. 방향이 바뀌면 즉시 ±1로 리셋된다. next_difficulty()의 가속 판단에 쓰인다.
    """
    topic_key = topic_key_for(question)
    now = time.time()

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO attempts
               (user_id, question_id, grade, topic_key, sector1, sector2, difficulty,
                is_correct, hint_used, mastery_before, mastery_after, answered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, question.get('id'), grade, topic_key,
             question.get('sector1'), question.get('sector2'), question.get('difficulty'),
             int(is_correct), int(hint_used), mastery_before, mastery_after, now)
        )

        row = conn.execute(
            "SELECT * FROM topic_mastery WHERE user_id=? AND grade=? AND topic_key=?",
            (user_id, grade, topic_key)
        ).fetchone()

        prev_streak = row['streak'] if row is not None else 0
        prev_mastery = row['mastery'] if row is not None else 0.5
        if is_correct:
            new_streak = prev_streak + 1 if prev_streak >= 0 else 1
        else:
            new_streak = prev_streak - 1 if prev_streak <= 0 else -1
        new_mastery = (1 - alpha) * prev_mastery + alpha * (1.0 if is_correct else 0.0)
        next_review_at = now + _next_review_delay(new_mastery)

        if row is None:
            conn.execute(
                """INSERT INTO topic_mastery
                   (user_id, grade, topic_key, sector1, sector2, mastery, attempt_count,
                    correct_count, streak, last_reviewed_at, next_review_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
                (user_id, grade, topic_key, question.get('sector1'), question.get('sector2'),
                 new_mastery, int(is_correct), new_streak, now, next_review_at)
            )
            attempt_count, correct_count = 1, int(is_correct)
        else:
            conn.execute(
                """UPDATE topic_mastery SET
                   mastery=?, attempt_count=attempt_count+1, correct_count=correct_count+?,
                   streak=?, last_reviewed_at=?, next_review_at=?
                   WHERE user_id=? AND grade=? AND topic_key=?""",
                (new_mastery, int(is_correct), new_streak, now, next_review_at,
                 user_id, grade, topic_key)
            )
            attempt_count, correct_count = row['attempt_count'] + 1, row['correct_count'] + int(is_correct)

    return {
        'topic_key': topic_key,
        'prev_streak': prev_streak,
        'streak': new_streak,
        'mastery': new_mastery,
        'attempt_count': attempt_count,
        'correct_count': correct_count,
    }


def get_topic_report(user_id: str, grade: str | None = None):
    query = "SELECT * FROM topic_mastery WHERE user_id=?"
    params = [user_id]
    if grade:
        query += " AND grade=?"
        params.append(grade)
    query += " ORDER BY mastery ASC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_due_topics(user_id: str, grade: str | None = None, limit: int = 5):
    """복습 시점이 지난(next_review_at <= now) 토픽을 mastery 낮은 순으로 반환."""
    now = time.time()
    query = "SELECT * FROM topic_mastery WHERE user_id=? AND next_review_at IS NOT NULL AND next_review_at <= ?"
    params = [user_id, now]
    if grade:
        query += " AND grade=?"
        params.append(grade)
    query += " ORDER BY mastery ASC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def log_llm(user_id, kind, question_id=None, prompt=None, response=None,
            prompt_tokens=0, completion_tokens=0, model=None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO llm_logs
               (user_id, kind, question_id, prompt, response, prompt_tokens, completion_tokens, model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, kind, question_id, prompt, response,
             prompt_tokens or 0, completion_tokens or 0, model, time.time())
        )


def get_llm_logs(user_id: str | None = None, limit: int = 100):
    query = "SELECT * FROM llm_logs"
    params: list = []
    if user_id:
        query += " WHERE user_id=?"
        params.append(user_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_llm_usage_summary():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT kind, model, COUNT(*) as calls,
                      SUM(prompt_tokens) as prompt_tokens,
                      SUM(completion_tokens) as completion_tokens
               FROM llm_logs GROUP BY kind, model"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_tutor_agent_stats():
    """튜터 에이전트가 실제로 몇 번 돌았고, 그중 개념 전환을 몇 번 추천했는지.
    관리자 개요 화면에서 '적응형 로직에 에이전트가 정말 관여하는지'를 숫자로 바로 보여준다.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT response FROM llm_logs WHERE kind='tutor_agent'"
        ).fetchall()
    total = len(rows)
    switches = 0
    for r in rows:
        try:
            parsed = json.loads(r['response'] or '{}')
            if parsed.get('next_topic'):
                switches += 1
        except (TypeError, ValueError):
            pass
    return {"total_calls": total, "topic_switches": switches}


def record_exam_session(user_id: str, grade: str, score: float,
                        total_questions: int, correct_count: int, topic_breakdown: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO exam_sessions
               (user_id, grade, score, total_questions, correct_count, topic_breakdown, taken_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, grade, score, total_questions, correct_count,
             json.dumps(topic_breakdown, ensure_ascii=False), time.time())
        )


def get_exam_sessions(user_id: str | None = None, grade: str | None = None, limit: int = 100):
    """grade를 안 주면 그 사용자의 모든 학년 시험이 taken_at 순서로 한 줄로 이어져
    나오므로 주의. 관리자 페이지의 "점수 추이"처럼 학년 간 점수를 비교하면 안 되는
    곳에서는 반드시 grade를 넘겨서 같은 학년끼리만 비교해야 한다.
    """
    query = "SELECT * FROM exam_sessions"
    conditions = []
    params: list = []
    if user_id:
        conditions.append("user_id=?")
        params.append(user_id)
    if grade:
        conditions.append("grade=?")
        params.append(grade)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY taken_at ASC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    for r in rows:
        try:
            r['topic_breakdown'] = json.loads(r['topic_breakdown'] or '{}')
        except (TypeError, ValueError):
            r['topic_breakdown'] = {}
    return rows[-limit:]


def list_users():
    """시도 기록이 있는 (사용자, 학년) 조합별 요약.

    같은 닉네임이라도 학년을 바꿔가며 공부하면 topic_mastery가 학년별로 완전히
    분리되어 쌓이므로(PRIMARY KEY에 grade 포함), 여기서도 grade까지 묶어야
    "이 학생이 이 학년에서 얼마나 하는지"가 뭉개지지 않는다.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT a.user_id, a.grade,
                      COUNT(*) as attempt_count,
                      SUM(a.is_correct) as correct_count,
                      MAX(a.answered_at) as last_active,
                      (SELECT AVG(mastery) FROM topic_mastery t
                       WHERE t.user_id = a.user_id AND t.grade = a.grade) as avg_mastery,
                      (SELECT name FROM personas p WHERE p.user_id = a.user_id) as persona_name
               FROM attempts a GROUP BY a.user_id, a.grade ORDER BY last_active DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def create_persona(user_id: str, name: str, ability: float, learning_questions: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO personas (user_id, name, ability, learning_questions, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, ability, learning_questions, time.time())
        )


def list_personas():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM personas ORDER BY created_at DESC").fetchall()]


def get_recent_attempts(user_id: str, grade: str, limit: int = 5):
    """튜터 에이전트가 최근 풀이 패턴을 참고할 수 있도록 최신순으로 반환."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT topic_key, sector1, sector2, difficulty, is_correct, hint_used, answered_at
               FROM attempts WHERE user_id=? AND grade=?
               ORDER BY answered_at DESC LIMIT ?""",
            (user_id, grade, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def get_wrong_question_ids(user_id: str, grade: str | None = None, limit: int = 50):
    """가장 최근 오답부터, question_id별 최신 정오답 상태만 반영해 아직도 틀리는 문제만 추린다."""
    query = """
        SELECT question_id, topic_key, grade, MAX(answered_at) as last_at
        FROM attempts
        WHERE user_id=? AND is_correct=0
    """
    params = [user_id]
    if grade:
        query += " AND grade=?"
        params.append(grade)
    query += " GROUP BY question_id ORDER BY last_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
