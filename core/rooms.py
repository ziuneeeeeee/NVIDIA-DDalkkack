"""
rooms.py
─────────
"방(Room)" — 이름을 붙여 만드는 학습 세션 단위. 방마다 독립된 RAG 인덱스
(ChromaDB + BM25)와 병합된 핵심개념 목록을 로컬 파일로 저장한다.

레이아웃:
  rooms/<room_id>/room.json      # 메타데이터 + 병합된 concept_bank/mapped_concepts
  rooms/<room_id>/chroma_db/     # 그 방 전용 벡터 인덱스
  rooms/<room_id>/bm25_index.pkl # 그 방 전용 키워드 인덱스

흐름: 방 생성 → 자료 업로드(여러 개 가능, 개념은 이름 기준으로 병합·중복
제거) → 병합된 개념을 팀원2 로직(type_mapping)으로 매핑 → 이 방의
mapped_concepts를 '단순 개념 확인'/'모의고사' 문제 생성의 입력으로 사용.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

ROOMS_DIR = "rooms"


class RoomNotFoundError(Exception):
    pass


def _room_dir(room_id: str) -> str:
    return os.path.join(ROOMS_DIR, room_id)


def _room_json_path(room_id: str) -> str:
    return os.path.join(_room_dir(room_id), "room.json")


def room_chroma_path(room_id: str) -> str:
    return os.path.join(_room_dir(room_id), "chroma_db")


def room_bm25_path(room_id: str) -> str:
    return os.path.join(_room_dir(room_id), "bm25_index.pkl")


def _load(room_id: str) -> dict:
    path = _room_json_path(room_id)
    if not os.path.exists(path):
        raise RoomNotFoundError(f"방을 찾을 수 없습니다: {room_id}")
    with open(path, encoding="utf-8") as f:
        room = json.load(f)
    room.setdefault("attempts", [])  # 이 필드가 생기기 전에 만들어진 방과의 하위호환
    return room


def _save(room: dict) -> None:
    os.makedirs(_room_dir(room["room_id"]), exist_ok=True)
    with open(_room_json_path(room["room_id"]), "w", encoding="utf-8") as f:
        json.dump(room, f, ensure_ascii=False, indent=2)


def create_room(name: str) -> dict:
    room_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    room = {
        "room_id": room_id,
        "name": name.strip() or "이름 없는 방",
        "created_at": now,
        "updated_at": now,
        "uploads": [],          # [{filename, source_type, page_count, chunk_count, concept_count, uploaded_at}]
        "concept_bank": [],     # 병합·중복제거된 원본 개념 (nodes/concept_extraction.py 스키마)
        "mapped_concepts": [],  # concept_bank + mapped_category 등 (nodes/type_mapping.py 산출)
        "attempts": [],         # 오답노트: 채점 완료된 시도 이력 (record_attempt로 추가)
    }
    _save(room)
    return room


def list_rooms() -> list[dict]:
    if not os.path.isdir(ROOMS_DIR):
        return []
    summaries = []
    for room_id in sorted(os.listdir(ROOMS_DIR)):
        json_path = _room_json_path(room_id)
        if not os.path.exists(json_path):
            continue
        room = _load(room_id)
        summaries.append({
            "room_id": room["room_id"],
            "name": room["name"],
            "created_at": room["created_at"],
            "updated_at": room["updated_at"],
            "upload_count": len(room["uploads"]),
            "concept_count": len(room["mapped_concepts"]),
        })
    summaries.sort(key=lambda r: r["updated_at"], reverse=True)
    return summaries


def get_room(room_id: str) -> dict:
    return _load(room_id)


def rename_room(room_id: str, new_name: str) -> dict:
    room = _load(room_id)
    room["name"] = new_name.strip() or room["name"]
    room["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(room)
    return room


def _dedup_key(concept_name: str) -> str:
    return concept_name.casefold().strip()


def merge_concepts(room_id: str, new_concepts: list[dict]) -> list[dict]:
    """새로 추출된 개념을 방의 기존 concept_bank에 이름 기준으로 병합한다
    (이미 있는 이름은 건너뜀 — 같은 개념이 다른 자료에 또 나와도 중복 저장 안 함).
    반환값: 병합 후 전체 concept_bank."""
    room = _load(room_id)
    existing_keys = {_dedup_key(c["concept_name"]) for c in room["concept_bank"]}

    next_index = len(room["concept_bank"])
    for c in new_concepts:
        key = _dedup_key(c["concept_name"])
        if key in existing_keys:
            continue
        c = dict(c)
        c["concept_id"] = f"concept_{next_index:04d}"
        room["concept_bank"].append(c)
        existing_keys.add(key)
        next_index += 1

    room["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(room)
    return room["concept_bank"]


def set_mapped_concepts(room_id: str, mapped_concepts: list[dict]) -> dict:
    room = _load(room_id)
    room["mapped_concepts"] = mapped_concepts
    room["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(room)
    return room


def record_upload(room_id: str, upload_summary: dict) -> dict:
    room = _load(room_id)
    room["uploads"].append(upload_summary)
    room["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(room)
    return room


def record_attempt(room_id: str, attempt: dict) -> dict:
    """채점이 끝난 시도(단순확인/모의고사)를 오답노트용으로 저장한다.
    attempt는 problems/student_answers/grade_result를 포함해, 나중에
    문제·내 답안·채점 근거를 그대로 다시 볼 수 있게 한다."""
    room = _load(room_id)
    room["attempts"].append(attempt)
    room["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(room)
    return room


def list_attempts(room_id: str) -> list[dict]:
    room = _load(room_id)
    return list(reversed(room["attempts"]))  # 최신 시도가 먼저 오도록
