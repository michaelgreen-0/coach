"""Users and sessions for the web front end, stored as JSON under data_dir.

Passwords are hashed with scrypt (stdlib) and a per-user salt. Sessions are
random opaque tokens persisted to disk, so a server restart doesn't sign
everyone out.
"""

import hashlib
import hmac
import json
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .models import Err, Ok, Result

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")
MIN_PASSWORD_LEN = 8
SESSION_TTL = timedelta(days=30)


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserRecord(BaseModel):
    salt: str  # hex
    hash: str  # hex
    created: str


class SessionRecord(BaseModel):
    username: str
    expires: str


def _load_json(path: Path, model: type[BaseModel]) -> dict:
    """Best-effort read of a {key: record} file; unreadable files start empty."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        return {k: model.model_validate(v) for k, v in raw.items()}
    except (json.JSONDecodeError, ValidationError, OSError):
        return {}


def _save_json(path: Path, records: dict) -> Result[None]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v.model_dump() for k, v in records.items()}
        path.write_text(json.dumps(payload, indent=2))
    except OSError as exc:
        return Err(f"could not save {path}: {exc}")
    return Ok(None)


class UserStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._users: dict[str, UserRecord] = _load_json(path, UserRecord)

    def register(self, username: str, password: str) -> Result[None]:
        if not USERNAME_RE.match(username):
            return Err("usernames are 3-32 characters: lowercase letters, digits, dashes")
        if len(password) < MIN_PASSWORD_LEN:
            return Err(f"passwords need at least {MIN_PASSWORD_LEN} characters")
        with self._lock:
            if username in self._users:
                return Err("that username is taken")
            salt = secrets.token_bytes(16)
            self._users[username] = UserRecord(
                salt=salt.hex(),
                hash=_hash_password(password, salt).hex(),
                created=_now().isoformat(timespec="seconds"),
            )
            return _save_json(self._path, self._users)

    def verify(self, username: str, password: str) -> bool:
        with self._lock:
            rec = self._users.get(username)
        if rec is None:
            # burn comparable time so absent users aren't detectable by timing
            _hash_password(password, b"x" * 16)
            return False
        expected = bytes.fromhex(rec.hash)
        return hmac.compare_digest(_hash_password(password, bytes.fromhex(rec.salt)), expected)


class SessionStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionRecord] = _load_json(path, SessionRecord)
        self._prune()

    @staticmethod
    def _expired(rec: SessionRecord) -> bool:
        try:
            return datetime.fromisoformat(rec.expires) <= _now()
        except ValueError:
            return True

    def _prune(self) -> None:
        with self._lock:
            expired = [t for t, s in self._sessions.items() if self._expired(s)]
            for t in expired:
                del self._sessions[t]

    def create(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = SessionRecord(
                username=username,
                expires=(_now() + SESSION_TTL).isoformat(timespec="seconds"),
            )
            _save_json(self._path, self._sessions)
        return token

    def resolve(self, token: str | None) -> str | None:
        if not token:
            return None
        with self._lock:
            rec = self._sessions.get(token)
        if rec is None or self._expired(rec):
            return None
        return rec.username

    def revoke(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            if self._sessions.pop(token, None) is not None:
                _save_json(self._path, self._sessions)
