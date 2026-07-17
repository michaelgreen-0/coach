import threading
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Cookie, HTTPException, Request
from fastapi.responses import JSONResponse

from ..core.config import Config, Subject
from ..core.limits import RateLimiter
from ..core.models import Bank, Err, Question
from ..core.security import SessionStore, UserStore
from ..services.storage import Progress, load_progress, save_progress


@dataclass
class SubjectState:
    subject: Subject
    bank: Bank
    by_id: dict[int, Question]


@dataclass
class UserProgress:
    progress: Progress
    path: Path


@dataclass
class AppState:
    cfg: Config
    states: dict[str, SubjectState]
    default_slug: str
    users: UserStore
    sessions: SessionStore
    invite_code: str
    tutor_on: bool
    limiter: RateLimiter
    lock: threading.Lock = field(default_factory=threading.Lock)  # guards the progress cache and its saves
    progress_cache: dict[tuple[str, str], UserProgress] = field(default_factory=dict)

    def subject_state(self, slug: str | None) -> SubjectState | None:
        return self.states.get(slug or self.default_slug)

    def user_progress(self, user: str, st: SubjectState) -> UserProgress | Err:
        key = (user, st.subject.slug)
        with self.lock:
            cached = self.progress_cache.get(key)
            if cached is not None:
                return cached
            path = self.cfg.data_dir / "progress" / user / st.subject.progress_file
            result = load_progress(path)
            if isinstance(result, Err):
                return result
            up = UserProgress(progress=result.value, path=path)
            self.progress_cache[key] = up
            return up

    def save(self, up: UserProgress) -> str | None:
        result = save_progress(up.progress, up.path)
        return result.message if isinstance(result, Err) else None


def get_state(request: Request) -> AppState:
    return request.app.state.app_state


def get_current_user(request: Request, session: str | None = Cookie(default=None)) -> str:
    state = get_state(request)
    username = state.sessions.resolve(session)
    if username is None:
        raise HTTPException(status_code=401, detail="not signed in")
    if not state.limiter.allow(f"api:{username}", state.cfg.limits.requests_per_minute, 60):
        raise HTTPException(status_code=429, detail="too many requests — give it a minute")
    return username


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def err(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def bank_sets(bank: Bank) -> list[str]:
    return sorted({q.set_name for q in bank.questions if q.set_name})


def filtered_bank(bank: Bank, active_set: str | None) -> Bank:
    if active_set is None:
        return bank
    return Bank(questions=tuple(q for q in bank.questions if q.set_name == active_set))
