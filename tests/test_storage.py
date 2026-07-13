from pathlib import Path

from teach_me.models import Err, Ok
from teach_me.storage import (
    Progress,
    QuestionProgress,
    Session,
    load_bank,
    load_progress,
    save_progress,
)

SAMPLE_BANK = Path(__file__).resolve().parent.parent / "examples" / "sample-bank.json"


def test_load_bank_ok():
    result = load_bank(SAMPLE_BANK)
    assert isinstance(result, Ok)
    assert len(result.value) == 10


def test_load_bank_missing_is_err(tmp_path: Path):
    assert isinstance(load_bank(tmp_path / "nope.json"), Err)


def test_load_bank_bad_json_is_err(tmp_path: Path):
    bad = tmp_path / "bank.json"
    bad.write_text("{not json")
    assert isinstance(load_bank(bad), Err)


def test_load_progress_missing_returns_empty(tmp_path: Path):
    result = load_progress(tmp_path / "progress.json")
    assert isinstance(result, Ok)
    assert result.value.questions == {}
    assert result.value.sessions == []


def test_progress_round_trip(tmp_path: Path):
    progress = Progress(
        questions={"1": QuestionProgress(attempts=2, correct=1, streak=-1, last_result=False)},
        sessions=[Session(date="2026-07-13T10:00:00+00:00", asked=3, correct=2)],
    )
    path = tmp_path / "sub" / "progress.json"  # parent dir does not exist yet

    assert isinstance(save_progress(progress, path), Ok)
    assert path.is_file()

    loaded = load_progress(path)
    assert isinstance(loaded, Ok)
    assert loaded.value == progress


def test_stats_for_unseen_is_zeroed_and_not_stored():
    progress = Progress()
    stats = progress.stats_for(99)
    assert stats == QuestionProgress()
    assert progress.questions == {}  # reading did not insert


def test_load_progress_corrupt_is_err(tmp_path: Path):
    path = tmp_path / "progress.json"
    path.write_text("{not json")
    assert isinstance(load_progress(path), Err)
