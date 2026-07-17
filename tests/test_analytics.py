from teach_me.backend.services.analytics import (
    coverage,
    overall_accuracy,
    progress_summary_text,
    topic_stats,
    weak_topics,
)
from teach_me.backend.core.models import Bank, Question
from teach_me.backend.services.storage import Progress, QuestionProgress


def _q(qid, topics):
    return Question(id=qid, question=f"q{qid}", options=("a", "b"), correct=(0,), topics=topics)


BANK = Bank(questions=(
    _q(1, ("A",)),
    _q(2, ("A", "B")),
    _q(3, ("B",)),
    _q(4, ("C",)),  # never attempted
))

PROGRESS = Progress(questions={
    "1": QuestionProgress(attempts=4, correct=1, streak=-1),
    "2": QuestionProgress(attempts=2, correct=2, streak=2),
    "3": QuestionProgress(attempts=5, correct=4, streak=3),
})


def _by_topic(stats):
    return {t.topic: t for t in stats}


def test_topic_stats_aggregate_across_multi_topic_questions():
    stats = _by_topic(topic_stats(BANK, PROGRESS))
    assert (stats["A"].questions, stats["A"].seen) == (2, 2)
    assert (stats["A"].attempts, stats["A"].correct) == (6, 3)
    assert stats["A"].accuracy == 0.5
    assert stats["B"].attempts == 7 and stats["B"].correct == 6
    assert stats["C"].seen == 0 and stats["C"].accuracy is None


def test_weak_topics_worst_first_and_min_attempts():
    weak = weak_topics(BANK, PROGRESS)
    assert [t.topic for t in weak] == ["A", "B"]  # C excluded (no attempts)


def test_coverage():
    seen, total, mastered = coverage(BANK, PROGRESS)
    assert (seen, total, mastered) == (3, 4, 2)  # q2 (streak 2) and q3 (streak 3)


def test_overall_accuracy():
    assert overall_accuracy(BANK, PROGRESS) == 7 / 11


def test_overall_accuracy_none_when_no_attempts():
    assert overall_accuracy(BANK, Progress()) is None


def test_progress_summary_text():
    text = progress_summary_text(BANK, PROGRESS)
    assert "- A: 50% over 6 attempts" in text
    assert "- B: 86% over 7 attempts" in text
    assert "C" not in text  # no attempts, omitted


def test_progress_summary_text_empty():
    assert progress_summary_text(BANK, Progress()) == "(no attempts recorded yet)"
