# coach

Study tool that tracks your performance per topic, surfaces your weak spots, and gives you an LLM-powered tutor.

This is deployed to [https://coach.michaelsprojects.dev](https://coach.michaelsprojects.dev/)

Follow on for running this yourself (BYO API key for the tutor)


## Getting Started

Needs Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Run it in the browser:

```bash
uv run python -m coach
# then open http://127.0.0.1:8000
```

It reads `coach.toml` from the current directory if there is one, and falls back to the bundled example subject and sample bank otherwise.

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

## Subjects

A subject is one thing you're studying — a certification, an exam path, a course. Each subject has its own question bank and its own saved progress:

```toml
[[subject]]
name = "AWS Solutions Architect"
bank = "aws-bank.json"

[[subject]]
name = "Networking 101"
bank = "net-bank.json"

[tutor]              # shared by all subjects
model    = "claude-sonnet-5"
base_url = "https://api.anthropic.com/v1/"
```

A config with a single top-level `subject = "..."`/`bank = "..."` pair still
works and is the same as one subject (and keeps its progress in
`data/progress.json`; subjects save to `data/progress-<subject>.json`).

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

Save the result as your bank, point `coach.toml` at it, and you're off. Mistakes have happened for me though so always double check.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
