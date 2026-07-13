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


class _RawConfig(BaseModel):
    subject: str
    bank: str
    data_dir: str = "data"
    tutor: TutorConfig | None = None


@dataclass(frozen=True)
class Config:
    subject: str
    bank_path: Path  # absolute; resolved relative to the config file
    data_dir: Path  # for saved progress; relative to the cwd unless absolute
    tutor: TutorConfig | None


def _discover() -> Path:
    local = Path("teach-me.toml")
    return local if local.is_file() else BUNDLED_CONFIG


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

    return Ok(Config(
        subject=raw.subject,
        bank_path=(cfg_path.parent / raw.bank).resolve(),
        data_dir=Path(raw.data_dir),
        tutor=raw.tutor,
    ))
