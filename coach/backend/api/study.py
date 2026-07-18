# Grading stays server-side: quiz payloads never include `correct`/`explanation`, so the browser can't leak answers before they're earned.

from fastapi import APIRouter, Depends

from ..core.models import Err
from ..services import analytics, quiz
from ..services.storage import Progress
from .deps import (
    AppState,
    bank_sets,
    err,
    filtered_bank,
    get_current_user,
    get_optional_user,
    get_state,
)
from .schemas import AnswerRequest, QuizRequest, SessionRequest

router = APIRouter(prefix="/api", tags=["study"])

# Modes that lean on saved progress; only signed-in users can run them.
PROGRESS_MODES = {"weak", "unseen", "missed"}


@router.get("/subjects")
def subjects(state: AppState = Depends(get_state), user: str | None = Depends(get_optional_user)):
    return {
        "subjects": [
            {
                "slug": subj.slug,
                "name": subj.name,
                "question_count": len(state.states[subj.slug].bank),
            }
            for subj in state.cfg.subjects
        ],
    }


@router.get("/state")
def state_view(subject: str | None = None, set: str | None = None,
               state: AppState = Depends(get_state), user: str | None = Depends(get_optional_user)):
    st = state.subject_state(subject)
    if st is None:
        return err(f"unknown subject: {subject}", status=404)
    bank = filtered_bank(st.bank, set)
    topics = [
        {"name": t, "questions": sum(1 for q in bank.questions if t in q.topics)}
        for t in bank.topics()
    ]
    cfg = state.cfg
    return {
        "subject": st.subject.slug,
        "name": st.subject.name,
        "sets": bank_sets(st.bank),
        "active_set": set,
        "question_count": len(bank),
        "topics": topics,
        "signed_in": user is not None,
        "tutor_on": state.tutor_on,
        "tutor_disabled_hint": (
            f"tutor disabled — set ${cfg.tutor.api_key_env} to enable it."
            if cfg.tutor is not None and not state.tutor_on else None
        ),
    }


@router.post("/quiz")
def start_quiz(req: QuizRequest, state: AppState = Depends(get_state),
               user: str | None = Depends(get_optional_user)):
    st = state.subject_state(req.subject)
    if st is None:
        return err(f"unknown subject: {req.subject}", status=404)
    if user is None and req.mode in PROGRESS_MODES:
        return err("sign in to use this quiz mode", status=401)

    # Anonymous visitors quiz against empty, unsaved progress.
    if user is None:
        progress = Progress()
    else:
        up = state.user_progress(user, st)
        if isinstance(up, Err):
            return err(up.message, status=500)
        progress = up.progress
    bank = filtered_bank(st.bank, req.set)
    with state.lock:
        pool = quiz.pick_questions(bank, progress, req.mode, req.topic)

    focus: list[str] = []
    if req.mode == "weak":
        focus = [t.topic for t in analytics.weak_topics(bank, progress)[:3]]

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


@router.post("/answer")
def answer(req: AnswerRequest, state: AppState = Depends(get_state),
           user: str | None = Depends(get_optional_user)):
    st = state.subject_state(req.subject)
    if st is None:
        return err(f"unknown subject: {req.subject}", status=404)
    q = st.by_id.get(req.id)
    if q is None:
        return err(f"unknown question id: {req.id}", status=404)
    parsed = quiz.parse_answer(req.answer, len(q.options))
    if isinstance(parsed, Err):
        return err(parsed.message)

    correct = quiz.is_correct(q, parsed.value)
    warning = None
    # Anonymous answers are graded but never recorded — no account to save under.
    if user is not None:
        up = state.user_progress(user, st)
        if isinstance(up, Err):
            return err(up.message, status=500)
        with state.lock:
            quiz.record_result(up.progress, q.id, correct)
            warning = state.save(up)
    return {
        "correct": correct,
        "correct_letters": list(q.answer_letters),
        "explanation": q.explanation,
        "warning": warning,
    }


@router.post("/session")
def finish_session(req: SessionRequest, state: AppState = Depends(get_state),
                   user: str | None = Depends(get_optional_user)):
    st = state.subject_state(req.subject)
    if st is None:
        return err(f"unknown subject: {req.subject}", status=404)
    # Nothing to record for anonymous sessions.
    if user is None or req.asked <= 0:
        return {"recorded": False, "warning": None}
    up = state.user_progress(user, st)
    if isinstance(up, Err):
        return err(up.message, status=500)
    with state.lock:
        quiz.record_session(up.progress, req.asked, req.correct)
        warning = state.save(up)
    return {"recorded": True, "warning": warning}


@router.get("/dashboard")
def dashboard_data(subject: str | None = None, set: str | None = None,
                   state: AppState = Depends(get_state), user: str = Depends(get_current_user)):
    st = state.subject_state(subject)
    if st is None:
        return err(f"unknown subject: {subject}", status=404)
    up = state.user_progress(user, st)
    if isinstance(up, Err):
        return err(up.message, status=500)
    bank = filtered_bank(st.bank, set)
    with state.lock:
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
