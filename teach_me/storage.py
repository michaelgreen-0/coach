import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .models import Bank, Err, Ok, Result, _format, parse_bank


def load_bank(path: Path) -> Result[Bank]:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return Err(f"question bank not found: {path}")
    except json.JSONDecodeError as exc:
        return Err(f"{path}: invalid JSON ({exc})")
    return parse_bank(raw)


class QuestionProgress(BaseModel):
    attempts: int = 0
    correct: int = 0
    streak: int = 0  # consecutive result run: positive = correct, negative = wrong
    last_result: bool | None = None
    last_seen: str | None = None


class Session(BaseModel):
    date: str
    asked: int
    correct: int


class Progress(BaseModel):
    questions: dict[str, QuestionProgress] = {}
    sessions: list[Session] = []

    def stats_for(self, qid: int) -> QuestionProgress:
        """The recorded stats for a question, or a fresh zeroed default.

        The default is not stored — reading an unseen question leaves the
        progress untouched.
        """
        return self.questions.get(str(qid), QuestionProgress())


def load_progress(path: Path) -> Result[Progress]:
    if not path.exists():
        return Ok(Progress())
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return Err(f"{path}: invalid JSON ({exc})")
    try:
        return Ok(Progress.model_validate(raw))
    except ValidationError as exc:
        return Err(_format(exc))


def save_progress(progress: Progress, path: Path) -> Result[None]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(progress.model_dump_json(indent=2))
    except OSError as exc:
        return Err(f"could not save progress to {path}: {exc}")
    return Ok(None)
