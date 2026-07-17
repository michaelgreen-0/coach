# Architecture

Two thin front ends — a terminal UI and a web UI — over one shared core. The
core modules are pure: they take a `Bank` and a `Progress`, return data, and
report expected failures as `Ok`/`Err` results rather than exceptions.

```mermaid
graph TD
    subgraph Front ends
        CLI["cli.py + dashboard.py<br/>(rich, interactive)"]
        WEB["web.py<br/>(FastAPI, JSON API)"]
        STATIC["static/<br/>index.html · style.css · app.js"]
    end

    subgraph Core
        QUIZ["quiz.py<br/>ordering · grading · recording"]
        ANALYTICS["analytics.py<br/>topic stats · coverage · weak areas"]
        TUTOR["tutor.py<br/>streaming LLM chat"]
        MODELS["models.py<br/>Question · Bank · Result"]
        STORAGE["storage.py<br/>bank + progress JSON I/O"]
        CONFIG["config.py<br/>teach-me.toml"]
    end

    STATIC -->|fetch| WEB
    CLI --> QUIZ & ANALYTICS & TUTOR & CONFIG & STORAGE
    WEB --> QUIZ & ANALYTICS & TUTOR & CONFIG & STORAGE
    QUIZ --> MODELS
    ANALYTICS --> MODELS
    STORAGE --> MODELS
    TUTOR -->|OpenAI-compatible API| LLM[(any LLM provider)]
    STORAGE --> DISK[("data/progress.json")]
```

## The web layer

`web.py` exposes the CLI's flows one-to-one:

| Endpoint | CLI equivalent |
| --- | --- |
| `GET /api/auth`, `POST /api/register` / `login` / `logout` | (web only — accounts) |
| `GET /api/chapters` | the chapter picker shown at startup |
| `GET /api/state` | the main menu header (subject, sets, topics, tutor availability) |
| `POST /api/quiz` | `pick_questions` — modes `all`, `topic`, `weak`, `unseen`, `missed` |
| `POST /api/answer` | answer parsing, grading, `record_result`, save |
| `POST /api/session` | `record_session` on quiz end / return to menu |
| `GET /api/dashboard` | the progress dashboard |
| `POST /api/tutor` | the tutor chat (streamed as plain text) |

Design decisions:

- **Answers stay server-side.** `POST /api/quiz` strips `correct` and
  `explanation`; they only come back from `POST /api/answer` after the student
  commits. `select_n` is included for multi-answer questions because the CLI
  also tells you how many to pick.
- **Grading reuses `quiz.parse_answer`.** The browser sends the chosen letters
  as a string, so validation and error messages match the terminal exactly.
- **The tutor is stateless per request.** The browser keeps the chat history
  and sends it with each turn; the server rebuilds the system prompt (question
  context, hint vs. reveal stage, progress summary) and streams the reply.
- **Accounts are web-only.** `auth.py` stores scrypt-hashed passwords in
  `data/users.json` and opaque session tokens (30-day TTL, persisted so
  restarts don't sign anyone out) in `data/sessions.json`. The session rides an
  `httponly` `samesite=lax` cookie; every study endpoint requires it. An
  optional `TEACH_ME_INVITE_CODE` env var gates registration. The CLI stays
  local and unauthenticated.
- **One `Progress` per (user, chapter) in memory, one lock.** Banks are loaded
  at startup; each user's progress loads lazily into a cache keyed by
  `(username, chapter)` and saves to `data/progress/<username>/` after every
  answer, mirroring the CLI's save-after-every-answer behaviour. Usernames are
  validated (`^[a-z0-9][a-z0-9-]{2,31}$`), so they are safe as directory
  names.

The front end (`teach_me/static/`) is a single page of hand-written HTML, CSS
and vanilla JS — no build step. `app.js` is a small state machine over the
views (menu, topic picker, quiz, session summary, dashboard, tutor) and mirrors
the CLI's keyboard shortcuts.
