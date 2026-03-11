from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from app.main import (
    SendOperatorNoteRequest,
    SendWebMessageRequest,
    UpdateJobRequest,
    api_reload_scheduler,
    app,
    dashboard_config,
    dashboard_create_web_session,
    dashboard_disable_job,
    dashboard_enable_job,
    dashboard_job_detail,
    dashboard_reset_session,
    dashboard_run_job,
    dashboard_send_operator_note,
    dashboard_send_web_message,
    dashboard_session_detail,
    dashboard_sessions,
    dashboard_skills,
    dashboard_update_job,
)
from app.orchestrator import ExecutionService
from app.sessions.manager import SessionManager
from app.sessions.store import SessionStore


@pytest.fixture()
def dashboard_state(workspace: Path):
    store = SessionStore(workspace / "test.db")
    manager = SessionManager(store)
    execution_service = ExecutionService(store, manager)
    app.state.session_store = store
    app.state.session_manager = manager
    app.state.execution_service = execution_service
    yield store, manager, execution_service
    store.close()


@pytest.mark.asyncio
async def test_dashboard_create_web_session_sets_placeholder(dashboard_state):
    store, _, _ = dashboard_state

    created = await dashboard_create_web_session()
    detail = await dashboard_session_detail(created["session_key"])

    assert created["session_key"].startswith("web:session:")
    assert store.get(created["session_key"]) is not None
    assert detail["channel"] == "web"
    assert detail["available_actions"] == ["reset"]


@pytest.mark.asyncio
async def test_dashboard_send_web_message_uses_execution_service(dashboard_state):
    store, _, execution_service = dashboard_state
    session_key = "web:session:test"
    store.create_placeholder_session(session_key)

    with patch.object(
        execution_service, "start_interactive", return_value="exec-1"
    ) as mock_start:
        result = await dashboard_send_web_message(
            session_key,
            SendWebMessageRequest(message="hello"),
        )

    assert result == {"session_key": session_key, "execution_id": "exec-1"}
    request = mock_start.call_args.args[0]
    assert request.session_key == session_key
    assert request.channel == "web"
    assert request.message == "hello"


@pytest.mark.asyncio
async def test_dashboard_send_operator_note_marks_note_role(dashboard_state):
    store, _, execution_service = dashboard_state
    session_key = "web:session:test"
    store.create_placeholder_session(session_key)

    with patch.object(
        execution_service, "start_interactive", return_value="exec-note"
    ) as mock_start:
        result = await dashboard_send_operator_note(
            session_key,
            SendOperatorNoteRequest(note="Pin this."),
        )

    assert result["execution_id"] == "exec-note"
    request = mock_start.call_args.args[0]
    assert request.stored_role == "note"
    assert request.stored_message == "Pin this."
    assert request.message.startswith("[Operator note from dashboard]")


@pytest.mark.asyncio
async def test_dashboard_reset_slack_session_is_unsupported(dashboard_state):
    store, _, _ = dashboard_state
    store.create_placeholder_session("slack:thread:C1:123")

    with pytest.raises(HTTPException, match="unsupported"):
        await dashboard_reset_session("slack:thread:C1:123")


@pytest.mark.asyncio
async def test_dashboard_sessions_filters_by_status(dashboard_state):
    store, _, _ = dashboard_state
    session = store.create_placeholder_session("web:session:test")

    payload = await dashboard_sessions(status="idle")

    assert payload["total"] == 1
    assert payload["sessions"][0]["session_key"] == session.session_key


@pytest.mark.asyncio
async def test_dashboard_update_job_promotes_legacy_prompt_and_reloads(
    workspace: Path, dashboard_state
):
    prompts_dir = workspace / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    (prompts_dir / "legacy_job.md").write_text(
        """\
---
schedule: "0 9 * * *"
---
Legacy body.
""",
        encoding="utf-8",
    )

    with patch("app.main.reload_scheduler", new=AsyncMock()) as mock_reload:
        result = await dashboard_update_job(
            "legacy_job",
            UpdateJobRequest(
                schedule="0 10 * * *",
                tools=["WebSearch"],
                max_turns=12,
                suppress_token="OK",
                enabled=False,
                prompt="Updated body.",
            ),
        )

    saved = workspace / "jobs" / "legacy_job.md"
    assert saved.exists()
    assert "enabled: false" in saved.read_text(encoding="utf-8")
    assert result["source"] == "jobs"
    mock_reload.assert_awaited_once()


@pytest.mark.asyncio
async def test_dashboard_enable_disable_job(workspace: Path, dashboard_state):
    jobs_dir = workspace / "jobs"
    jobs_dir.mkdir(exist_ok=True)
    (jobs_dir / "heartbeat.md").write_text(
        """\
---
schedule: "*/30 * * * *"
enabled: true
---
Heartbeat.
""",
        encoding="utf-8",
    )

    with patch("app.main.reload_scheduler", new=AsyncMock()):
        disabled = await dashboard_disable_job("heartbeat")
        enabled = await dashboard_enable_job("heartbeat")

    assert disabled["enabled"] is False
    assert enabled["enabled"] is True
    detail = await dashboard_job_detail("heartbeat")
    assert detail["enabled"] is True


@pytest.mark.asyncio
async def test_dashboard_run_job_returns_409_without_scheduler(
    workspace: Path, dashboard_state
):
    jobs_dir = workspace / "jobs"
    jobs_dir.mkdir(exist_ok=True)
    (jobs_dir / "heartbeat.md").write_text(
        """\
---
schedule: "*/30 * * * *"
---
Heartbeat.
""",
        encoding="utf-8",
    )

    with patch("app.main.run_job_now", new=AsyncMock(return_value=False)):
        with pytest.raises(HTTPException, match="Telegram delivery is disabled"):
            await dashboard_run_job("heartbeat")


@pytest.mark.asyncio
async def test_dashboard_config_and_skills(workspace: Path, dashboard_state):
    (workspace / "SOUL.md").write_text("You are Reborn.", encoding="utf-8")
    (workspace / "MEMORY.md").write_text("## Facts", encoding="utf-8")
    skills_dir = workspace / "skills"
    skills_dir.mkdir(exist_ok=True)
    good_dir = skills_dir / "good"
    good_dir.mkdir()
    (good_dir / "SKILL.md").write_text(
        """\
---
description: Good skill
---
Use me.
""",
        encoding="utf-8",
    )
    bad_dir = skills_dir / "bad"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text(
        """\
---
tools:
  - WebSearch
---
Missing description.
""",
        encoding="utf-8",
    )

    config = await dashboard_config()
    skills = await dashboard_skills()

    assert "runtime" in config
    assert any(
        item["name"] == "good" and item["status"] == "loaded"
        for item in skills["skills"]
    )
    assert any(
        item["name"] == "bad" and item["status"] == "blocked"
        for item in skills["skills"]
    )


@pytest.mark.asyncio
async def test_api_reload_scheduler_when_not_initialized(dashboard_state):
    with patch("app.main.reload_scheduler", new=AsyncMock(return_value=None)):
        result = await api_reload_scheduler()

    assert result["status"] == "skipped"
    assert result["reason"] == "scheduler not initialized"
    assert result["jobs"] == 0


@pytest.mark.asyncio
async def test_api_reload_scheduler_returns_job_count(workspace: Path, dashboard_state):
    mock_scheduler = Mock()
    mock_scheduler.get_jobs.return_value = ["job1", "job2", "job3"]

    with patch("app.main.reload_scheduler", new=AsyncMock(return_value=mock_scheduler)):
        result = await api_reload_scheduler()

    assert result["status"] == "reloaded"
    assert result["jobs"] == 3
