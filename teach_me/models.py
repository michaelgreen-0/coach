from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

T = TypeVar("T")


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T


@dataclass(frozen=True)
class Err:
    message: str


Result = Ok[T] | Err


class Question(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: StrictInt
    question: StrictStr = Field(min_length=1)
    options: tuple[StrictStr, ...] = Field(min_length=2)
    correct: tuple[StrictInt, ...] = Field(min_length=1)  # zero-based option indices
    topics: tuple[StrictStr, ...] = ("General",)
    explanation: StrictStr = ""
    source: StrictStr | None = None
    set_name: StrictStr | None = Field(default=None, alias="set")
    category: StrictStr | None = None

    @field_validator("topics", mode="before")
    @classmethod
    def _default_topics(cls, v: object) -> object:
        return v or ("General",)

    @field_validator("question", mode="after")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v

    @field_validator("correct", mode="after")
    @classmethod
    def _unique_sorted(cls, v: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(v)) != len(v):
            raise ValueError("has duplicate indices")
        return tuple(sorted(v))

    @model_validator(mode="after")
    def _indices_in_range(self) -> Question:
        n = len(self.options)
        if any(i < 0 or i >= n for i in self.correct):
            raise ValueError(f"'correct' has an index outside 0..{n - 1}")
        return self

    @property
    def answer_letters(self) -> tuple[str, ...]:
        return tuple(chr(ord("A") + i) for i in self.correct)

    @property
    def is_multi(self) -> bool:
        return len(self.correct) > 1


class Bank(BaseModel):
    model_config = ConfigDict(frozen=True)

    questions: tuple[Question, ...] = Field(min_length=1)

    # ids key the saved progress, so a collision would corrupt tracking.
    @model_validator(mode="after")
    def _unique_ids(self) -> Bank:
        ids = [q.id for q in self.questions]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate question id(s): {dupes}")
        return self

    def topics(self) -> tuple[str, ...]:
        return tuple(sorted({t for q in self.questions for t in q.topics}))

    def __len__(self) -> int:
        return len(self.questions)


def _format(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"])
        parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return "; ".join(parts)


def parse_question(raw: object) -> Result[Question]:
    try:
        return Ok(Question.model_validate(raw))
    except ValidationError as exc:
        return Err(_format(exc))


def parse_bank(raw: object) -> Result[Bank]:
    if not isinstance(raw, list):
        return Err("bank must be a JSON array of questions")
    try:
        return Ok(Bank(questions=raw))
    except ValidationError as exc:
        return Err(_format(exc))
