from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    password: str
    invite: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class QuizRequest(BaseModel):
    mode: str
    topic: str | None = None
    set: str | None = None
    subject: str | None = None


class AnswerRequest(BaseModel):
    id: int
    answer: str  # option letters, e.g. "a" or "ac" for multi-answer
    subject: str | None = None


class SessionRequest(BaseModel):
    asked: int
    correct: int
    subject: str | None = None


class TutorRequest(BaseModel):
    message: str
    history: list[dict] = []
    question_id: int | None = None
    stage: str = "chat"  # "hint" before answering, "reveal" after, "chat" from the menu
    correct: bool | None = None
    picked: str = ""  # letters the student chose, for the post-answer context
    set: str | None = None
    subject: str | None = None
