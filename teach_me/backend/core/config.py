import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from .models import Err, Ok, Result, _format

BUNDLED_CONFIG = Path(__file__).resolve().parents[3] / "examples" / "teach-me.toml"


class TutorConfig(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    model: str
    base_url: str
    api_key_env: str = "OPENAI_API_KEY"
    persona: str = "a friendly, encouraging quiz tutor"
    guidelines: str = ""


class LimitsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    # per signed-in user; the tutor cap is what protects your LLM bill
    requests_per_minute: int = 120
    tutor_per_day: int = 50


class _RawSubject(BaseModel):
    name: str
    bank: str


class _RawConfig(BaseModel):
    # a plain string is the single-subject shorthand; [[subject]] tables are
    # the full form (TOML forbids mixing the two under one key)
    subject: str | list[_RawSubject] | None = None
    bank: str | None = None
    data_dir: str = "data"
    tutor: TutorConfig | None = None
    limits: LimitsConfig = LimitsConfig()


@dataclass(frozen=True)
class Subject:
    slug: str  # stable id: keys the API and the progress file name
    name: str
    bank_path: Path  # absolute; resolved relative to the config file
    progress_file: str  # file name inside data_dir


@dataclass(frozen=True)
class Config:
    subjects: tuple[Subject, ...]
    data_dir: Path  # for saved progress; relative to the cwd unless absolute
    tutor: TutorConfig | None
    limits: LimitsConfig


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "subject"


def _discover() -> Path:
    local = Path("teach-me.toml")
    return local if local.is_file() else BUNDLED_CONFIG


def _subjects(raw: _RawConfig, base: Path) -> Result[tuple[Subject, ...]]:
    if isinstance(raw.subject, str) or (raw.subject is None and raw.bank is not None):
        if not isinstance(raw.subject, str) or raw.bank is None:
            return Err("a subject and a bank are both required")
        # single-subject configs keep the historical progress.json path
        return Ok((Subject(_slug(raw.subject), raw.subject,
                           (base / raw.bank).resolve(), "progress.json"),))

    if not raw.subject:
        return Err("config needs a subject and bank, or one or more [[subject]] entries")
    if raw.bank is not None:
        return Err("use either top-level subject/bank or [[subject]] entries, not both")

    subjects = tuple(
        Subject(_slug(s.name), s.name, (base / s.bank).resolve(),
                f"progress-{_slug(s.name)}.json")
        for s in raw.subject
    )
    slugs = [s.slug for s in subjects]
    dupes = sorted({s for s in slugs if slugs.count(s) > 1})
    if dupes:
        return Err(f"subject names collide: {', '.join(dupes)}")
    return Ok(subjects)


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

    subjects = _subjects(raw, cfg_path.parent)
    if isinstance(subjects, Err):
        return Err(f"{cfg_path}: {subjects.message}")

    return Ok(Config(
        subjects=subjects.value,
        data_dir=Path(raw.data_dir),
        tutor=raw.tutor,
        limits=raw.limits,
    ))
