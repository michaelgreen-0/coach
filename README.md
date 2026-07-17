# teach-me

A generic study tool with a terminal UI and a web UI. Tracks your performance per topic, surfaces your weak spots, and
gives you an **LLM-powered tutor** that knows what you're studying and how
you're doing.

## Install

Needs Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Run

In the terminal:

```bash
uv run python -m teach_me
```

Or in the browser:

```bash
uv run python -m teach_me.web
# then open http://127.0.0.1:8000
```

Both read `teach-me.toml` from the current directory if there is one, and fall back to the bundled example subject and sample bank otherwise.

To serve the web app to other machines (e.g. for deployment), bind uvicorn yourself:

```bash
uv run uvicorn --factory 'teach_me.web:create_app' --host 0.0.0.0 --port 8000
```

## Accounts (web only)

The web app asks you to sign in; each account keeps its own progress under
`data/progress/<username>/`. Accounts are simple username + password
(scrypt-hashed, stored in `data/users.json`); sessions are 30-day cookies that
survive server restarts.

Registration is open by default. To keep a deployed instance to your friends,
set an invite code — signups then require it:

```bash
TEACH_ME_INVITE_CODE=sesame uv run uvicorn --factory 'teach_me.web:create_app' --host 0.0.0.0
```

Put the app behind HTTPS in production (a reverse proxy like Caddy is the easy
way) — the password and session cookie travel in plain text otherwise.

The terminal UI has no accounts: it's local, and keeps using
`data/progress*.json` directly, separate from web users' progress.

## Studying

If your config has more than one **chapter** (see below), you first pick what
you're studying. Then the menu lets you quiz all questions (weakest and unseen
first), drill a single topic, target your weak areas automatically, run only
unseen questions, or review the ones you got wrong. There's also a dashboard
with per-topic accuracy, coverage, and your current focus areas.

In a quiz, answer with letters — `a`, or `ac` for a multi-answer question. Press
`t` to ask the tutor: before you answer it gives hints without spoiling it,
after you answer it explains in depth (it knows what you picked). `s` skips, `m`
goes back to the menu.

The web UI has the same flows and the same keyboard shortcuts (letters to
select, `Enter` to check, `s`/`m`/`t`, number keys on the menu). Answers are
graded server-side, so the browser never sees the correct option before you
commit.

Progress is saved to `data/progress.json` after every answer, and a question is
"mastered" once you get it right twice in a row.

## The tutor works with any LLM

The tutor uses an OpenAI-compatible client, so you can point it at whatever provider you have a key for. Configure it in your subject's TOML file:

```toml
[tutor]
model       = "gpt-4o"
base_url    = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"      # name of the env var holding your key
```

Any provider that speaks the OpenAI API works. I personally have had success using Sonnet. This brings a good balance of accuracy and speed of response.

```toml
# Claude, directly (Anthropic's OpenAI-compatible endpoint; keep the trailing slash)
model       = "claude-sonnet-5"
base_url    = "https://api.anthropic.com/v1/"
api_key_env = "ANTHROPIC_API_KEY"

# A local model via Ollama (no key needed)
model       = "llama3"
base_url    = "http://localhost:11434/v1"
```

Copy .env.default to .env. Then paste in your api key as above (OPENAI_API_KEY, or ANTHROPIC_API_KEY etc ...)

```bash
cp .env.default .env    # then edit .env and paste your key
```

Alternatively, you can export the key

```bash
export OPENAI_API_KEY=...
```

BTW The quiz works without any key. Only the tutor needs one.

## Chapters

A chapter is one thing you're studying — a certification, an exam path, a
course. Each chapter has its own question bank and its own saved progress:

```toml
[[chapter]]
subject = "AWS Solutions Architect"
bank    = "aws-bank.json"

[[chapter]]
subject = "Networking 101"
bank    = "net-bank.json"

[tutor]              # shared by all chapters
model    = "claude-sonnet-5"
base_url = "https://api.anthropic.com/v1/"
```

A config with a single top-level `subject`/`bank` pair still works and is the
same as one chapter (and keeps its progress in `data/progress.json`; chapters
save to `data/progress-<chapter>.json`).

## Bring your own bank

A question bank is a JSON array. Each question declares its own topics, so the tool never needs to know your subject:

```json
[
  {
    "id": 1,
    "question": "Which planet is known as the Red Planet?",
    "options": ["Venus", "Mars", "Jupiter", "Saturn"],
    "correct": [1],
    "explanation": "Mars looks red because of iron oxide (rust) on its surface.",
    "topics": ["Astronomy"]
  }
]
```

- `correct` holds zero-based indices into `options` (a list, so multi-answer
  questions just list several).
- `topics` drives the per-topic stats and weak-area targeting.
- Optional `source`, `set`, and `category` fields are carried through. If your
  questions use `set` (e.g. separate practice exams), the menu gains a switcher
  to study one set at a time.
- See [`examples/`](examples/) for a complete sample bank and config.

### Let an AI write the bank for you

I prefer to use an LLM to generate the JSON bank. You can use a prompt like the following:

> Here is a JSON question-bank format: `<paste the example above>`.
> Using the attached notes on <your subject>, write 30 exam-style questions in
> exactly this format. Mix single- and multi-answer questions, give each a
> concise `explanation`, and tag each with 1–3 `topics`. Return only the JSON.

Save the result as your bank, point `teach-me.toml` at it, and you're studying.
Skim a few entries for accuracy first — models occasionally get facts or the
`correct` indices wrong.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).