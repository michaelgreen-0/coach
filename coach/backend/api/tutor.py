from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..core.models import Err, Question
from ..services import analytics, tutor
from .deps import AppState, err, filtered_bank, get_current_user, get_state
from .schemas import TutorRequest

router = APIRouter(prefix="/api", tags=["tutor"])


@router.post("/tutor")
def tutor_chat(req: TutorRequest, state: AppState = Depends(get_state),
               user: str = Depends(get_current_user)):
    cfg = state.cfg
    if not state.tutor_on:
        return err("tutor is not configured", status=503)
    st = state.subject_state(req.subject)
    if st is None:
        return err(f"unknown subject: {req.subject}", status=404)

    question: Question | None = None
    result: str | None = None
    reveal = True
    if req.question_id is not None:
        question = st.by_id.get(req.question_id)
        if question is None:
            return err(f"unknown question id: {req.question_id}", status=404)
        if req.stage == "hint":
            reveal = False
            result = "has not answered yet"
        elif req.correct is not None:
            result = ("answered correctly" if req.correct
                      else f"answered incorrectly (picked {req.picked})")

    if not state.limiter.allow(f"tutor:{user}", cfg.limits.tutor_per_day, 86400):
        return err("tutor budget used up for today — it resets over the next 24h",
                   status=429)

    up = state.user_progress(user, st)
    if isinstance(up, Err):
        return err(up.message, status=500)
    bank = filtered_bank(st.bank, req.set)
    with state.lock:
        summary = analytics.progress_summary_text(bank, up.progress)

    try:
        session = tutor.Tutor(cfg.tutor, st.subject.name, question=question,
                              result=result, progress_summary=summary,
                              reveal_answer=reveal)
    except Exception as exc:  # constructing the client can fail (bad base_url, etc.)
        return err(f"could not start tutor: {exc}", status=502)
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
