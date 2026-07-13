from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import analytics
from .models import Bank
from .storage import Progress

_BAR_WIDTH = 20


def _accuracy_bar(accuracy: float) -> Text:
    filled = round(accuracy * _BAR_WIDTH)
    color = "green" if accuracy >= 0.8 else "yellow" if accuracy >= 0.6 else "red"
    return Text("█" * filled + "░" * (_BAR_WIDTH - filled), style=color)


def show_dashboard(console: Console, bank: Bank, progress: Progress) -> None:
    stats = analytics.topic_stats(bank, progress)

    table = Table(title="Performance by Topic")
    table.add_column("Topic", style="cyan")
    table.add_column("Coverage", justify="right")
    table.add_column("Attempts", justify="right")
    table.add_column("Accuracy", justify="right")
    table.add_column("")

    # Attempted topics first, weakest at the top; untouched topics sink.
    for t in sorted(stats, key=lambda t: (t.accuracy is None, t.accuracy or 0)):
        if t.accuracy is None:
            bar, acc = Text("░" * _BAR_WIDTH, style="dim"), "—"
        else:
            bar, acc = _accuracy_bar(t.accuracy), f"{100 * t.accuracy:.0f}%"
        table.add_row(t.topic, f"{t.seen}/{t.questions}", str(t.attempts), acc, bar)
    console.print(table)

    seen, total, mastered = analytics.coverage(bank, progress)
    console.print(f"\nBank coverage: [bold]{seen}/{total}[/bold] attempted, "
                  f"[bold green]{mastered}[/bold green] mastered "
                  f"(answered correctly twice in a row)")

    worst = [f"{t.topic} ({100 * t.accuracy:.0f}%)"
             for t in analytics.weak_topics(bank, progress)[:3] if t.accuracy < 0.8]
    if worst:
        console.print(f"[bold red]Focus areas:[/bold red] {', '.join(worst)}")

    overall = analytics.overall_accuracy(bank, progress)
    if overall is not None:
        verdict = ("looking strong — aim to keep it above 80%" if overall >= 0.8
                   else "getting there — target 80%+" if overall >= 0.65
                   else "keep drilling — target 80%+")
        console.print(f"Overall accuracy: [bold]{100 * overall:.0f}%[/bold] — {verdict}")
    console.print()
