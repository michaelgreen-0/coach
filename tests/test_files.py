import os
from pathlib import Path

import pytest

from coach.backend.core.files import atomic_write_text


def test_writes_content(tmp_path: Path):
    target = tmp_path / "sub" / "data.json"  # parent created on demand
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"


def test_failed_write_preserves_original_and_leaves_no_temp(tmp_path: Path, monkeypatch):
    target = tmp_path / "data.json"
    target.write_text("original")

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(target, "new content")

    # the existing file is untouched, and no temp file is left behind
    assert target.read_text() == "original"
    assert list(tmp_path.iterdir()) == [target]
