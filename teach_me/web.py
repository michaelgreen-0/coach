"""Web front end. Same flows as the CLI, exposed as a small JSON API.

Grading stays server-side: quiz payloads never include `correct` or
`explanation`, so the browser can't leak answers before they're earned.
"""

import threading
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analytics, quiz, tutor
from .config import Chapter, Config, load_config
from .models import Bank, Err, Question
from .storage import Progress, load_bank, load_progress, save_progress

STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass
class ChapterState:
    chapter: Chapter
    bank: Bank
    by_id: dict[int, Question]
    progress: Progress
    progress_path: Path


def _bank_sets(bank: Bank) -> list[str]:
    return sorted({q.set_name for q in bank.questions if q.set_name})


def _filtered_bank(bank: Bank, active_set: str | None) -> Bank:
    if active_set is None:
        return bank
    return Bank(questions=tuple(q for q in bank.questions if q.set_name == active_set))


def _err(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


class QuizRequest(BaseModel):
    mode: str
    topic: str | None = None
    set: str | None = None
    chapter: str | None = None


class AnswerRequest(BaseModel):
    id: int
    answer: str  # letters, exactly as the CLI accepts them ("a", "ac", ...)
    chapter: str | None = None


class SessionRequest(BaseModel):
    asked: int
    correct: int
    chapter: str | None = None


class TutorRequest(BaseModel):
    message: str
    history: list[dict] = []
    question_id: int | None = None
    stage: str = "chat"  # "hint" before answering, "reveal" after, "chat" from the menu
    correct: bool | None = None
    picked: str = ""  # letters the student chose, for the post-answer context
    set: str | None = None
    chapter: str | None = None


def create_app(config_path: Path | None = None) -> FastAPI:
    cfg_result = load_config(config_path)
    if isinstance(cfg_result, Err):
        raise RuntimeError(cfg_result.message)
    cfg: Config = cfg_result.value

    states: dict[str, ChapterState] = {}
    for ch in cfg.chapters:
        bank_result = load_bank(ch.bank_path)
        if isinstance(bank_result, Err):
            raise RuntimeError(f"chapter '{ch.subject}': {bank_result.message}")
        progress_path = cfg.data_dir / ch.progress_file
        progress_result = load_progress(progress_path)
        if isinstance(progress_result, Err):
            raise RuntimeError(f"chapter '{ch.subject}': {progress_result.message}")
        states[ch.slug] = ChapterState(
            chapter=ch,
            bank=bank_result.value,
            by_id={q.id: q for q in bank_result.value.questions},
            progress=progress_result.value,
            progress_path=progress_path,
        )
    default_slug = cfg.chapters[0].slug

    tutor_on = cfg.tutor is not None and tutor.tutor_available(cfg.tutor)
    lock = threading.Lock()  # progress is shared mutable state across requests

    app = FastAPI(title="teach-me")

    def _chapter_state(slug: str | None) -> ChapterState | None:
        return states.get(slug or default_slug)

    def _save(st: ChapterState) -> str | None:
        result = save_progress(st.progress, st.progress_path)
        return result.message if isinstance(result, Err) else None

    @app.get("/api/chapters")
    def chapters():
        return {
            "chapters": [
                {
                    "slug": ch.slug,
                    "subject": ch.subject,
                    "question_count": len(states[ch.slug].bank),
                }
                for ch in cfg.chapters
            ],
        }

    @app.get("/api/state")
    def state(chapter: str | None = None, set: str | None = None):
        st = _chapter_state(chapter)
        if st is None:
            return _err(f"unknown chapter: {chapter}", status=404)
        bank = _filtered_bank(st.bank, set)
        topics = [
            {"name": t, "questions": sum(1 for q in bank.questions if t in q.topics)}
            for t in bank.topics()
        ]
        return {
            "chapter": st.chapter.slug,
            "subject": st.chapter.subject,
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
    def start_quiz(req: QuizRequest):
        st = _chapter_state(req.chapter)
        if st is None:
            return _err(f"unknown chapter: {req.chapter}", status=404)
        bank = _filtered_bank(st.bank, req.set)
        with lock:
            pool = quiz.pick_questions(bank, st.progress, req.mode, req.topic)

        focus: list[str] = []
        if req.mode == "weak":
            focus = [t.topic for t in analytics.weak_topics(bank, st.progress)[:3]]

        questions = [
            {
                "id": q.id,
                "question": q.question,
                "options": list(q.options),
                "topics": list(q.topics),
                # the CLI tells you how many to pick on multi-answer questions
                "select_n": len(q.correct) if q.is_multi else None,
            }
            for q in pool
        ]
        return {"questions": questions, "focus": focus}

    @app.post("/api/answer")
    def answer(req: AnswerRequest):
        st = _chapter_state(req.chapter)
        if st is None:
            return _err(f"unknown chapter: {req.chapter}", status=404)
        q = st.by_id.get(req.id)
        if q is None:
            return _err(f"unknown question id: {req.id}", status=404)
        parsed = quiz.parse_answer(req.answer, len(q.options))
        if isinstance(parsed, Err):
            return _err(parsed.message)

        correct = quiz.is_correct(q, parsed.value)
        with lock:
            quiz.record_result(st.progress, q.id, correct)
            warning = _save(st)
        return {
            "correct": correct,
            "correct_letters": list(q.answer_letters),
            "explanation": q.explanation,
            "warning": warning,
        }

    @app.post("/api/session")
    def finish_session(req: SessionRequest):
        st = _chapter_state(req.chapter)
        if st is None:
            return _err(f"unknown chapter: {req.chapter}", status=404)
        if req.asked <= 0:
            return {"recorded": False, "warning": None}
        with lock:
            quiz.record_session(st.progress, req.asked, req.correct)
            warning = _save(st)
        return {"recorded": True, "warning": warning}

    @app.get("/api/dashboard")
    def dashboard_data(chapter: str | None = None, set: str | None = None):
        st = _chapter_state(chapter)
        if st is None:
            return _err(f"unknown chapter: {chapter}", status=404)
        bank = _filtered_bank(st.bank, set)
        with lock:
            stats = analytics.topic_stats(bank, st.progress)
            seen, total, mastered = analytics.coverage(bank, st.progress)
            weak = analytics.weak_topics(bank, st.progress)[:3]
            overall = analytics.overall_accuracy(bank, st.progress)

        # Same ordering as the terminal dashboard: weakest attempted first.
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
    def tutor_chat(req: TutorRequest):
        if not tutor_on:
            return _err("tutor is not configured", status=503)
        st = _chapter_state(req.chapter)
        if st is None:
            return _err(f"unknown chapter: {req.chapter}", status=404)

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

        bank = _filtered_bank(st.bank, req.set)
        with lock:
            summary = analytics.progress_summary_text(bank, st.progress)

        try:
            session = tutor.Tutor(cfg.tutor, st.chapter.subject, question=question,
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
