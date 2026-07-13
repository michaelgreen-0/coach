import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import analytics, dashboard, quiz
from .config import Config, load_config
from .models import Bank, Err, Ok, Question
from .storage import Progress, load_bank, load_progress, save_progress

console = Console()


def _bank_sets(bank: Bank) -> list[str]:
    return sorted({q.set_name for q in bank.questions if q.set_name})


def _filtered_bank(bank: Bank, active_set: str | None) -> Bank:
    if active_set is None:
        return bank
    return Bank(questions=tuple(q for q in bank.questions if q.set_name == active_set))


def _render_question(q: Question, index: int, total: int) -> None:
    header = f"Question {index}/{total}  (#{q.id})  •  {' / '.join(q.topics)}"
    body = Text(q.question + "\n\n")
    for i, opt in enumerate(q.options):
        body.append(f"  {chr(ord('A') + i)}. ", style="bold cyan")
        body.append(opt + "\n")
    if q.is_multi:
        body.append(f"\n(Select {len(q.correct)} answers, e.g. 'AC')", style="italic yellow")
    console.print(Panel(body, title=header, border_style="blue"))


def _finish_session(progress: Progress, path: Path, asked: int, correct: int) -> None:
    if not asked:
        return
    quiz.record_session(progress, asked, correct)
    _save(progress, path)
    console.print(f"\n[bold]Session: {correct}/{asked} correct "
                  f"({100 * correct / asked:.0f}%)[/bold]\n")


def _save(progress: Progress, path: Path) -> None:
    result = save_progress(progress, path)
    if isinstance(result, Err):
        console.print(f"[red]Warning: {result.message}[/red]")


def _run_quiz(bank: Bank, progress: Progress, path: Path, mode: str,
              topic: str | None = None) -> None:
    pool = quiz.pick_questions(bank, progress, mode, topic)
    if not pool:
        console.print("[yellow]No questions match that selection.[/yellow]")
        return

    asked = correct_count = 0
    for index, q in enumerate(pool, 1):
        console.clear()
        _render_question(q, index, len(pool))

        answer = _prompt_answer(q)
        if answer is _MENU:
            _finish_session(progress, path, asked, correct_count)
            return
        if answer is _SKIP:
            continue

        correct = quiz.is_correct(q, answer)
        asked += 1
        correct_count += correct
        quiz.record_result(progress, q.id, correct)
        _save(progress, path)

        letters = ", ".join(q.answer_letters)
        if correct:
            console.print(f"\n[bold green]✓ Correct![/bold green] ({letters})")
        else:
            console.print(f"\n[bold red]✗ Incorrect.[/bold red] Correct answer: [bold]{letters}[/bold]")
        if q.explanation:
            console.print(Panel(q.explanation, title="Explanation", border_style="yellow"))

        if console.input("[dim][Enter] next  •  'm' menu[/dim] ").strip().lower() == "m":
            _finish_session(progress, path, asked, correct_count)
            return

    _finish_session(progress, path, asked, correct_count)


_SKIP = object()
_MENU = object()


def _prompt_answer(q: Question):
    while True:
        raw = console.input("[bold]Your answer[/bold] (letters, 's' skip, 'm' menu): ").strip()
        low = raw.lower()
        if low == "m":
            return _MENU
        if low == "s":
            return _SKIP
        result = quiz.parse_answer(raw, len(q.options))
        if isinstance(result, Ok):
            return result.value
        console.print(f"[red]{result.message}[/red]")


def _choose_topic(bank: Bank) -> str | None:
    topics = bank.topics()
    for i, t in enumerate(topics, 1):
        n = sum(1 for q in bank.questions if t in q.topics)
        console.print(f"  [cyan]{i:2}[/cyan]. {t} ({n} questions)")
    raw = console.input("Topic number (or Enter to cancel): ").strip()
    return topics[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(topics) else None


def _choose_set(bank: Bank, current: str | None) -> str | None:
    options: list[str | None] = [None, *_bank_sets(bank)]
    console.print()
    for i, key in enumerate(options, 1):
        label = "All sets" if key is None else key
        n = len(_filtered_bank(bank, key))
        marker = " [green]← current[/green]" if key == current else ""
        console.print(f"  [cyan]{i}[/cyan]. {label} ({n} questions){marker}")
    raw = console.input("Set number (or Enter to keep current): ").strip()
    return options[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(options) else current


def _menu(subject: str, count: int, set_label: str | None, has_sets: bool) -> None:
    where = f" — {set_label}" if set_label else ""
    console.print(f"\n[bold]{subject}[/bold]{where} — {count} questions\n")
    console.print("  [cyan]1[/cyan]. Quiz — all questions (weakest first)")
    console.print("  [cyan]2[/cyan]. Quiz — pick a topic")
    console.print("  [cyan]3[/cyan]. Quiz — my weak areas")
    console.print("  [cyan]4[/cyan]. Quiz — unseen questions")
    console.print("  [cyan]5[/cyan]. Review — questions I got wrong")
    console.print("  [cyan]6[/cyan]. Progress dashboard")
    if has_sets:
        console.print("  [cyan]7[/cyan]. Switch question set")
    console.print("  [cyan]q[/cyan]. Quit")


def _load_everything() -> Config | None:
    cfg_result = load_config()
    if isinstance(cfg_result, Err):
        console.print(f"[red]{cfg_result.message}[/red]")
        return None
    return cfg_result.value


def main() -> None:
    cfg = _load_everything()
    if cfg is None:
        sys.exit(1)

    bank_result = load_bank(cfg.bank_path)
    if isinstance(bank_result, Err):
        console.print(f"[red]{bank_result.message}[/red]")
        sys.exit(1)
    full_bank = bank_result.value

    progress_path = cfg.data_dir / "progress.json"
    progress_result = load_progress(progress_path)
    if isinstance(progress_result, Err):
        console.print(f"[red]Could not read progress: {progress_result.message}[/red]")
        sys.exit(1)
    progress = progress_result.value

    has_sets = bool(_bank_sets(full_bank))
    active_set: str | None = None

    while True:
        bank = _filtered_bank(full_bank, active_set)
        _menu(cfg.subject, len(bank), active_set if has_sets else None, has_sets)
        choice = console.input("[bold]Choose:[/bold] ").strip().lower()

        if choice == "1":
            _run_quiz(bank, progress, progress_path, "all")
        elif choice == "2":
            topic = _choose_topic(bank)
            if topic:
                _run_quiz(bank, progress, progress_path, "topic", topic)
        elif choice == "3":
            weak = analytics.weak_topics(bank, progress)[:3]
            if weak:
                console.print(f"[cyan]Focusing on: {', '.join(t.topic for t in weak)}[/cyan]")
            else:
                console.print("[yellow]Not enough data yet — using the whole bank.[/yellow]")
            _run_quiz(bank, progress, progress_path, "weak")
        elif choice == "4":
            _run_quiz(bank, progress, progress_path, "unseen")
        elif choice == "5":
            _run_quiz(bank, progress, progress_path, "missed")
        elif choice == "6":
            dashboard.show_dashboard(console, bank, progress)
        elif choice == "7" and has_sets:
            active_set = _choose_set(full_bank, active_set)
        elif choice in ("q", "quit", "exit"):
            break
