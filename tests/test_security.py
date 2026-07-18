import json
from datetime import timedelta
from pathlib import Path

from coach.backend.core.models import Err, Ok
from coach.backend.core.security import (
    Database,
    SessionStore,
    UserStore,
    _now,
    _stamp,
    migrate_json_files,
)


def _db(tmp_path: Path) -> Database:
    return Database(tmp_path / "coach.db")


def test_register_and_verify(tmp_path):
    users = UserStore(_db(tmp_path))
    assert isinstance(users.register("alice", "password123"), Ok)
    assert users.verify("alice", "password123") is True
    assert users.verify("alice", "wrongpass1") is False
    assert users.verify("nobody", "password123") is False


def test_register_validation_and_duplicates(tmp_path):
    users = UserStore(_db(tmp_path))
    assert isinstance(users.register("Bad Name", "password123"), Err)
    assert isinstance(users.register("goodname", "short"), Err)
    assert isinstance(users.register("goodname", "password123"), Ok)
    dupe = users.register("goodname", "otherpass1")
    assert isinstance(dupe, Err)
    assert "taken" in dupe.message


def test_session_lifecycle(tmp_path):
    sessions = SessionStore(_db(tmp_path))
    token = sessions.create("alice")
    assert sessions.resolve(token) == "alice"
    assert sessions.resolve(None) is None
    assert sessions.resolve("bogus") is None
    sessions.revoke(token)
    assert sessions.resolve(token) is None


def test_expired_session_is_not_resolved(tmp_path):
    db = _db(tmp_path)
    sessions = SessionStore(db)
    past = _stamp(_now() - timedelta(minutes=1))
    db.write("INSERT INTO sessions (token, username, expires) VALUES (?, ?, ?)",
             ("stale", "alice", past))
    assert sessions.resolve("stale") is None


def test_data_persists_across_store_instances(tmp_path):
    path = tmp_path / "coach.db"
    UserStore(Database(path)).register("alice", "password123")
    token = SessionStore(Database(path)).create("alice")
    # a fresh set of stores on the same file still sees everything
    assert UserStore(Database(path)).verify("alice", "password123") is True
    assert SessionStore(Database(path)).resolve(token) == "alice"


def test_migrates_legacy_json(tmp_path):
    # a legacy user, hashed the same way the store does, plus a live session
    seed = Database(tmp_path / "coach.db")
    UserStore(seed).register("legacy", "password123")
    user_row = seed.read_one("SELECT salt, hash, created FROM users WHERE username = 'legacy'")
    (tmp_path / "users.json").write_text(json.dumps({
        "legacy": {"salt": user_row["salt"], "hash": user_row["hash"], "created": user_row["created"]},
    }))
    (tmp_path / "sessions.json").write_text(json.dumps({
        "tok123": {"username": "legacy", "expires": _stamp(_now() + timedelta(days=1))},
    }))
    # migrate into a brand new database
    fresh = Database(tmp_path / "fresh.db")
    migrate_json_files(fresh, tmp_path)
    assert UserStore(fresh).verify("legacy", "password123") is True
    assert SessionStore(fresh).resolve("tok123") == "legacy"


def test_migration_skips_when_users_present(tmp_path):
    db = Database(tmp_path / "coach.db")
    UserStore(db).register("existing", "password123")
    (tmp_path / "users.json").write_text(json.dumps({
        "intruder": {"salt": "00", "hash": "00", "created": "2020-01-01T00:00:00+00:00"},
    }))
    migrate_json_files(db, tmp_path)
    # non-empty table means the legacy file is ignored
    assert db.read_one("SELECT 1 FROM users WHERE username = 'intruder'") is None
