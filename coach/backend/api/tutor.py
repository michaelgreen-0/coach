import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..core.models import Err, Question
from ..services import analytics, tutor
from .deps import AppState, client_ip, err, filtered_bank, get_current_user, get_state
from .schemas import TutorRequest

logger = logging.getLogger("coach.tutor")

router = APIRouter(prefix="/api", tags=["tutor"])

# Bound the size of a single tutor call so no one request can run up the bill:
# the message is capped, and the client-supplied history is trimmed to the most
# recent turns with each turn's text clipped.
MAX_MESSAGE_CHARS = 4000
MAX_HISTORY_TURNS = 12
MAX_TURN_CHARS = 4000


def _bounded_history(history: list[dict]) -> list[dict]:
    turns = [
        {"role": m["role"], "content": str(m.get("content", ""))[:MAX_TURN_CHARS]}
        for m in history if m.get("role") in ("user", "assistant")
    ]
    return turns[-MAX_HISTORY_TURNS:]


@router.post("/tutor")
def tutor_chat(req: TutorRequest, request: Request, state: AppState = Depends(get_state),
               user: str = Depends(get_current_user)):
    cfg = state.cfg
    if not state.tutor_on:
        return err("tutor is not configured", status=503)
    st = state.subject_state(req.subject)
    if st is None:
        return err(f"unknown subject: {req.subject}", status=404)
    if len(req.message) > MAX_MESSAGE_CHARS:
        return err("message is too long", status=400)

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

    # narrowest budget first, so a request a tighter cap rejects doesn't burn a broader slot
    if not state.limiter.allow(f"tutor:{user}", cfg.limits.tutor_per_day, 86400):
        return err("tutor budget used up for today — it resets over the next 24h",
                   status=429)
    if not state.limiter.allow(f"tutor:ip:{client_ip(request)}",
                               cfg.limits.tutor_per_ip_per_day, 86400):
        return err("tutor budget used up for today — it resets over the next 24h",
                   status=429)
    if not state.limiter.allow("tutor:global", cfg.limits.tutor_global_per_day, 86400):
        return err("the tutor is unusually busy right now — please try again later",
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
    except Exception:  # constructing the client can fail (bad base_url, etc.)
        logger.exception("tutor setup failed for subject %s", st.subject.slug)
        return err("could not reach the tutor right now — please try again", status=502)
    session.history = _bounded_history(req.history)

    def stream():
        try:
            yield from session.ask_stream(req.message)
        except Exception:  # network / API errors mid-chat are recoverable
            logger.exception("tutor stream failed for user %s", user)
            yield "\n\n[the tutor hit an error — please try again]"

    return StreamingResponse(stream(), media_type="text/plain; charset=utf-8")
