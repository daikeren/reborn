from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.types import Attachment
from app.monitoring.tracker import ExecutionTracker
from app.orchestrator import ExecutionService, InteractiveExecutionRequest
from app.sessions.manager import SessionManager
from app.sessions.store import SessionStore


@dataclass
class FakeResult:
    text: str
    session_id: str | None = None


@pytest.fixture()
def service(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    manager = SessionManager(store)
    return ExecutionService(store, manager), store, manager


@pytest.mark.asyncio
async def test_run_interactive_passes_channel_to_agent_turn(service):
    execution_service, _, _ = service
    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.return_value = FakeResult(text="ok", session_id="s1")
        await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="msg",
            )
        )

    assert mock_at.call_args.kwargs["channel"] == "telegram"


@pytest.mark.asyncio
async def test_run_interactive_retry_passes_channel(service):
    execution_service, _, _ = service
    call_count = 0

    async def fail_then_succeed(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("resume failed")
        return FakeResult(text="ok", session_id="s2")

    with patch(
        "app.orchestrator.service.agent_turn", side_effect=fail_then_succeed
    ) as mock_at:
        result = await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="msg",
                resume_session_id="old-sess",
            )
        )

    assert result is not None
    assert result.text == "ok"
    assert call_count == 2
    assert mock_at.await_args_list[1].kwargs["channel"] == "telegram"
    assert mock_at.await_args_list[1].kwargs["session_id"] is None


@pytest.mark.asyncio
async def test_run_interactive_persists_message_history(service):
    execution_service, store, _ = service
    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.return_value = FakeResult(text="pong", session_id="s1")
        result = await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="ping",
            )
        )

    assert result is not None
    messages = store.get_messages("key")
    assert [m.role for m in messages] == ["user", "assistant"]
    assert [m.content for m in messages] == ["ping", "pong"]


@pytest.mark.asyncio
async def test_run_interactive_passes_attachments_to_agent_turn(service):
    execution_service, _, _ = service
    att = Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff")
    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.return_value = FakeResult(text="ok", session_id="s1")
        await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="msg",
                attachments=[att],
            )
        )

    assert mock_at.call_args.kwargs["attachments"] == [att]


@pytest.mark.asyncio
async def test_run_interactive_stores_attachment_note(service):
    execution_service, store, _ = service
    att = Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff")
    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.return_value = FakeResult(text="ok", session_id="s1")
        await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="look at this",
                attachments=[att],
            )
        )

    user_msg = store.get_messages("key")[0]
    assert user_msg.role == "user"
    assert "[Attachments: photo.jpg]" in user_msg.content
    assert "look at this" in user_msg.content


@pytest.mark.asyncio
async def test_run_interactive_stores_attachment_only_no_text(service):
    execution_service, store, _ = service
    att = Attachment(filename="doc.pdf", mime_type="application/pdf", data=b"%PDF")
    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.return_value = FakeResult(text="ok", session_id="s1")
        await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="",
                attachments=[att],
            )
        )

    assert store.get_messages("key")[0].content == "[Attachments: doc.pdf]"


@pytest.mark.asyncio
async def test_run_interactive_no_attachments_stores_plain_text(service):
    execution_service, store, _ = service
    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.return_value = FakeResult(text="pong", session_id="s1")
        await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="ping",
            )
        )

    user_msg = store.get_messages("key")[0]
    assert user_msg.content == "ping"
    assert "[Attachments" not in user_msg.content


@pytest.mark.asyncio
async def test_same_session_concurrent_messages_are_serialized(service):
    execution_service, _, _ = service
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    active_calls = 0
    max_active_calls = 0

    async def slow_turn(*args, **kwargs):
        nonlocal active_calls, max_active_calls
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        if not first_started.is_set():
            first_started.set()
            await release_first.wait()
        await asyncio.sleep(0)
        active_calls -= 1
        return FakeResult(text="ok", session_id="sid")

    with patch("app.orchestrator.service.agent_turn", side_effect=slow_turn):
        task1 = asyncio.create_task(
            execution_service.run_interactive(
                InteractiveExecutionRequest(
                    session_key="shared",
                    channel="telegram",
                    message="one",
                )
            )
        )
        await first_started.wait()
        task2 = asyncio.create_task(
            execution_service.run_interactive(
                InteractiveExecutionRequest(
                    session_key="shared",
                    channel="telegram",
                    message="two",
                )
            )
        )
        await asyncio.sleep(0)
        assert max_active_calls == 1
        release_first.set()
        await asyncio.gather(task1, task2)

    assert max_active_calls == 1


@pytest.mark.asyncio
async def test_different_sessions_can_run_concurrently(service):
    execution_service, _, _ = service
    both_started = asyncio.Event()
    active_calls = 0
    max_active_calls = 0

    async def slow_turn(*args, **kwargs):
        nonlocal active_calls, max_active_calls
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        if active_calls >= 2:
            both_started.set()
        await both_started.wait()
        await asyncio.sleep(0)
        active_calls -= 1
        return FakeResult(text="ok", session_id="sid")

    with patch("app.orchestrator.service.agent_turn", side_effect=slow_turn):
        await asyncio.gather(
            execution_service.run_interactive(
                InteractiveExecutionRequest(
                    session_key="one",
                    channel="telegram",
                    message="one",
                )
            ),
            execution_service.run_interactive(
                InteractiveExecutionRequest(
                    session_key="two",
                    channel="telegram",
                    message="two",
                )
            ),
        )

    assert max_active_calls == 2


@pytest.mark.asyncio
async def test_telegram_chat_reuses_active_conversation(service):
    execution_service, store, _ = service
    chat_key = "telegram:chat:42"

    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.side_effect = [
            FakeResult(text="first", session_id="sid-1"),
            FakeResult(text="second", session_id="sid-1"),
        ]

        await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key=None,
                chat_key=chat_key,
                channel="telegram",
                message="hello",
                session_policy="telegram",
            )
        )
        await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key=None,
                chat_key=chat_key,
                channel="telegram",
                message="again",
                session_policy="telegram",
            )
        )

    assert mock_at.await_args_list[0].kwargs["session_id"] is None
    assert mock_at.await_args_list[1].kwargs["session_id"] == "sid-1"
    sessions = store.list_sessions(limit=10)
    assert len(sessions) == 1
    assert sessions[0].chat_key == chat_key
    assert sessions[0].session_key.startswith("telegram:conversation:42:")
    assert [m.content for m in store.get_messages(sessions[0].session_key)] == [
        "hello",
        "first",
        "again",
        "second",
    ]


@pytest.mark.asyncio
async def test_telegram_new_starts_fresh_conversation(service):
    execution_service, store, manager = service
    chat_key = "telegram:chat:42"

    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.side_effect = [
            FakeResult(text="first", session_id="sid-1"),
            FakeResult(text="second", session_id="sid-2"),
        ]

        await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key=None,
                chat_key=chat_key,
                channel="telegram",
                message="hello",
                session_policy="telegram",
            )
        )
        await manager.reset_telegram_session(chat_key)
        await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key=None,
                chat_key=chat_key,
                channel="telegram",
                message="new topic",
                session_policy="telegram",
            )
        )

    assert mock_at.await_args_list[0].kwargs["session_id"] is None
    assert mock_at.await_args_list[1].kwargs["session_id"] is None
    sessions = store.list_sessions(limit=10)
    assert len(sessions) == 2
    assert {s.chat_key for s in sessions} == {chat_key}
    assert len({s.session_key for s in sessions}) == 2


@pytest.mark.asyncio
async def test_same_telegram_chat_is_locked_by_chat_key(service):
    execution_service, _, _ = service
    chat_key = "telegram:chat:shared"
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    active_calls = 0
    max_active_calls = 0

    async def slow_turn(*args, **kwargs):
        nonlocal active_calls, max_active_calls
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        if not first_started.is_set():
            first_started.set()
            await release_first.wait()
        await asyncio.sleep(0)
        active_calls -= 1
        return FakeResult(text="ok", session_id="sid")

    with patch("app.orchestrator.service.agent_turn", side_effect=slow_turn):
        task1 = asyncio.create_task(
            execution_service.run_interactive(
                InteractiveExecutionRequest(
                    session_key=None,
                    chat_key=chat_key,
                    channel="telegram",
                    message="one",
                    session_policy="telegram",
                )
            )
        )
        await first_started.wait()
        task2 = asyncio.create_task(
            execution_service.run_interactive(
                InteractiveExecutionRequest(
                    session_key=None,
                    chat_key=chat_key,
                    channel="telegram",
                    message="two",
                    session_policy="telegram",
                )
            )
        )
        await asyncio.sleep(0)
        assert max_active_calls == 1
        release_first.set()
        await asyncio.gather(task1, task2)

    assert max_active_calls == 1


@pytest.mark.asyncio
async def test_start_interactive_cancel_marks_execution_cancelled(service):
    execution_service, store, _ = service
    tracker = ExecutionTracker()
    started = asyncio.Event()

    async def slow_turn(*args, **kwargs):
        started.set()
        await asyncio.sleep(10)
        return FakeResult(text="ok", session_id="sid")

    with (
        patch("app.orchestrator.service.get_tracker", return_value=tracker),
        patch("app.orchestrator.service.agent_turn", side_effect=slow_turn),
    ):
        execution_id = execution_service.start_interactive(
            InteractiveExecutionRequest(
                session_key="web:session:test",
                channel="web",
                message="hello",
            )
        )
        await started.wait()
        assert execution_service.cancel_execution(execution_id) is True
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    completed = tracker.get_completed(execution_id)
    assert completed is not None
    assert completed.status == "cancelled"
    messages = store.get_messages("web:session:test")
    assert [m.role for m in messages] == ["user"]
    assert [m.content for m in messages] == ["hello"]


@pytest.mark.asyncio
async def test_operator_note_is_persisted_as_note_role(service):
    execution_service, store, _ = service
    tracker = ExecutionTracker()

    with (
        patch("app.orchestrator.service.get_tracker", return_value=tracker),
        patch(
            "app.orchestrator.service.agent_turn",
            new_callable=AsyncMock,
            return_value=FakeResult(text="ack", session_id="sid-note"),
        ) as mock_at,
    ):
        result = await execution_service.run_interactive(
            InteractiveExecutionRequest(
                session_key="web:session:test",
                channel="web",
                message="[Operator note from dashboard]\nPin this context.",
                persist_user_message=True,
                stored_role="note",
                stored_message="Pin this context.",
            )
        )

    assert result is not None
    assert (
        mock_at.await_args.args[0]
        == "[Operator note from dashboard]\nPin this context."
    )
    messages = store.get_messages("web:session:test")
    assert [m.role for m in messages] == ["note", "assistant"]
    assert messages[0].content == "Pin this context."
