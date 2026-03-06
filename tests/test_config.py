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
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)

    settings = Settings()

    assert settings.extra_writable_roots == (first.resolve(), second.resolve())


def test_extra_writable_roots_merges_legacy_obsidian_path(monkeypatch, tmp_path: Path):
    first = tmp_path / "first"
    legacy = tmp_path / "vault"
    monkeypatch.setenv("EXTRA_WRITABLE_ROOTS", str(first))
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(legacy))

    settings = Settings()

    assert settings.extra_writable_roots == (first.resolve(), legacy.resolve())
    assert settings.obsidian_vault_path == legacy.resolve()
