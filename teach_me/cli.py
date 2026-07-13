import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import analytics, dashboard, quiz, tutor
from .config import Config, TutorConfig, load_config
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


def _tutor_chat(tutor_cfg: TutorConfig, subject: str, summary: str,
                question: Question | None = None, result: str | None = None,
                reveal_answer: bool = True) -> None:
    try:
        session = tutor.Tutor(tutor_cfg, subject, question=question, result=result,
                              progress_summary=summary, reveal_answer=reveal_answer)
    except Exception as exc:  # constructing the client can fail (bad base_url, etc.)
        console.print(f"[red]Could not start tutor: {exc}[/red]")
        return
    console.print("[dim]Tutor — type a question, or 'back' to return.[/dim]")
    while True:
        try:
            msg = console.input("[bold magenta]you ›[/bold magenta] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg:
            continue
        if msg.lower() in ("back", "exit", "quit", "q"):
            break
        console.print("[bold green]tutor ›[/bold green] ", end="")
        try:
            session.ask(msg)
        except Exception as exc:  # network / API errors mid-chat are recoverable
            console.print(f"\n[red]Tutor error: {exc}[/red]")
        console.print()


def _save(progress: Progress, path: Path) -> None:
    result = save_progress(progress, path)
    if isinstance(result, Err):
        console.print(f"[red]Warning: {result.message}[/red]")


def _finish_session(progress: Progress, path: Path, asked: int, correct: int) -> None:
    if not asked:
        return
    quiz.record_session(progress, asked, correct)
    _save(progress, path)
    console.print(f"\n[bold]Session: {correct}/{asked} correct "
                  f"({100 * correct / asked:.0f}%)[/bold]\n")


def _run_quiz(cfg: Config, bank: Bank, progress: Progress, path: Path, mode: str,
              topic: str | None = None, tutor_on: bool = False) -> None:
    pool = quiz.pick_questions(bank, progress, mode, topic)
    if not pool:
        console.print("[yellow]No questions match that selection.[/yellow]")
        return
    summary = analytics.progress_summary_text(bank, progress)
    hint = ", 't' tutor" if tutor_on else ""

    asked = correct_count = 0
    for index, q in enumerate(pool, 1):
        console.clear()
        _render_question(q, index, len(pool))

        answer = None
        while answer is None:
            raw = console.input(f"[bold]Your answer[/bold] (letters{hint}, 's' skip, 'm' menu): ")
            low = raw.strip().lower()
            if low == "m":
                _finish_session(progress, path, asked, correct_count)
                return
            if low == "s":
                break
            if low == "t" and tutor_on:
                _tutor_chat(cfg.tutor, cfg.subject, summary, question=q,
                            result="has not answered yet", reveal_answer=False)
                _render_question(q, index, len(pool))
                continue
            result = quiz.parse_answer(raw, len(q.options))
            if isinstance(result, Ok):
                answer = result.value
            else:
                console.print(f"[red]{result.message}[/red]")
        if answer is None:  # skipped
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

        if _after_answer(cfg, summary, q, answer, correct, tutor_on):
            _finish_session(progress, path, asked, correct_count)
            return

    _finish_session(progress, path, asked, correct_count)


def _after_answer(cfg: Config, summary: str, q: Question, answer: frozenset[int],
                  correct: bool, tutor_on: bool) -> bool:
    """Returns True if the student asked to return to the menu."""
    prompt = "[dim][Enter] next" + ("  •  't' tutor" if tutor_on else "") + "  •  'm' menu[/dim] "
    while True:
        nxt = console.input(prompt).strip().lower()
        if nxt == "t" and tutor_on:
            picked = ", ".join(chr(ord("A") + i) for i in sorted(answer))
            result = "answered correctly" if correct else f"answered incorrectly (picked {picked})"
            _tutor_chat(cfg.tutor, cfg.subject, summary, question=q, result=result)
        elif nxt == "m":
            return True
        else:
            return False


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


def _menu(subject: str, count: int, set_label: str | None, has_sets: bool, tutor_on: bool) -> None:
    where = f" — {set_label}" if set_label else ""
    console.print(f"\n[bold]{subject}[/bold]{where} — {count} questions\n")
    console.print("  [cyan]1[/cyan]. Quiz — all questions (weakest first)")
    console.print("  [cyan]2[/cyan]. Quiz — pick a topic")
    console.print("  [cyan]3[/cyan]. Quiz — my weak areas")
    console.print("  [cyan]4[/cyan]. Quiz — unseen questions")
    console.print("  [cyan]5[/cyan]. Review — questions I got wrong")
    console.print("  [cyan]6[/cyan]. Progress dashboard")
    if tutor_on:
        console.print("  [cyan]7[/cyan]. Talk to the tutor")
    if has_sets:
        console.print("  [cyan]s[/cyan]. Switch question set")
    console.print("  [cyan]q[/cyan]. Quit")


def main() -> None:
    cfg_result = load_config()
    if isinstance(cfg_result, Err):
        console.print(f"[red]{cfg_result.message}[/red]")
        sys.exit(1)
    cfg = cfg_result.value

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

    tutor_on = cfg.tutor is not None and tutor.tutor_available(cfg.tutor)
    if cfg.tutor is not None and not tutor_on:
        console.print(f"[yellow]Tutor disabled — set ${cfg.tutor.api_key_env} to enable it.[/yellow]")
    has_sets = bool(_bank_sets(full_bank))
    active_set: str | None = None

    while True:
        bank = _filtered_bank(full_bank, active_set)
        _menu(cfg.subject, len(bank), active_set if has_sets else None, has_sets, tutor_on)
        choice = console.input("[bold]Choose:[/bold] ").strip().lower()

        if choice == "1":
            _run_quiz(cfg, bank, progress, progress_path, "all", tutor_on=tutor_on)
        elif choice == "2":
            topic = _choose_topic(bank)
            if topic:
                _run_quiz(cfg, bank, progress, progress_path, "topic", topic, tutor_on=tutor_on)
        elif choice == "3":
            weak = analytics.weak_topics(bank, progress)[:3]
            if weak:
                console.print(f"[cyan]Focusing on: {', '.join(t.topic for t in weak)}[/cyan]")
            else:
                console.print("[yellow]Not enough data yet — using the whole bank.[/yellow]")
            _run_quiz(cfg, bank, progress, progress_path, "weak", tutor_on=tutor_on)
        elif choice == "4":
            _run_quiz(cfg, bank, progress, progress_path, "unseen", tutor_on=tutor_on)
        elif choice == "5":
            _run_quiz(cfg, bank, progress, progress_path, "missed", tutor_on=tutor_on)
        elif choice == "6":
            dashboard.show_dashboard(console, bank, progress)
        elif choice == "7" and tutor_on:
            summary = analytics.progress_summary_text(bank, progress)
            _tutor_chat(cfg.tutor, cfg.subject, summary)
        elif choice == "s" and has_sets:
            active_set = _choose_set(full_bank, active_set)
        elif choice in ("q", "quit", "exit"):
            break
