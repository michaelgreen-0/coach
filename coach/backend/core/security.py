import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Err, Ok, Result

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")
MIN_PASSWORD_LEN = 8
SESSION_TTL = timedelta(days=30)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    salt     TEXT NOT NULL,
    hash     TEXT NOT NULL,
    created  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token    TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    expires  TEXT NOT NULL
);
"""


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(when: datetime) -> str:
    # fixed-width UTC strings so SQLite's lexical comparison matches chronology
    return when.isoformat(timespec="seconds")


class Database:
    """A single SQLite file shared by the user and session stores. One
    connection guarded by a lock serialises threads; WAL mode plus a busy
    timeout let separate worker processes share the same file safely."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA)

    def write(self, sql: str, params: tuple = ()) -> None:
        with self._lock, self._conn:
            self._conn.execute(sql, params)

    def write_many(self, sql: str, rows: list[tuple]) -> None:
        with self._lock, self._conn:
            self._conn.executemany(sql, rows)

    def read_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()


class UserStore:
    def __init__(self, db: Database):
        self._db = db

    def register(self, username: str, password: str) -> Result[None]:
        if not USERNAME_RE.match(username):
            return Err("usernames are 3-32 characters: lowercase letters, digits, dashes")
        if len(password) < MIN_PASSWORD_LEN:
            return Err(f"passwords need at least {MIN_PASSWORD_LEN} characters")
        salt = secrets.token_bytes(16)
        try:
            self._db.write(
                "INSERT INTO users (username, salt, hash, created) VALUES (?, ?, ?, ?)",
                (username, salt.hex(), _hash_password(password, salt).hex(), _stamp(_now())),
            )
        except sqlite3.IntegrityError:
            return Err("that username is taken")
        return Ok(None)

    def verify(self, username: str, password: str) -> bool:
        row = self._db.read_one(
            "SELECT salt, hash FROM users WHERE username = ?", (username,))
        if row is None:
            # burn comparable time so absent users aren't detectable by timing
            _hash_password(password, b"x" * 16)
            return False
        expected = bytes.fromhex(row["hash"])
        return hmac.compare_digest(_hash_password(password, bytes.fromhex(row["salt"])), expected)


class SessionStore:
    def __init__(self, db: Database):
        self._db = db
        self._db.write("DELETE FROM sessions WHERE expires <= ?", (_stamp(_now()),))

    def create(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        self._db.write(
            "INSERT INTO sessions (token, username, expires) VALUES (?, ?, ?)",
            (token, username, _stamp(_now() + SESSION_TTL)),
        )
        return token

    def resolve(self, token: str | None) -> str | None:
        if not token:
            return None
        row = self._db.read_one(
            "SELECT username FROM sessions WHERE token = ? AND expires > ?",
            (token, _stamp(_now())),
        )
        return row["username"] if row else None

    def revoke(self, token: str | None) -> None:
        if not token:
            return
        self._db.write("DELETE FROM sessions WHERE token = ?", (token,))


def migrate_json_files(db: Database, data_dir: Path) -> None:
    """Import legacy users.json/sessions.json into empty tables, once. Runs only
    when the corresponding table is empty, so it never clobbers live data. The
    source files are left in place — delete them once you've confirmed the import."""
    if db.read_one("SELECT 1 FROM users LIMIT 1") is None:
        _import(db, data_dir / "users.json",
                "INSERT OR IGNORE INTO users (username, salt, hash, created) VALUES (?, ?, ?, ?)",
                lambda k, r: (k, r["salt"], r["hash"], r.get("created", _stamp(_now()))),
                required={"salt", "hash"})
    if db.read_one("SELECT 1 FROM sessions LIMIT 1") is None:
        _import(db, data_dir / "sessions.json",
                "INSERT OR IGNORE INTO sessions (token, username, expires) VALUES (?, ?, ?)",
                lambda k, r: (k, r["username"], r["expires"]),
                required={"username", "expires"})


def _import(db: Database, path: Path, sql: str, to_row, required: set[str]) -> None:
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    rows = [to_row(k, r) for k, r in data.items() if required <= r.keys()]
    if rows:
        db.write_many(sql, rows)
