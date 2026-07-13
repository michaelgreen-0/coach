import os

from openai import OpenAI

from .config import TutorConfig
from .models import Question

_BASE_SYSTEM = """You are {persona}, helping a student study {subject}.

Explain concepts clearly and concretely. Keep replies focused and readable in a
terminal — no markdown tables. If asked something unrelated, gently steer back
to studying.
{guidelines}"""

_QUESTION_REVEAL = """

The student is looking at this practice question:

QUESTION:
{question}

OPTIONS:
{options}

CORRECT ANSWER(S): {answer}

EXPLANATION: {explanation}

The student {result}. Help them genuinely understand it."""

_QUESTION_HINT = """

The student is stuck on this practice question and has NOT answered yet:

QUESTION:
{question}

OPTIONS:
{options}

Give hints and nudge their thinking. Do NOT reveal which option is correct."""

_PROGRESS = """

For context, the student's recent accuracy by topic (use it to tailor advice):
{summary}"""


def _is_local(base_url: str) -> bool:
    return "localhost" in base_url or "127.0.0.1" in base_url


def tutor_available(cfg: TutorConfig) -> bool:
    """The tutor needs a key, unless it points at a local (keyless) endpoint."""
    return bool(os.environ.get(cfg.api_key_env)) or _is_local(cfg.base_url)


def _lettered(options: tuple[str, ...]) -> str:
    return "\n".join(f"{chr(ord('A') + i)}. {opt}" for i, opt in enumerate(options))


class Tutor:
    """One streaming conversation. Create a fresh instance per question/session."""

    def __init__(self, cfg: TutorConfig, subject: str, question: Question | None = None,
                 result: str | None = None, progress_summary: str | None = None,
                 reveal_answer: bool = True):
        self.client = OpenAI(
            api_key=os.environ.get(cfg.api_key_env) or "no-key-needed",
            base_url=cfg.base_url,
        )
        self.model = cfg.model
        self.history: list[dict] = []
        self.system = _BASE_SYSTEM.format(
            persona=cfg.persona, subject=subject, guidelines=cfg.guidelines
        )
        if question is not None:
            template = _QUESTION_REVEAL if reveal_answer else _QUESTION_HINT
            self.system += template.format(
                question=question.question,
                options=_lettered(question.options),
                answer=", ".join(question.answer_letters),
                explanation=question.explanation or "(none provided)",
                result=result or "is reviewing this question",
            )
        if progress_summary:
            self.system += _PROGRESS.format(summary=progress_summary)

    def ask(self, message: str) -> str:
        """Send a message, stream the reply to stdout, and return the full text."""
        self.history.append({"role": "user", "content": message})
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": self.system}, *self.history],
            stream=True,
        )
        parts = []
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="", flush=True)
                parts.append(delta)
        print()
        reply = "".join(parts)
        self.history.append({"role": "assistant", "content": reply})
        return reply
