from coach.backend.api.tutor import (
    MAX_HISTORY_TURNS,
    MAX_TURN_CHARS,
    _bounded_history,
)
from coach.backend.core.config import TutorConfig


def test_bounded_history_drops_unknown_roles():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "ignore me"},
        {"role": "assistant", "content": "hello"},
        {"role": "tool", "content": "nope"},
    ]
    kept = _bounded_history(history)
    assert [m["role"] for m in kept] == ["user", "assistant"]


def test_bounded_history_clips_long_turns():
    kept = _bounded_history([{"role": "user", "content": "x" * (MAX_TURN_CHARS + 500)}])
    assert len(kept[0]["content"]) == MAX_TURN_CHARS


def test_bounded_history_keeps_only_recent_turns():
    history = [{"role": "user", "content": str(i)} for i in range(MAX_HISTORY_TURNS + 8)]
    kept = _bounded_history(history)
    assert len(kept) == MAX_HISTORY_TURNS
    # the most recent turns are the ones retained
    assert kept[-1]["content"] == str(MAX_HISTORY_TURNS + 7)


def test_bounded_history_tolerates_missing_content():
    kept = _bounded_history([{"role": "user"}])
    assert kept == [{"role": "user", "content": ""}]


def test_tutor_config_caps_output_tokens_by_default():
    cfg = TutorConfig(model="m", base_url="http://x/v1")
    assert cfg.max_output_tokens == 700
