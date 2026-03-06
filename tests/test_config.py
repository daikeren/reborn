from __future__ import annotations

from pathlib import Path

from app.config import Settings


def test_extra_writable_roots_parses_multiple_paths(monkeypatch, tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    monkeypatch.setenv(
        "EXTRA_WRITABLE_ROOTS",
        f" {first} , , {second} , {first} ",
    )
    settings = Settings()

    assert settings.extra_writable_roots == (first.resolve(), second.resolve())
