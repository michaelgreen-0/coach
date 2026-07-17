import random

from coach.backend.core.models import Bank, Err, Ok, Question
from coach.backend.services.quiz import (
    is_correct,
    parse_answer,
    pick_questions,
    record_result,
    record_session,
)
from coach.backend.services.storage import Progress, QuestionProgress


def _q(qid, topics=("T",), correct=(0,)):
    return Question(id=qid, question=f"q{qid}", options=("a", "b", "c", "d"),
                    correct=correct, topics=topics)


def test_parse_answer_single_and_multi():
    assert parse_answer("a", 4) == Ok(frozenset({0}))
    assert parse_answer("ac", 4) == Ok(frozenset({0, 2}))
    assert parse_answer("AC", 4) == Ok(frozenset({0, 2}))  # case-insensitive


def test_parse_answer_errors():
    assert isinstance(parse_answer("", 4), Err)      # nothing
    assert isinstance(parse_answer("12", 4), Err)    # no letters
    assert isinstance(parse_answer("e", 4), Err)     # out of range


def test_is_correct():
    q = _q(1, correct=(0, 2))
    assert is_correct(q, frozenset({0, 2})) is True
    assert is_correct(q, frozenset({0})) is False


def test_record_result_streak_and_fields():
    p = Progress()
    record_result(p, 1, True)
    qs = p.questions["1"]
    assert (qs.attempts, qs.correct, qs.streak, qs.last_result) == (1, 1, 1, True)
    assert qs.last_seen is not None

    record_result(p, 1, True)
    assert p.questions["1"].streak == 2

    record_result(p, 1, False)  # a wrong answer resets the run to -1
    qs = p.questions["1"]
    assert (qs.attempts, qs.correct, qs.streak, qs.last_result) == (3, 2, -1, False)


def test_record_session():
    p = Progress()
    record_session(p, asked=5, correct=3)
    assert len(p.sessions) == 1
    assert (p.sessions[0].asked, p.sessions[0].correct) == (5, 3)


BANK = Bank(questions=(_q(1), _q(2), _q(3, topics=("B",)), _q(4)))
PROGRESS = Progress(questions={
    "2": QuestionProgress(attempts=1, correct=1, streak=1),
    "4": QuestionProgress(attempts=1, correct=0, streak=-1, last_result=False),
})
RNG = random.Random(0)


def _ids(questions):
    return {q.id for q in questions}


def test_pick_unseen():
    assert _ids(pick_questions(BANK, PROGRESS, "unseen", rng=RNG)) == {1, 3}


def test_pick_missed():
    assert _ids(pick_questions(BANK, PROGRESS, "missed", rng=RNG)) == {4}


def test_pick_topic():
    assert _ids(pick_questions(BANK, PROGRESS, "topic", topic="B", rng=RNG)) == {3}


def test_pick_all_orders_weakest_first():
    ordered = pick_questions(BANK, PROGRESS, "all", rng=RNG)
    assert _ids(ordered) == {1, 2, 3, 4}
    assert ordered[0].id == 4  # lowest streak (-1) surfaces first


def test_pick_weak_falls_back_to_all_without_data():
    # No topic has >= 3 attempts, so weak mode uses the whole bank.
    assert _ids(pick_questions(BANK, PROGRESS, "weak", rng=RNG)) == {1, 2, 3, 4}
