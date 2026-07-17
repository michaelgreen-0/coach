from pathlib import Path

from teach_me.config import BUNDLED_CONFIG, load_config
from teach_me.models import Err, Ok

BANK_JSON = '[{"id":1,"question":"q","options":["a","b"],"correct":[0],"topics":["T"]}]'


def test_load_bundled_config():
    result = load_config(BUNDLED_CONFIG)
    assert isinstance(result, Ok)
    cfg = result.value
    assert [c.subject for c in cfg.chapters] == ["General Knowledge", "Python Basics"]
    for chapter in cfg.chapters:
        assert chapter.bank_path.is_file()
    assert cfg.tutor is not None
    assert cfg.tutor.model == "claude-sonnet-5"


def test_legacy_single_subject_config(tmp_path: Path):
    (tmp_path / "bank.json").write_text(BANK_JSON)
    cfg_file = tmp_path / "teach-me.toml"
    cfg_file.write_text('subject = "Sub"\nbank = "bank.json"\n')

    result = load_config(cfg_file)
    assert isinstance(result, Ok)
    (chapter,) = result.value.chapters
    assert chapter.subject == "Sub"
    assert chapter.bank_path == (tmp_path / "bank.json").resolve()
    # legacy configs keep the historical progress path
    assert chapter.progress_file == "progress.json"
    assert result.value.data_dir == Path("data")  # default


def test_chapter_config(tmp_path: Path):
    cfg_file = tmp_path / "teach-me.toml"
    cfg_file.write_text(
        '[[chapter]]\nsubject = "AWS SAA"\nbank = "aws.json"\n'
        '[[chapter]]\nsubject = "Networking 101"\nbank = "net.json"\n'
    )
    result = load_config(cfg_file)
    assert isinstance(result, Ok)
    a, b = result.value.chapters
    assert a.slug == "aws-saa"
    assert a.progress_file == "progress-aws-saa.json"
    assert b.slug == "networking-101"
    assert b.bank_path == (tmp_path / "net.json").resolve()


def test_mixing_legacy_and_chapters_is_err(tmp_path: Path):
    cfg_file = tmp_path / "teach-me.toml"
    cfg_file.write_text(
        'subject = "Sub"\nbank = "bank.json"\n'
        '[[chapter]]\nsubject = "Other"\nbank = "other.json"\n'
    )
    result = load_config(cfg_file)
    assert isinstance(result, Err)
    assert "not both" in result.message


def test_colliding_chapter_slugs_is_err(tmp_path: Path):
    cfg_file = tmp_path / "teach-me.toml"
    cfg_file.write_text(
        '[[chapter]]\nsubject = "My Exam"\nbank = "a.json"\n'
        '[[chapter]]\nsubject = "my exam"\nbank = "b.json"\n'
    )
    result = load_config(cfg_file)
    assert isinstance(result, Err)
    assert "collide" in result.message


def test_tutor_is_optional(tmp_path: Path):
    cfg_file = tmp_path / "teach-me.toml"
    cfg_file.write_text('subject = "Sub"\nbank = "bank.json"\n')
    result = load_config(cfg_file)
    assert isinstance(result, Ok)
    assert result.value.tutor is None


def test_missing_file_is_err(tmp_path: Path):
    assert isinstance(load_config(tmp_path / "nope.toml"), Err)


def test_invalid_toml_is_err(tmp_path: Path):
    cfg_file = tmp_path / "teach-me.toml"
    cfg_file.write_text("subject = = broken")
    assert isinstance(load_config(cfg_file), Err)


def test_missing_required_field_is_err(tmp_path: Path):
    cfg_file = tmp_path / "teach-me.toml"
    cfg_file.write_text('bank = "bank.json"\n')  # no subject
    result = load_config(cfg_file)
    assert isinstance(result, Err)
    assert "subject" in result.message
