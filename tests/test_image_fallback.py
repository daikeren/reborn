from __future__ import annotations

from app.agent.image_fallback import (
    build_retry_instruction,
    build_text_attachment_entries,
    failed_image_attachment_names,
    has_image_attachments,
    is_recoverable_image_error,
)
from app.agent.types import Attachment


def test_has_image_attachments_detects_images():
    attachments = [
        Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff\xd8"),
        Attachment(filename="note.txt", mime_type="text/plain", data=b"hello"),
    ]

    assert has_image_attachments(attachments) is True


def test_has_image_attachments_false_without_images():
    attachments = [
        Attachment(filename="note.txt", mime_type="text/plain", data=b"hello"),
    ]

    assert has_image_attachments(attachments) is False


def test_is_recoverable_image_error_matches_image_specific_failures():
    error = (
        'API Error: 400 {"type":"error","error":{"type":"invalid_request_error",'
        '"message":"Could not process image"}}'
    )

    assert is_recoverable_image_error(error) is True


def test_is_recoverable_image_error_ignores_generic_invalid_requests():
    assert (
        is_recoverable_image_error("invalid_request_error: malformed tool schema")
        is False
    )


def test_build_retry_instruction_mentions_follow_up_safety():
    text = build_retry_instruction("What is in this image?")

    assert "Do not claim to have seen the image." in text
    assert "If the user asks about the image contents in a later turn" in text


def test_build_retry_instruction_for_image_only_requests_asks_for_resend():
    text = build_retry_instruction("")

    assert "re-upload the image or describe what they want analyzed" in text


def test_build_text_attachment_entries_include_failed_images_and_non_image_text():
    attachments = [
        Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff\xd8"),
        Attachment(filename="note.txt", mime_type="text/plain", data=b"hello"),
    ]

    entries = build_text_attachment_entries(attachments, include_failed_images=True)

    assert "photo.jpg (image/jpeg)" in entries[0]
    assert "could not process this image" in entries[0]
    assert entries[1] == "[Content of note.txt]\nhello"


def test_failed_image_attachment_names_only_returns_images():
    attachments = [
        Attachment(filename="photo.jpg", mime_type="image/jpeg", data=b"\xff\xd8"),
        Attachment(filename="note.txt", mime_type="text/plain", data=b"hello"),
    ]

    assert failed_image_attachment_names(attachments) == ["photo.jpg"]
