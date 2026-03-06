from __future__ import annotations

import base64
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.types import Attachment
from app.orchestrator import ExecutionService, InteractiveExecutionRequest
from app.sessions.manager import SessionManager
from app.sessions.store import SessionStore


# ---------------------------------------------------------------------------
# Attachment dataclass
# ---------------------------------------------------------------------------


def test_attachment_is_image_true():
    att = Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff")
    assert att.is_image is True


def test_attachment_is_image_png():
    att = Attachment(filename="shot.png", mime_type="image/png", data=b"\x89PNG")
    assert att.is_image is True


def test_attachment_is_image_false_for_pdf():
    att = Attachment(filename="doc.pdf", mime_type="application/pdf", data=b"%PDF")
    assert att.is_image is False


def test_attachment_is_image_false_for_text():
    att = Attachment(filename="note.txt", mime_type="text/plain", data=b"hello")
    assert att.is_image is False


# ---------------------------------------------------------------------------
# Claude backend content building
# ---------------------------------------------------------------------------


class TestClaudeBackendContent:
    def _backend(self):
        from app.agent.backends.claude_backend import ClaudeBackend

        return ClaudeBackend()

    def test_no_attachments_returns_string(self):
        backend = self._backend()
        result = backend._build_content("hello", None)
        assert result == "hello"

    def test_no_attachments_empty_list_returns_string(self):
        backend = self._backend()
        result = backend._build_content("hello", [])
        assert result == "hello"

    def test_image_attachment_produces_image_block(self):
        backend = self._backend()
        att = Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff\xd8")
        result = backend._build_content("look at this", [att])

        assert isinstance(result, list)
        assert len(result) == 2  # image block + text block

        img_block = result[0]
        assert img_block["type"] == "image"
        assert img_block["source"]["type"] == "base64"
        assert img_block["source"]["media_type"] == "image/jpeg"
        assert img_block["source"]["data"] == base64.b64encode(b"\xff\xd8").decode()

        text_block = result[1]
        assert text_block["type"] == "text"
        assert text_block["text"] == "look at this"

    def test_pdf_attachment_extracts_text(self):
        """PDF with extractable text sends inline text content."""
        import fitz  # pymupdf

        # Create a minimal valid PDF with text
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello from PDF")
        pdf_bytes = doc.tobytes()
        doc.close()

        backend = self._backend()
        att = Attachment(
            filename="doc.pdf", mime_type="application/pdf", data=pdf_bytes
        )
        result = backend._build_content("check this", [att])

        assert isinstance(result, list)
        assert len(result) == 2

        text_block = result[0]
        assert text_block["type"] == "text"
        assert "Content of doc.pdf" in text_block["text"]
        assert "Hello from PDF" in text_block["text"]

    def test_text_file_attachment_extracts_content(self):
        backend = self._backend()
        att = Attachment(
            filename="note.txt", mime_type="text/plain", data=b"some notes here"
        )
        result = backend._build_content("read this", [att])

        assert isinstance(result, list)
        assert len(result) == 2

        text_block = result[0]
        assert text_block["type"] == "text"
        assert "Content of note.txt" in text_block["text"]
        assert "some notes here" in text_block["text"]

    def test_unsupported_type_produces_text_placeholder(self):
        backend = self._backend()
        att = Attachment(
            filename="data.bin", mime_type="application/octet-stream", data=b"\x00\x01"
        )
        result = backend._build_content("check this", [att])

        assert isinstance(result, list)
        assert len(result) == 2

        placeholder = result[0]
        assert placeholder["type"] == "text"
        assert "data.bin" in placeholder["text"]
        assert "could not be extracted" in placeholder["text"]

    def test_attachment_only_no_text(self):
        backend = self._backend()
        att = Attachment(filename="img.png", mime_type="image/png", data=b"\x89PNG")
        result = backend._build_content("", [att])

        assert isinstance(result, list)
        # Only image block, no text block since message is empty
        assert len(result) == 1
        assert result[0]["type"] == "image"

    def test_mixed_attachments(self):
        import fitz

        # Create a valid PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "PDF content")
        pdf_bytes = doc.tobytes()
        doc.close()

        backend = self._backend()
        img = Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff")
        pdf = Attachment(
            filename="doc.pdf", mime_type="application/pdf", data=pdf_bytes
        )
        result = backend._build_content("mixed", [img, pdf])

        assert isinstance(result, list)
        assert len(result) == 3  # image + extracted text + user text
        assert result[0]["type"] == "image"
        assert result[1]["type"] == "text"
        assert "Content of doc.pdf" in result[1]["text"]
        assert "PDF content" in result[1]["text"]
        assert result[2]["type"] == "text"
        assert result[2]["text"] == "mixed"


# ---------------------------------------------------------------------------
# Codex backend attachment item building
# ---------------------------------------------------------------------------


class TestCodexBackendAttachments:
    def _backend(self):
        from app.agent.backends.codex_backend import CodexBackend

        return CodexBackend()

    def test_no_attachments_returns_empty(self):
        backend = self._backend()
        assert backend._build_attachment_items(None) == []
        assert backend._build_attachment_items([]) == []

    def test_image_produces_data_uri(self):
        backend = self._backend()
        att = Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff\xd8")
        items = backend._build_attachment_items([att])

        assert len(items) == 1
        item = items[0]
        assert item["type"] == "image_url"
        expected_uri = (
            f"data:image/jpeg;base64,{base64.b64encode(b'\xff\xd8').decode()}"
        )
        assert item["image_url"] == expected_uri

    def test_non_image_produces_text_placeholder(self):
        backend = self._backend()
        att = Attachment(filename="doc.pdf", mime_type="application/pdf", data=b"%PDF")
        items = backend._build_attachment_items([att])

        assert len(items) == 1
        assert items[0]["type"] == "text"
        assert "doc.pdf" in items[0]["text"]
        assert "application/pdf" in items[0]["text"]

    def test_mixed_attachments(self):
        backend = self._backend()
        img = Attachment(filename="img.png", mime_type="image/png", data=b"\x89PNG")
        pdf = Attachment(filename="file.pdf", mime_type="application/pdf", data=b"%PDF")
        items = backend._build_attachment_items([img, pdf])

        assert len(items) == 2
        assert items[0]["type"] == "image_url"
        assert items[1]["type"] == "text"


# ---------------------------------------------------------------------------
# Execution service attachment threading
# ---------------------------------------------------------------------------


@dataclass
class FakeResult:
    text: str
    session_id: str | None = None


@pytest.fixture()
def execution_service(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    manager = SessionManager(store)
    return ExecutionService(store, manager), store


@pytest.mark.asyncio
async def test_run_agent_passes_attachments_to_agent_turn(execution_service):
    service, _ = execution_service
    att = Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff")
    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.return_value = FakeResult(text="ok", session_id="s1")
        await service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="msg",
                attachments=[att],
            )
        )

    mock_at.assert_awaited_once()
    assert mock_at.call_args.kwargs["attachments"] == [att]


@pytest.mark.asyncio
async def test_run_agent_stores_attachment_note(execution_service):
    service, store = execution_service
    att = Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff")
    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.return_value = FakeResult(text="ok", session_id="s1")
        await service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="look at this",
                attachments=[att],
            )
        )

    messages = store.get_messages("key")
    user_msg = messages[0]
    assert user_msg.role == "user"
    assert "[Attachments: photo.jpg]" in user_msg.content
    assert "look at this" in user_msg.content


@pytest.mark.asyncio
async def test_run_agent_stores_attachment_only_no_text(execution_service):
    service, store = execution_service
    att = Attachment(filename="doc.pdf", mime_type="application/pdf", data=b"%PDF")
    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.return_value = FakeResult(text="ok", session_id="s1")
        await service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="",
                attachments=[att],
            )
        )

    messages = store.get_messages("key")
    user_msg = messages[0]
    assert user_msg.content == "[Attachments: doc.pdf]"


@pytest.mark.asyncio
async def test_run_agent_no_attachments_stores_plain_text(execution_service):
    service, store = execution_service
    with patch(
        "app.orchestrator.service.agent_turn", new_callable=AsyncMock
    ) as mock_at:
        mock_at.return_value = FakeResult(text="pong", session_id="s1")
        await service.run_interactive(
            InteractiveExecutionRequest(
                session_key="key",
                channel="telegram",
                message="ping",
            )
        )

    messages = store.get_messages("key")
    user_msg = messages[0]
    assert user_msg.content == "ping"
    assert "[Attachments" not in user_msg.content


# ---------------------------------------------------------------------------
# Runtime passes attachments through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_passes_attachments(monkeypatch):
    from types import SimpleNamespace

    from app.agent.runtime import agent_turn
    from app.agent.types import AgentResult

    att = Attachment(filename="img.png", mime_type="image/png", data=b"\x89PNG")
    backend = SimpleNamespace(
        name="codex",
        agent_turn=AsyncMock(return_value=AgentResult(text="ok", session_id="s1")),
    )
    monkeypatch.setattr("app.agent.runtime.get_runtime_backend", lambda: backend)

    await agent_turn("hello", attachments=[att])

    assert backend.agent_turn.call_args.kwargs["attachments"] == [att]


@pytest.mark.asyncio
async def test_runtime_no_attachments_passes_none(monkeypatch):
    from types import SimpleNamespace

    from app.agent.runtime import agent_turn
    from app.agent.types import AgentResult

    backend = SimpleNamespace(
        name="codex",
        agent_turn=AsyncMock(return_value=AgentResult(text="ok", session_id="s1")),
    )
    monkeypatch.setattr("app.agent.runtime.get_runtime_backend", lambda: backend)

    await agent_turn("hello")

    assert backend.agent_turn.call_args.kwargs.get("attachments") is None
