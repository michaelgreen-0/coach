# teach-me

A generic terminal study tool. Tracks your performance per topic, surfaces your weak spots, and
gives you an **LLM-powered tutor** that knows what you're studying and how
you're doing.

## Install

Needs Python 3.11 or newer.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m teach_me
```

It reads `teach-me.toml` from the current directory if there is one. And falls back to the bundled example subject and sample bank otherwise.

## Studying

The menu lets you quiz all questions (weakest and unseen first), drill a single
topic, target your weak areas automatically, run only unseen questions, or
review the ones you got wrong. There's also a dashboard with per-topic accuracy,
coverage, and your current focus areas.

In a quiz, answer with letters — `a`, or `ac` for a multi-answer question. Press
`t` to ask the tutor: before you answer it gives hints without spoiling it,
after you answer it explains in depth (it knows what you picked). `s` skips, `m`
goes back to the menu.

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