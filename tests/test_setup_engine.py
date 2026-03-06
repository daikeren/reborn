from __future__ import annotations

import importlib.util
from pathlib import Path

from app.setup.engine import SetupAnswers, apply_setup, inspect_setup, verify_setup


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(
        repo / ".env.example",
        "# Example\n# AGENT_BACKEND=codex\n# TIMEZONE=Asia/Taipei\n# WORKSPACE_DIR=workspace\n",
    )
    jobs = repo / "workspace" / "jobs"
    jobs.mkdir(parents=True)
    for name in ("heartbeat.md", "morning_brief.md", "weekly_review.md"):
        (jobs / name).write_text(f"{name}\n", encoding="utf-8")
    return repo


def test_inspect_reports_missing_core_state(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.setattr("app.setup.engine._codex_auth_ready", lambda: False)
    monkeypatch.setattr("app.setup.engine.shutil.which", lambda name: None)

    result = inspect_setup(repo).to_dict()

    assert ".env is missing" in result["blocking_problems"]
    assert "AGENT_BACKEND is not configured" in result["blocking_problems"]
    assert (
        "At least one channel must be fully configured" in result["blocking_problems"]
    )
    assert result["workspace"]["soul_exists"] is False
    assert result["workspace"]["memory_exists"] is False


def test_apply_creates_env_and_workspace_files(tmp_path: Path):
    repo = _repo(tmp_path)
    answers = SetupAnswers(
        assistant_name="Reborn",
        owner_name="Andy",
        primary_language="Traditional Chinese",
        timezone="Asia/Taipei",
        backend="codex",
        telegram_bot_token="123:abc",
        allowed_telegram_user_id="42",
    )

    result = apply_setup(answers, repo)
    env_text = (repo / ".env").read_text(encoding="utf-8")
    soul_text = (repo / "workspace" / "SOUL.md").read_text(encoding="utf-8")
    memory_text = (repo / "workspace" / "MEMORY.md").read_text(encoding="utf-8")

    assert str(repo / ".env") in result["files_written"]
    assert "AGENT_BACKEND=codex" in env_text
    assert "TELEGRAM_BOT_TOKEN=123:abc" in env_text
    assert "You are Reborn, Andy's personal AI assistant." in soul_text
    assert "Primary language: Traditional Chinese" in memory_text


def test_apply_dry_run_reports_existing_default_job_files_without_writing(
    tmp_path: Path,
):
    repo = _repo(tmp_path)
    answers = SetupAnswers(
        assistant_name="Reborn",
        owner_name="Andy",
        primary_language="Traditional Chinese",
        timezone="Asia/Taipei",
        backend="codex",
        telegram_bot_token="123:abc",
        allowed_telegram_user_id="42",
    )

    result = apply_setup(answers, repo, dry_run=True)

    assert result["dry_run"] is True
    assert str(repo / ".env") in result["files_written"]
    assert (
        str(repo / "workspace" / "jobs" / "heartbeat.md") not in result["files_written"]
    )
    assert not (repo / ".env").exists()


def test_verify_passes_for_complete_codex_setup(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path)
    _write(
        repo / ".env",
        "\n".join(
            [
                "AGENT_BACKEND=codex",
                "WORKSPACE_DIR=workspace",
                "TIMEZONE=Asia/Taipei",
                "TELEGRAM_BOT_TOKEN=123:abc",
                "ALLOWED_TELEGRAM_USER_ID=42",
            ]
        )
        + "\n",
    )
    _write(repo / "workspace" / "SOUL.md", "soul\n")
    _write(repo / "workspace" / "MEMORY.md", "memory\n")
    monkeypatch.setattr("app.setup.engine._codex_auth_ready", lambda: True)
    monkeypatch.setattr(
        "app.setup.engine.shutil.which",
        lambda name: "/usr/bin/fake" if name in {"codex", "gog"} else None,
    )

    result = verify_setup(repo)

    assert result["ok"] is True
    assert result["errors"] == []
    assert "uv run uvicorn app.main:app --reload" in result["next_steps"][0]


def test_verify_fails_on_partial_slack_config(tmp_path: Path, monkeypatch):
    repo = _repo(tmp_path)
    _write(
        repo / ".env",
        "\n".join(
            [
                "AGENT_BACKEND=codex",
                "WORKSPACE_DIR=workspace",
                "TIMEZONE=Asia/Taipei",
                "SLACK_BOT_TOKEN=xoxb-1",
            ]
        )
        + "\n",
    )
    monkeypatch.setattr("app.setup.engine._codex_auth_ready", lambda: True)
    monkeypatch.setattr("app.setup.engine.shutil.which", lambda name: "/usr/bin/fake")

    result = verify_setup(repo)

    assert result["ok"] is False
    assert any("Slack configuration is incomplete" in err for err in result["errors"])


def test_default_templates_are_optional_safe():
    repo_root = Path(__file__).resolve().parents[1]
    soul = (repo_root / "workspace" / "SOUL.md.example").read_text(encoding="utf-8")
    heartbeat = (repo_root / "workspace" / "jobs" / "heartbeat.md").read_text(
        encoding="utf-8"
    )
    morning = (repo_root / "workspace" / "jobs" / "morning_brief.md").read_text(
        encoding="utf-8"
    )
    weekly = (repo_root / "workspace" / "jobs" / "weekly_review.md").read_text(
        encoding="utf-8"
    )

    assert "gog calendar events" not in heartbeat
    assert "gog calendar events" not in morning
    assert "gog calendar events" not in weekly
    assert "obsidian_*" not in morning
    assert "Use Obsidian tools only when an Obsidian vault path is configured" in soul


def test_install_setup_skill_defaults_to_codex_dir(tmp_path: Path, monkeypatch):
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "install_setup_skill.py"
    )
    spec = importlib.util.spec_from_file_location("install_setup_skill", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    home = tmp_path / "home"
    monkeypatch.delenv("CODEX_HOME", raising=False)

    destinations = module.resolve_destinations(home=home)

    assert destinations == [home / ".codex" / "skills"]


def test_codex_auth_ready_uses_home_fallback(tmp_path: Path, monkeypatch):
    auth_dir = tmp_path / ".codex"
    auth_dir.mkdir()
    (auth_dir / "auth.json").write_text("{}", encoding="utf-8")

    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    from app.setup.engine import _codex_auth_ready

    assert _codex_auth_ready() is True
