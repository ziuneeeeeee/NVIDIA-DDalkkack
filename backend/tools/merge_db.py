"""여러 팀원의 sudal.db를 하나로 합치는 스크립트.

사용법:
    python tools/merge_db.py 대상.db 팀원A.db 팀원B.db ...

대상.db가 없으면 새로 만들어지고, 있으면 그 위에 병합된다.

병합 규칙:
- attempts: id(AUTOINCREMENT)는 버리고 나머지 컬럼만 이어 붙인다.
  (user_id, question_id, answered_at)가 완전히 같은 행은 중복으로 보고 건너뛴다.
- topic_mastery: (user_id, grade, topic_key)가 겹치면 last_reviewed_at이
  더 최신인 쪽을 남긴다. 팀원마다 user_id(브라우저별 UUID)가 달라서
  실제로 겹치는 일은 거의 없다.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.db import SCHEMA  # noqa: E402

ATTEMPT_COLS = (
    "user_id, question_id, grade, topic_key, sector1, sector2, difficulty, "
    "is_correct, hint_used, mastery_before, mastery_after, answered_at"
)


def merge(target_path: str, source_paths: list[str]):
    target = sqlite3.connect(target_path)
    target.executescript(SCHEMA)

    for src_path in source_paths:
        if not Path(src_path).exists():
            print(f"[skip] {src_path}: 파일이 없습니다")
            continue

        src = sqlite3.connect(src_path)
        src.row_factory = sqlite3.Row

        added_attempts = 0
        for row in src.execute(f"SELECT {ATTEMPT_COLS} FROM attempts"):
            dup = target.execute(
                "SELECT 1 FROM attempts WHERE user_id=? AND question_id=? AND answered_at=?",
                (row["user_id"], row["question_id"], row["answered_at"]),
            ).fetchone()
            if dup:
                continue
            target.execute(
                f"INSERT INTO attempts ({ATTEMPT_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(row),
            )
            added_attempts += 1

        added_topics = 0
        for row in src.execute("SELECT * FROM topic_mastery"):
            existing = target.execute(
                "SELECT last_reviewed_at FROM topic_mastery WHERE user_id=? AND grade=? AND topic_key=?",
                (row["user_id"], row["grade"], row["topic_key"]),
            ).fetchone()
            if existing and (existing[0] or 0) >= (row["last_reviewed_at"] or 0):
                continue
            target.execute(
                """INSERT OR REPLACE INTO topic_mastery
                   (user_id, grade, topic_key, sector1, sector2, mastery, attempt_count,
                    correct_count, streak, last_reviewed_at, next_review_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (row["user_id"], row["grade"], row["topic_key"], row["sector1"],
                 row["sector2"], row["mastery"], row["attempt_count"],
                 row["correct_count"], row["streak"], row["last_reviewed_at"],
                 row["next_review_at"]),
            )
            added_topics += 1

        src.close()
        print(f"[ok] {src_path}: attempts +{added_attempts}, topic_mastery +{added_topics}")

    target.commit()
    total_a = target.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    total_t = target.execute("SELECT COUNT(*) FROM topic_mastery").fetchone()[0]
    target.close()
    print(f"[done] {target_path}: attempts {total_a}건, topic_mastery {total_t}건")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    merge(sys.argv[1], sys.argv[2:])
