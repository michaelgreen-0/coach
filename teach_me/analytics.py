from dataclasses import dataclass

from .models import Bank
from .storage import Progress

MASTERY_STREAK = 2  # correct answers in a row before a question counts as mastered


@dataclass(frozen=True)
class TopicStat:
    topic: str
    questions: int  # questions carrying this topic
    seen: int  # of those, how many have been attempted at least once
    attempts: int
    correct: int

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.attempts if self.attempts else None


def topic_stats(bank: Bank, progress: Progress) -> list[TopicStat]:
    acc: dict[str, dict[str, int]] = {}
    for q in bank.questions:
        qs = progress.stats_for(q.id)
        for topic in q.topics:
            t = acc.setdefault(topic, {"questions": 0, "seen": 0, "attempts": 0, "correct": 0})
            t["questions"] += 1
            if qs.attempts:
                t["seen"] += 1
                t["attempts"] += qs.attempts
                t["correct"] += qs.correct
    return [TopicStat(topic, **t) for topic, t in sorted(acc.items())]


def weak_topics(bank: Bank, progress: Progress, min_attempts: int = 3) -> list[TopicStat]:
    """Topics with enough data to judge, worst accuracy first."""
    judged = [t for t in topic_stats(bank, progress) if t.attempts >= min_attempts]
    return sorted(judged, key=lambda t: t.accuracy)


def coverage(bank: Bank, progress: Progress) -> tuple[int, int, int]:
    """(attempted, total, mastered) across the bank."""
    seen = mastered = 0
    for q in bank.questions:
        qs = progress.stats_for(q.id)
        if qs.attempts:
            seen += 1
        if qs.streak >= MASTERY_STREAK:
            mastered += 1
    return seen, len(bank), mastered


def overall_accuracy(bank: Bank, progress: Progress) -> float | None:
    attempts = correct = 0
    for q in bank.questions:
        qs = progress.stats_for(q.id)
        attempts += qs.attempts
        correct += qs.correct
    return correct / attempts if attempts else None


def progress_summary_text(bank: Bank, progress: Progress) -> str:
    """Compact per-topic summary fed to the tutor."""
    lines = [
        f"- {t.topic}: {100 * t.accuracy:.0f}% over {t.attempts} attempts"
        for t in topic_stats(bank, progress)
        if t.attempts
    ]
    return "\n".join(lines) or "(no attempts recorded yet)"
