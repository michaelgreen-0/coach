import random
import string
from datetime import datetime, timezone

from . import analytics
from ..core.models import Bank, Err, Ok, Question, Result
from .storage import Progress, QuestionProgress, Session


def parse_answer(raw: str, n_options: int) -> Result[frozenset[int]]:
    letters = {c for c in raw.upper() if c in string.ascii_uppercase}
    indices = {ord(c) - ord("A") for c in letters}
    if not indices:
        return Err("enter one or more answer letters")
    if any(i >= n_options for i in indices):
        last = chr(ord("A") + n_options - 1)
        return Err(f"answers must be letters A-{last}")
    return Ok(frozenset(indices))


def is_correct(question: Question, answer: frozenset[int]) -> bool:
    return answer == frozenset(question.correct)


def pick_questions(bank: Bank, progress: Progress, mode: str,
                   topic: str | None = None,
                   rng: random.Random | None = None) -> list[Question]:
    rng = rng or random
    if mode == "topic":
        pool = [q for q in bank.questions if topic in q.topics]
    elif mode == "unseen":
        pool = [q for q in bank.questions if progress.stats_for(q.id).attempts == 0]
    elif mode == "missed":
        pool = [q for q in bank.questions if progress.stats_for(q.id).last_result is False]
    elif mode == "weak":
        weakest = {t.topic for t in analytics.weak_topics(bank, progress)[:3]}
        pool = [q for q in bank.questions if weakest & set(q.topics)] if weakest else list(bank.questions)
    else:
        pool = list(bank.questions)

    pool = list(pool)
    rng.shuffle(pool)
    pool.sort(key=lambda q: (progress.stats_for(q.id).streak, progress.stats_for(q.id).attempts))
    return pool


def record_result(progress: Progress, qid: int, correct: bool) -> None:
    qs = progress.questions.setdefault(str(qid), QuestionProgress())
    qs.attempts += 1
    if correct:
        qs.correct += 1
        qs.streak = max(qs.streak, 0) + 1
    else:
        qs.streak = min(qs.streak, 0) - 1
    qs.last_result = correct
    qs.last_seen = datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_session(progress: Progress, asked: int, correct: int) -> None:
    progress.sessions.append(Session(
        date=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        asked=asked,
        correct=correct,
    ))
