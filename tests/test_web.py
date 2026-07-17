import json

import pytest
from fastapi.testclient import TestClient

from teach_me.web import create_app

BANK = [
    {
        "id": 1,
        "question": "Which planet is known as the Red Planet?",
        "options": ["Venus", "Mars", "Jupiter", "Saturn"],
        "correct": [1],
        "explanation": "Iron oxide.",
        "topics": ["Astronomy"],
        "set": "Exam A",
    },
    {
        "id": 2,
        "question": "Which two are noble gases?",
        "options": ["Helium", "Nitrogen", "Neon", "Oxygen"],
        "correct": [0, 2],
        "topics": ["Chemistry"],
        "set": "Exam B",
    },
    {
        "id": 3,
        "question": "2 + 2?",
        "options": ["3", "4"],
        "correct": [1],
        "topics": ["Mathematics"],
        "set": "Exam A",
    },
]


@pytest.fixture()
def client(tmp_path):
    (tmp_path / "bank.json").write_text(json.dumps(BANK))
    cfg = tmp_path / "teach-me.toml"
    cfg.write_text(
        f'subject = "Test Subject"\nbank = "bank.json"\ndata_dir = "{tmp_path / "data"}"\n'
    )
    return TestClient(create_app(cfg))


def test_state(client):
    data = client.get("/api/state").json()
    assert data["subject"] == "Test Subject"
    assert data["question_count"] == 3
    assert data["sets"] == ["Exam A", "Exam B"]
    assert data["tutor_on"] is False
    assert {"name": "Chemistry", "questions": 1} in data["topics"]


def test_state_set_filter(client):
    data = client.get("/api/state", params={"set": "Exam A"}).json()
    assert data["question_count"] == 2
    assert all(t["name"] != "Chemistry" for t in data["topics"])


def test_quiz_hides_answers(client):
    data = client.post("/api/quiz", json={"mode": "all"}).json()
    assert len(data["questions"]) == 3
    for q in data["questions"]:
        assert "correct" not in q
        assert "explanation" not in q
    multi = next(q for q in data["questions"] if q["id"] == 2)
    assert multi["select_n"] == 2
    single = next(q for q in data["questions"] if q["id"] == 1)
    assert single["select_n"] is None


def test_quiz_topic_and_set(client):
    data = client.post("/api/quiz", json={"mode": "topic", "topic": "Chemistry"}).json()
    assert [q["id"] for q in data["questions"]] == [2]
    data = client.post("/api/quiz", json={"mode": "all", "set": "Exam A"}).json()
    assert sorted(q["id"] for q in data["questions"]) == [1, 3]


def test_quiz_missed_empty_before_any_answers(client):
    data = client.post("/api/quiz", json={"mode": "missed"}).json()
    assert data["questions"] == []


def test_answer_grades_and_records(client, tmp_path):
    res = client.post("/api/answer", json={"id": 1, "answer": "b"}).json()
    assert res["correct"] is True
    assert res["correct_letters"] == ["B"]
    assert res["explanation"] == "Iron oxide."

    res = client.post("/api/answer", json={"id": 2, "answer": "AB"}).json()
    assert res["correct"] is False
    assert res["correct_letters"] == ["A", "C"]

    saved = json.loads((tmp_path / "data" / "progress.json").read_text())
    assert saved["questions"]["1"]["correct"] == 1
    assert saved["questions"]["2"]["attempts"] == 1

    # and the missed review now surfaces the wrong answer
    data = client.post("/api/quiz", json={"mode": "missed"}).json()
    assert [q["id"] for q in data["questions"]] == [2]


def test_answer_validation(client):
    assert client.post("/api/answer", json={"id": 99, "answer": "a"}).status_code == 404
    res = client.post("/api/answer", json={"id": 3, "answer": "z"})
    assert res.status_code == 400
    assert res.json()["error"] == "answers must be letters A-B"
    res = client.post("/api/answer", json={"id": 3, "answer": "1"})
    assert res.status_code == 400


def test_session_recording(client, tmp_path):
    res = client.post("/api/session", json={"asked": 5, "correct": 3}).json()
    assert res["recorded"] is True
    saved = json.loads((tmp_path / "data" / "progress.json").read_text())
    assert saved["sessions"][0]["asked"] == 5

    res = client.post("/api/session", json={"asked": 0, "correct": 0}).json()
    assert res["recorded"] is False


def test_dashboard(client):
    client.post("/api/answer", json={"id": 1, "answer": "b"})
    client.post("/api/answer", json={"id": 3, "answer": "a"})
    d = client.get("/api/dashboard").json()
    assert d["coverage"] == {"seen": 2, "total": 3, "mastered": 0}
    assert d["overall"] == 0.5
    astro = next(t for t in d["topics"] if t["topic"] == "Astronomy")
    assert astro["accuracy"] == 1.0
    assert astro["seen"] == 1
    # attempted topics come before untouched ones, weakest first
    assert d["topics"][0]["topic"] == "Mathematics"


def test_tutor_unconfigured(client):
    res = client.post("/api/tutor", json={"message": "hi"})
    assert res.status_code == 503


@pytest.fixture()
def chapter_client(tmp_path):
    (tmp_path / "bank.json").write_text(json.dumps(BANK))
    (tmp_path / "mini.json").write_text(json.dumps([
        {"id": 1, "question": "1 + 1?", "options": ["1", "2"], "correct": [1],
         "topics": ["Arithmetic"]},
    ]))
    cfg = tmp_path / "teach-me.toml"
    cfg.write_text(
        f'data_dir = "{tmp_path / "data"}"\n'
        '[[chapter]]\nsubject = "Big Exam"\nbank = "bank.json"\n'
        '[[chapter]]\nsubject = "Mini Exam"\nbank = "mini.json"\n'
    )
    return TestClient(create_app(cfg))


def test_chapters_listing(chapter_client):
    data = chapter_client.get("/api/chapters").json()
    assert data["chapters"] == [
        {"slug": "big-exam", "subject": "Big Exam", "question_count": 3},
        {"slug": "mini-exam", "subject": "Mini Exam", "question_count": 1},
    ]


def test_chapter_scoping(chapter_client, tmp_path):
    state = chapter_client.get("/api/state", params={"chapter": "mini-exam"}).json()
    assert state["subject"] == "Mini Exam"
    assert state["question_count"] == 1

    # same question id in both chapters grades against the right bank
    res = chapter_client.post("/api/answer",
                              json={"id": 1, "answer": "b", "chapter": "mini-exam"}).json()
    assert res["correct"] is True

    # and progress lands in the chapter's own file
    saved = json.loads((tmp_path / "data" / "progress-mini-exam.json").read_text())
    assert saved["questions"]["1"]["correct"] == 1
    assert not (tmp_path / "data" / "progress-big-exam.json").exists()

    d = chapter_client.get("/api/dashboard", params={"chapter": "big-exam"}).json()
    assert d["coverage"] == {"seen": 0, "total": 3, "mastered": 0}


def test_unknown_chapter_is_404(chapter_client):
    assert chapter_client.get("/api/state", params={"chapter": "nope"}).status_code == 404
    assert chapter_client.post("/api/quiz", json={"mode": "all", "chapter": "nope"}).status_code == 404


def test_omitted_chapter_defaults_to_first(chapter_client):
    state = chapter_client.get("/api/state").json()
    assert state["subject"] == "Big Exam"


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "teach-me" in res.text
