from pathlib import Path

from teach_me.config import BUNDLED_CONFIG, load_config
from teach_me.models import Err, Ok

BANK_JSON = '[{"id":1,"question":"q","options":["a","b"],"correct":[0],"topics":["T"]}]'


def test_load_bundled_config():
    result = load_config(BUNDLED_CONFIG)
    assert isinstance(result, Ok)
    cfg = result.value
    assert cfg.subject == "General Knowledge"
    assert cfg.bank_path.name == "sample-bank.json"
    assert cfg.bank_path.is_file()
    assert cfg.tutor is not None
    assert cfg.tutor.model == "claude-sonnet-5"


def test_bank_path_resolves_relative_to_config(tmp_path: Path):
    (tmp_path / "bank.json").write_text(BANK_JSON)
    cfg_file = tmp_path / "teach-me.toml"
    cfg_file.write_text('subject = "Sub"\nbank = "bank.json"\n')

    result = load_config(cfg_file)
    assert isinstance(result, Ok)
    assert result.value.bank_path == (tmp_path / "bank.json").resolve()
    assert result.value.data_dir == Path("data")  # default


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
