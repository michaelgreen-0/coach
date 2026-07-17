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


def _signed_in_client(cfg, username="tester"):
    client = TestClient(create_app(cfg))
    res = client.post("/api/register",
                      json={"username": username, "password": "password123"})
    assert res.status_code == 200
    return client


@pytest.fixture()
def client(tmp_path):
    (tmp_path / "bank.json").write_text(json.dumps(BANK))
    cfg = tmp_path / "teach-me.toml"
    cfg.write_text(
        f'subject = "Test Subject"\nbank = "bank.json"\ndata_dir = "{tmp_path / "data"}"\n'
    )
    return _signed_in_client(cfg)


def test_state(client):
    data = client.get("/api/state").json()
    assert data["name"] == "Test Subject"
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

    saved = json.loads(
        (tmp_path / "data" / "progress" / "tester" / "progress.json").read_text())
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
    saved = json.loads(
        (tmp_path / "data" / "progress" / "tester" / "progress.json").read_text())
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
def subject_client(tmp_path):
    (tmp_path / "bank.json").write_text(json.dumps(BANK))
    (tmp_path / "mini.json").write_text(json.dumps([
        {"id": 1, "question": "1 + 1?", "options": ["1", "2"], "correct": [1],
         "topics": ["Arithmetic"]},
    ]))
    cfg = tmp_path / "teach-me.toml"
    cfg.write_text(
        f'data_dir = "{tmp_path / "data"}"\n'
        '[[subject]]\nname = "Big Exam"\nbank = "bank.json"\n'
        '[[subject]]\nname = "Mini Exam"\nbank = "mini.json"\n'
    )
    return _signed_in_client(cfg)


def test_subjects_listing(subject_client):
    data = subject_client.get("/api/subjects").json()
    assert data["subjects"] == [
        {"slug": "big-exam", "name": "Big Exam", "question_count": 3},
        {"slug": "mini-exam", "name": "Mini Exam", "question_count": 1},
    ]


def test_subject_scoping(subject_client, tmp_path):
    state = subject_client.get("/api/state", params={"subject": "mini-exam"}).json()
    assert state["name"] == "Mini Exam"
    assert state["question_count"] == 1

    # same question id in both subjects grades against the right bank
    res = subject_client.post("/api/answer",
                              json={"id": 1, "answer": "b", "subject": "mini-exam"}).json()
    assert res["correct"] is True

    # and progress lands in the subject's own file, under the user's directory
    saved = json.loads((tmp_path / "data" / "progress" / "tester"
                        / "progress-mini-exam.json").read_text())
    assert saved["questions"]["1"]["correct"] == 1
    assert not (tmp_path / "data" / "progress" / "tester"
                / "progress-big-exam.json").exists()

    d = subject_client.get("/api/dashboard", params={"subject": "big-exam"}).json()
    assert d["coverage"] == {"seen": 0, "total": 3, "mastered": 0}


def test_unknown_subject_is_404(subject_client):
    assert subject_client.get("/api/state", params={"subject": "nope"}).status_code == 404
    assert subject_client.post("/api/quiz", json={"mode": "all", "subject": "nope"}).status_code == 404


def test_omitted_subject_defaults_to_first(subject_client):
    state = subject_client.get("/api/state").json()
    assert state["name"] == "Big Exam"


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "teach-me" in res.text


@pytest.fixture()
def anon_client(tmp_path):
    (tmp_path / "bank.json").write_text(json.dumps(BANK))
    cfg = tmp_path / "teach-me.toml"
    cfg.write_text(
        f'subject = "Test Subject"\nbank = "bank.json"\ndata_dir = "{tmp_path / "data"}"\n'
    )
    return TestClient(create_app(cfg))


def test_endpoints_require_auth(anon_client):
    for res in (
        anon_client.get("/api/subjects"),
        anon_client.get("/api/state"),
        anon_client.post("/api/quiz", json={"mode": "all"}),
        anon_client.post("/api/answer", json={"id": 1, "answer": "a"}),
        anon_client.get("/api/dashboard"),
        anon_client.post("/api/tutor", json={"message": "hi"}),
    ):
        assert res.status_code == 401
        assert res.json() == {"error": "not signed in"}
    # the page itself and auth status stay public
    assert anon_client.get("/").status_code == 200
    status = anon_client.get("/api/auth").json()
    assert status == {"signed_in": False, "username": None, "invite_required": False}


def test_register_validation(anon_client):
    bad = anon_client.post("/api/register",
                           json={"username": "Bad Name!", "password": "password123"})
    assert bad.status_code == 400
    short = anon_client.post("/api/register",
                             json={"username": "goodname", "password": "short"})
    assert short.status_code == 400

    ok = anon_client.post("/api/register",
                          json={"username": "goodname", "password": "password123"})
    assert ok.status_code == 200
    dupe = anon_client.post("/api/register",
                            json={"username": "goodname", "password": "password456"})
    assert dupe.status_code == 400
    assert "taken" in dupe.json()["error"]


def test_login_and_logout(anon_client):
    anon_client.post("/api/register",
                     json={"username": "friend", "password": "password123"})
    anon_client.post("/api/logout", json={})
    assert anon_client.get("/api/state").status_code == 401

    wrong = anon_client.post("/api/login",
                             json={"username": "friend", "password": "wrongwrong"})
    assert wrong.status_code == 401

    ok = anon_client.post("/api/login",
                          json={"username": "friend", "password": "password123"})
    assert ok.status_code == 200
    assert anon_client.get("/api/state").status_code == 200
    assert anon_client.get("/api/auth").json()["username"] == "friend"


def test_progress_is_per_user(tmp_path):
    (tmp_path / "bank.json").write_text(json.dumps(BANK))
    cfg = tmp_path / "teach-me.toml"
    cfg.write_text(
        f'subject = "Test Subject"\nbank = "bank.json"\ndata_dir = "{tmp_path / "data"}"\n'
    )
    alice = _signed_in_client(cfg, "alice")
    bob = _signed_in_client(cfg, "bob")

    res = alice.post("/api/answer", json={"id": 1, "answer": "b"}).json()
    assert res["correct"] is True

    assert alice.get("/api/dashboard").json()["coverage"]["seen"] == 1
    assert bob.get("/api/dashboard").json()["coverage"]["seen"] == 0
    assert (tmp_path / "data" / "progress" / "alice" / "progress.json").exists()
    assert not (tmp_path / "data" / "progress" / "bob").exists()


def test_invite_code(tmp_path, monkeypatch):
    (tmp_path / "bank.json").write_text(json.dumps(BANK))
    cfg = tmp_path / "teach-me.toml"
    cfg.write_text(
        f'subject = "Test Subject"\nbank = "bank.json"\ndata_dir = "{tmp_path / "data"}"\n'
    )
    monkeypatch.setenv("TEACH_ME_INVITE_CODE", "sesame")
    client = TestClient(create_app(cfg))

    assert client.get("/api/auth").json()["invite_required"] is True
    refused = client.post("/api/register",
                          json={"username": "friend", "password": "password123"})
    assert refused.status_code == 403
    ok = client.post("/api/register",
                     json={"username": "friend", "password": "password123",
                           "invite": "sesame"})
    assert ok.status_code == 200


def test_request_rate_limit(tmp_path):
    (tmp_path / "bank.json").write_text(json.dumps(BANK))
    cfg = tmp_path / "teach-me.toml"
    cfg.write_text(
        f'subject = "Test Subject"\nbank = "bank.json"\ndata_dir = "{tmp_path / "data"}"\n'
        "[limits]\nrequests_per_minute = 3\n"
    )
    client = _signed_in_client(cfg)
    for _ in range(3):
        assert client.get("/api/state").status_code == 200
    res = client.get("/api/state")
    assert res.status_code == 429
    assert "too many requests" in res.json()["error"]


def test_tutor_daily_budget(tmp_path):
    (tmp_path / "bank.json").write_text(json.dumps(BANK))
    cfg = tmp_path / "teach-me.toml"
    cfg.write_text(
        f'subject = "Test Subject"\nbank = "bank.json"\ndata_dir = "{tmp_path / "data"}"\n'
        "[limits]\ntutor_per_day = 1\n"
        # localhost counts as keyless, so the tutor is "on" without an API key
        '[tutor]\nmodel = "stub"\nbase_url = "http://localhost:9/v1"\n'
    )
    client = _signed_in_client(cfg)
    first = client.post("/api/tutor", json={"message": "hi"})
    assert first.status_code == 200  # the call is spent even though nothing listens
    second = client.post("/api/tutor", json={"message": "hi again"})
    assert second.status_code == 429
    assert "budget" in second.json()["error"]


def test_auth_attempts_are_throttled(anon_client):
    for _ in range(10):
        res = anon_client.post("/api/login",
                               json={"username": "ghost", "password": "wrongwrong"})
        assert res.status_code == 401
    res = anon_client.post("/api/login",
                           json={"username": "ghost", "password": "wrongwrong"})
    assert res.status_code == 429


def test_sessions_survive_restart(tmp_path):
    (tmp_path / "bank.json").write_text(json.dumps(BANK))
    cfg = tmp_path / "teach-me.toml"
    cfg.write_text(
        f'subject = "Test Subject"\nbank = "bank.json"\ndata_dir = "{tmp_path / "data"}"\n'
    )
    first = _signed_in_client(cfg)
    cookie = first.cookies["session"]

    reborn = TestClient(create_app(cfg))
    reborn.cookies.set("session", cookie)
    assert reborn.get("/api/state").status_code == 200
