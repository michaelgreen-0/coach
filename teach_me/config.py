import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from .models import Err, Ok, Result, _format

BUNDLED_CONFIG = Path(__file__).resolve().parent.parent / "examples" / "teach-me.toml"


class TutorConfig(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    model: str
    base_url: str
    api_key_env: str = "OPENAI_API_KEY"
    persona: str = "a friendly, encouraging quiz tutor"
    guidelines: str = ""


class _RawChapter(BaseModel):
    subject: str
    bank: str


class _RawConfig(BaseModel):
    subject: str | None = None
    bank: str | None = None
    chapter: list[_RawChapter] = []
    data_dir: str = "data"
    tutor: TutorConfig | None = None


@dataclass(frozen=True)
class Chapter:
    slug: str  # stable id: keys the API and the progress file name
    subject: str
    bank_path: Path  # absolute; resolved relative to the config file
    progress_file: str  # file name inside data_dir


@dataclass(frozen=True)
class Config:
    chapters: tuple[Chapter, ...]
    data_dir: Path  # for saved progress; relative to the cwd unless absolute
    tutor: TutorConfig | None


def _slug(subject: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-") or "chapter"


def _discover() -> Path:
    local = Path("teach-me.toml")
    return local if local.is_file() else BUNDLED_CONFIG


def _chapters(raw: _RawConfig, base: Path) -> Result[tuple[Chapter, ...]]:
    legacy = raw.subject is not None or raw.bank is not None
    if legacy and raw.chapter:
        return Err("use either top-level subject/bank or [[chapter]] entries, not both")

    if legacy:
        if raw.subject is None or raw.bank is None:
            return Err("a subject and a bank are both required")
        # single-chapter configs keep the historical progress.json path
        return Ok((Chapter(_slug(raw.subject), raw.subject,
                           (base / raw.bank).resolve(), "progress.json"),))

    if not raw.chapter:
        return Err("config needs a subject and bank, or one or more [[chapter]] entries")

    chapters = tuple(
        Chapter(_slug(c.subject), c.subject, (base / c.bank).resolve(),
                f"progress-{_slug(c.subject)}.json")
        for c in raw.chapter
    )
    slugs = [c.slug for c in chapters]
    dupes = sorted({s for s in slugs if slugs.count(s) > 1})
    if dupes:
        return Err(f"chapter subjects collide: {', '.join(dupes)}")
    return Ok(chapters)


def load_config(path: Path | None = None) -> Result[Config]:
    cfg_path = path or _discover()
    if not cfg_path.is_file():
        return Err(f"config file not found: {cfg_path}")
    try:
        data = tomllib.loads(cfg_path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return Err(f"{cfg_path}: {exc}")
    try:
        raw = _RawConfig.model_validate(data)
    except ValidationError as exc:
        return Err(f"{cfg_path}: {_format(exc)}")

    chapters = _chapters(raw, cfg_path.parent)
    if isinstance(chapters, Err):
        return Err(f"{cfg_path}: {chapters.message}")

    return Ok(Config(
        chapters=chapters.value,
        data_dir=Path(raw.data_dir),
        tutor=raw.tutor,
    ))
