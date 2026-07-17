"""Web front end — the study flows exposed as a small JSON API.

Grading stays server-side: quiz payloads never include `correct` or
`explanation`, so the browser can't leak answers before they're earned.

Every study endpoint requires a signed-in user; each user gets their own
progress files under data_dir/progress/<username>/.
"""

import os
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import analytics, quiz, tutor
from .auth import SESSION_TTL, SessionStore, UserStore
from .config import Config, Subject, load_config
from .limits import RateLimiter
from .models import Bank, Err, Question
from .storage import Progress, load_bank, load_progress, save_progress

STATIC_DIR = Path(__file__).resolve().parent / "static"
INVITE_ENV = "TEACH_ME_INVITE_CODE"
SESSION_COOKIE = "session"
AUTH_ATTEMPTS, AUTH_WINDOW = 10, 300  # sign-in tries per IP per 5 minutes


@dataclass
class SubjectState:
    subject: Subject
    bank: Bank
    by_id: dict[int, Question]


@dataclass
class UserProgress:
    progress: Progress
    path: Path


def _bank_sets(bank: Bank) -> list[str]:
    return sorted({q.set_name for q in bank.questions if q.set_name})


def _filtered_bank(bank: Bank, active_set: str | None) -> Bank:
    if active_set is None:
        return bank
    return Bank(questions=tuple(q for q in bank.questions if q.set_name == active_set))


def _err(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


class RegisterRequest(BaseModel):
    username: str
    password: str
    invite: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class QuizRequest(BaseModel):
    mode: str
    topic: str | None = None
    set: str | None = None
    subject: str | None = None


class AnswerRequest(BaseModel):
    id: int
    answer: str  # option letters, e.g. "a" or "ac" for multi-answer
    subject: str | None = None


class SessionRequest(BaseModel):
    asked: int
    correct: int
    subject: str | None = None


class TutorRequest(BaseModel):
    message: str
    history: list[dict] = []
    question_id: int | None = None
    stage: str = "chat"  # "hint" before answering, "reveal" after, "chat" from the menu
    correct: bool | None = None
    picked: str = ""  # letters the student chose, for the post-answer context
    set: str | None = None
    subject: str | None = None


def create_app(config_path: Path | None = None) -> FastAPI:
    cfg_result = load_config(config_path)
    if isinstance(cfg_result, Err):
        raise RuntimeError(cfg_result.message)
    cfg: Config = cfg_result.value

    states: dict[str, SubjectState] = {}
    for subj in cfg.subjects:
        bank_result = load_bank(subj.bank_path)
        if isinstance(bank_result, Err):
            raise RuntimeError(f"subject '{subj.name}': {bank_result.message}")
        states[subj.slug] = SubjectState(
            subject=subj,
            bank=bank_result.value,
            by_id={q.id: q for q in bank_result.value.questions},
        )
    default_slug = cfg.subjects[0].slug

    users = UserStore(cfg.data_dir / "users.json")
    sessions = SessionStore(cfg.data_dir / "sessions.json")
    invite_code = os.environ.get(INVITE_ENV, "")

    tutor_on = cfg.tutor is not None and tutor.tutor_available(cfg.tutor)
    lock = threading.Lock()  # guards the per-user progress cache and its saves
    progress_cache: dict[tuple[str, str], UserProgress] = {}
    limiter = RateLimiter()

    app = FastAPI(title="teach-me")

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request, exc):
        # keep one error envelope everywhere: {"error": ...}
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    def current_user(session: str | None = Cookie(default=None)) -> str:
        username = sessions.resolve(session)
        if username is None:
            raise HTTPException(status_code=401, detail="not signed in")
        if not limiter.allow(f"api:{username}", cfg.limits.requests_per_minute, 60):
            raise HTTPException(status_code=429,
                                detail="too many requests — give it a minute")
        return username

    def _client_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def _subject_state(slug: str | None) -> SubjectState | None:
        return states.get(slug or default_slug)

    def _user_progress(user: str, st: SubjectState) -> UserProgress | Err:
        key = (user, st.subject.slug)
        with lock:
            cached = progress_cache.get(key)
            if cached is not None:
                return cached
            path = cfg.data_dir / "progress" / user / st.subject.progress_file
            result = load_progress(path)
            if isinstance(result, Err):
                return result
            up = UserProgress(progress=result.value, path=path)
            progress_cache[key] = up
            return up

    def _save(up: UserProgress) -> str | None:
        result = save_progress(up.progress, up.path)
        return result.message if isinstance(result, Err) else None

    def _sign_in(response: Response, username: str) -> dict:
        token = sessions.create(username)
        response.set_cookie(
            SESSION_COOKIE, token,
            max_age=int(SESSION_TTL.total_seconds()),
            httponly=True, samesite="lax", path="/",
        )
        return {"username": username}

    # ── auth ──────────────────────────────────────────────

    @app.get("/api/auth")
    def auth_status(session: str | None = Cookie(default=None)):
        username = sessions.resolve(session)
        return {
            "signed_in": username is not None,
            "username": username,
            "invite_required": bool(invite_code),
        }

    @app.post("/api/register")
    def register(req: RegisterRequest, request: Request, response: Response):
        if not limiter.allow(f"auth:{_client_ip(request)}", AUTH_ATTEMPTS, AUTH_WINDOW):
            return _err("too many attempts — try again in a few minutes", status=429)
        if invite_code and not secrets.compare_digest(req.invite, invite_code):
            return _err("wrong invite code", status=403)
        result = users.register(req.username, req.password)
        if isinstance(result, Err):
            return _err(result.message)
        return _sign_in(response, req.username)

    @app.post("/api/login")
    def login(req: LoginRequest, request: Request, response: Response):
        if not limiter.allow(f"auth:{_client_ip(request)}", AUTH_ATTEMPTS, AUTH_WINDOW):
            return _err("too many attempts — try again in a few minutes", status=429)
        if not users.verify(req.username, req.password):
            return _err("wrong username or password", status=401)
        return _sign_in(response, req.username)

    @app.post("/api/logout")
    def logout(response: Response, session: str | None = Cookie(default=None)):
        sessions.revoke(session)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"signed_out": True}

    # ── studying ──────────────────────────────────────────

    @app.get("/api/subjects")
    def subjects(user: str = Depends(current_user)):
        return {
            "subjects": [
                {
                    "slug": subj.slug,
                    "name": subj.name,
                    "question_count": len(states[subj.slug].bank),
                }
                for subj in cfg.subjects
            ],
        }

    @app.get("/api/state")
    def state(subject: str | None = None, set: str | None = None,
              user: str = Depends(current_user)):
        st = _subject_state(subject)
        if st is None:
            return _err(f"unknown subject: {subject}", status=404)
        bank = _filtered_bank(st.bank, set)
        topics = [
            {"name": t, "questions": sum(1 for q in bank.questions if t in q.topics)}
            for t in bank.topics()
        ]
        return {
            "subject": st.subject.slug,
            "name": st.subject.name,
            "sets": _bank_sets(st.bank),
            "active_set": set,
            "question_count": len(bank),
            "topics": topics,
            "tutor_on": tutor_on,
            "tutor_disabled_hint": (
                f"tutor disabled — set ${cfg.tutor.api_key_env} to enable it."
                if cfg.tutor is not None and not tutor_on else None
            ),
        }

    @app.post("/api/quiz")
    def start_quiz(req: QuizRequest, user: str = Depends(current_user)):
        st = _subject_state(req.subject)
        if st is None:
            return _err(f"unknown subject: {req.subject}", status=404)
        up = _user_progress(user, st)
        if isinstance(up, Err):
            return _err(up.message, status=500)
        bank = _filtered_bank(st.bank, req.set)
        with lock:
            pool = quiz.pick_questions(bank, up.progress, req.mode, req.topic)

        focus: list[str] = []
        if req.mode == "weak":
            focus = [t.topic for t in analytics.weak_topics(bank, up.progress)[:3]]

        questions = [
            {
                "id": q.id,
                "question": q.question,
                "options": list(q.options),
                "topics": list(q.topics),
                # tells the UI how many to pick on multi-answer questions
                "select_n": len(q.correct) if q.is_multi else None,
            }
            for q in pool
        ]
        return {"questions": questions, "focus": focus}

    @app.post("/api/answer")
    def answer(req: AnswerRequest, user: str = Depends(current_user)):
        st = _subject_state(req.subject)
        if st is None:
            return _err(f"unknown subject: {req.subject}", status=404)
        q = st.by_id.get(req.id)
        if q is None:
            return _err(f"unknown question id: {req.id}", status=404)
        parsed = quiz.parse_answer(req.answer, len(q.options))
        if isinstance(parsed, Err):
            return _err(parsed.message)
        up = _user_progress(user, st)
        if isinstance(up, Err):
            return _err(up.message, status=500)

        correct = quiz.is_correct(q, parsed.value)
        with lock:
            quiz.record_result(up.progress, q.id, correct)
            warning = _save(up)
        return {
            "correct": correct,
            "correct_letters": list(q.answer_letters),
            "explanation": q.explanation,
            "warning": warning,
        }

    @app.post("/api/session")
    def finish_session(req: SessionRequest, user: str = Depends(current_user)):
        st = _subject_state(req.subject)
        if st is None:
            return _err(f"unknown subject: {req.subject}", status=404)
        if req.asked <= 0:
            return {"recorded": False, "warning": None}
        up = _user_progress(user, st)
        if isinstance(up, Err):
            return _err(up.message, status=500)
        with lock:
            quiz.record_session(up.progress, req.asked, req.correct)
            warning = _save(up)
        return {"recorded": True, "warning": warning}

    @app.get("/api/dashboard")
    def dashboard_data(subject: str | None = None, set: str | None = None,
                       user: str = Depends(current_user)):
        st = _subject_state(subject)
        if st is None:
            return _err(f"unknown subject: {subject}", status=404)
        up = _user_progress(user, st)
        if isinstance(up, Err):
            return _err(up.message, status=500)
        bank = _filtered_bank(st.bank, set)
        with lock:
            stats = analytics.topic_stats(bank, up.progress)
            seen, total, mastered = analytics.coverage(bank, up.progress)
            weak = analytics.weak_topics(bank, up.progress)[:3]
            overall = analytics.overall_accuracy(bank, up.progress)

        # weakest attempted first
        stats.sort(key=lambda t: (t.accuracy is None, t.accuracy or 0))
        return {
            "topics": [
                {
                    "topic": t.topic,
                    "questions": t.questions,
                    "seen": t.seen,
                    "attempts": t.attempts,
                    "accuracy": t.accuracy,
                }
                for t in stats
            ],
            "coverage": {"seen": seen, "total": total, "mastered": mastered},
            "focus": [
                {"topic": t.topic, "accuracy": t.accuracy}
                for t in weak if t.accuracy < 0.8
            ],
            "overall": overall,
        }

    @app.post("/api/tutor")
    def tutor_chat(req: TutorRequest, user: str = Depends(current_user)):
        if not tutor_on:
            return _err("tutor is not configured", status=503)
        st = _subject_state(req.subject)
        if st is None:
            return _err(f"unknown subject: {req.subject}", status=404)

        question: Question | None = None
        result: str | None = None
        reveal = True
        if req.question_id is not None:
            question = st.by_id.get(req.question_id)
            if question is None:
                return _err(f"unknown question id: {req.question_id}", status=404)
            if req.stage == "hint":
                reveal = False
                result = "has not answered yet"
            elif req.correct is not None:
                result = ("answered correctly" if req.correct
                          else f"answered incorrectly (picked {req.picked})")

        # the tutor is the endpoint that costs real money — budget it per user
        if not limiter.allow(f"tutor:{user}", cfg.limits.tutor_per_day, 86400):
            return _err("tutor budget used up for today — it resets over the next 24h",
                        status=429)

        up = _user_progress(user, st)
        if isinstance(up, Err):
            return _err(up.message, status=500)
        bank = _filtered_bank(st.bank, req.set)
        with lock:
            summary = analytics.progress_summary_text(bank, up.progress)

        try:
            session = tutor.Tutor(cfg.tutor, st.subject.name, question=question,
                                  result=result, progress_summary=summary,
                                  reveal_answer=reveal)
        except Exception as exc:  # constructing the client can fail (bad base_url, etc.)
            return _err(f"could not start tutor: {exc}", status=502)
        session.history = [
            {"role": m["role"], "content": m["content"]}
            for m in req.history if m.get("role") in ("user", "assistant")
        ]

        def stream():
            try:
                yield from session.ask_stream(req.message)
            except Exception as exc:  # network / API errors mid-chat are recoverable
                yield f"\n\n[tutor error: {exc}]"

        return StreamingResponse(stream(), media_type="text/plain; charset=utf-8")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
