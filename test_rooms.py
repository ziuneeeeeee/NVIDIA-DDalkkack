"""
core/rooms.py 테스트. 실제 파일시스템에 임시 디렉터리를 사용하고
(LLM/네트워크 호출 없음) 끝나면 정리한다.
"""

import json

import pytest

import core.rooms as rooms


@pytest.fixture(autouse=True)
def _isolated_rooms_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(rooms, "ROOMS_DIR", str(tmp_path / "rooms"))


def test_create_room_generates_id_and_defaults():
    room = rooms.create_room("알고리즘 중간고사")
    assert room["name"] == "알고리즘 중간고사"
    assert room["room_id"]
    assert room["uploads"] == []
    assert room["concept_bank"] == []
    assert room["mapped_concepts"] == []


def test_create_room_falls_back_to_default_name_when_blank():
    room = rooms.create_room("   ")
    assert room["name"] == "이름 없는 방"


def test_get_room_roundtrips_created_room():
    created = rooms.create_room("자료구조")
    fetched = rooms.get_room(created["room_id"])
    assert fetched["room_id"] == created["room_id"]
    assert fetched["name"] == "자료구조"


def test_get_room_raises_for_unknown_id():
    with pytest.raises(rooms.RoomNotFoundError):
        rooms.get_room("no-such-room")


def test_rename_room_updates_name():
    room = rooms.create_room("원래 이름")
    renamed = rooms.rename_room(room["room_id"], "바뀐 이름")
    assert renamed["name"] == "바뀐 이름"
    assert rooms.get_room(room["room_id"])["name"] == "바뀐 이름"


def test_rename_room_ignores_blank_name():
    room = rooms.create_room("유지되는 이름")
    renamed = rooms.rename_room(room["room_id"], "   ")
    assert renamed["name"] == "유지되는 이름"


def test_list_rooms_returns_summaries_sorted_by_recent_update():
    a = rooms.create_room("A방")
    b = rooms.create_room("B방")
    rooms.rename_room(a["room_id"], "A방-수정됨")  # a를 더 최근으로 만듦

    listed = rooms.list_rooms()
    assert [r["room_id"] for r in listed] == [a["room_id"], b["room_id"]]


def test_merge_concepts_dedupes_by_case_insensitive_name():
    room = rooms.create_room("병합 테스트")
    first = rooms.merge_concepts(room["room_id"], [
        {"concept_id": "x", "concept_name": "Heap"},
        {"concept_id": "y", "concept_name": "Binary Tree"},
    ])
    assert [c["concept_name"] for c in first] == ["Heap", "Binary Tree"]

    second = rooms.merge_concepts(room["room_id"], [
        {"concept_id": "z", "concept_name": "heap"},   # Heap과 대소문자만 다름 -> 중복
        {"concept_id": "w", "concept_name": "Sorting"},
    ])
    assert [c["concept_name"] for c in second] == ["Heap", "Binary Tree", "Sorting"]


def test_merge_concepts_assigns_sequential_ids_ignoring_input_ids():
    room = rooms.create_room("ID 테스트")
    merged = rooms.merge_concepts(room["room_id"], [
        {"concept_id": "whatever", "concept_name": "A"},
        {"concept_id": "whatever2", "concept_name": "B"},
    ])
    assert [c["concept_id"] for c in merged] == ["concept_0000", "concept_0001"]


def test_set_mapped_concepts_persists():
    room = rooms.create_room("매핑 테스트")
    mapped = [{"concept_id": "concept_0000", "concept_name": "A", "mapped_category": "DESCRIPTIVE"}]
    rooms.set_mapped_concepts(room["room_id"], mapped)
    assert rooms.get_room(room["room_id"])["mapped_concepts"] == mapped


def test_record_upload_appends_to_uploads_list():
    room = rooms.create_room("업로드 기록 테스트")
    rooms.record_upload(room["room_id"], {"filename": "a.pdf"})
    rooms.record_upload(room["room_id"], {"filename": "b.pdf"})
    uploads = rooms.get_room(room["room_id"])["uploads"]
    assert [u["filename"] for u in uploads] == ["a.pdf", "b.pdf"]


def test_create_room_starts_with_empty_attempts():
    room = rooms.create_room("오답노트 테스트")
    assert room["attempts"] == []


def test_load_room_missing_attempts_field_defaults_to_empty_list(tmp_path):
    # attempts 필드가 생기기 전에 저장된 room.json을 흉내낸다 (하위호환 확인)
    room = rooms.create_room("옛날 방")
    path = rooms._room_json_path(room["room_id"])
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    del data["attempts"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    loaded = rooms.get_room(room["room_id"])
    assert loaded["attempts"] == []


def test_record_attempt_appends_and_list_attempts_returns_newest_first():
    room = rooms.create_room("오답노트 순서 테스트")
    rooms.record_attempt(room["room_id"], {"attempt_id": "a1", "mode": "simple"})
    rooms.record_attempt(room["room_id"], {"attempt_id": "a2", "mode": "mock"})

    attempts = rooms.list_attempts(room["room_id"])
    assert [a["attempt_id"] for a in attempts] == ["a2", "a1"]
