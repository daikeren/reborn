from __future__ import annotations

from app.agent.types import Attachment

_IMAGE_ERROR_MARKERS = (
    "could not process image",
    "image could not be processed",
    "unable to process image",
    "failed to process image",
    "error processing image",
    "image processing failed",
    "invalid image",
    "unsupported image",
    "corrupt image",
    "malformed image",
)
_INVALID_REQUEST_MARKERS = (
    "invalid_request_error",
    "invalid request",
    "bad request",
)
_IMAGE_HINT_MARKERS = (
    "image",
    "jpeg",
    "jpg",
    "png",
    "gif",
    "webp",
)
_IMAGE_ACTION_MARKERS = (
    "process",
    "decode",
    "parse",
    "unsupported",
    "invalid",
)


def has_image_attachments(attachments: list[Attachment] | None) -> bool:
    return any(att.is_image for att in attachments or [])


def is_recoverable_image_error(error: BaseException | str) -> bool:
    text = str(error).lower()
    if not text:
        return False
    if any(marker in text for marker in _IMAGE_ERROR_MARKERS):
        return True
    return (
        any(marker in text for marker in _INVALID_REQUEST_MARKERS)
        and any(marker in text for marker in _IMAGE_HINT_MARKERS)
        and any(marker in text for marker in _IMAGE_ACTION_MARKERS)
    )


def build_retry_instruction(message: str) -> str:
    has_user_text = bool(message.strip())
    response_rule = (
        "Briefly tell the user the image could not be processed this time, then continue "
        "answering using only the text context that is available."
        if has_user_text
        else "Tell the user the image could not be processed this time and ask them to "
        "re-upload the image or describe what they want analyzed."
    )
    return (
        "[System note: image upload fallback]\n"
        "One or more image attachments in the immediately previous request could not be "
        "processed by the upstream API.\n"
        "You did not successfully view the image contents.\n"
        f"{response_rule}\n"
        "Do not claim to have seen the image.\n"
        "If the user asks about the image contents in a later turn, ask them to re-upload "
        "the image or describe it in text.\n"
        "Do not invent any visual details."
    )


def build_text_attachment_entries(
    attachments: list[Attachment] | None,
    *,
    include_failed_images: bool = False,
) -> list[str]:
    entries: list[str] = []
    for att in attachments or []:
        if att.is_image:
            if include_failed_images:
                entries.append(
                    "[Image attachment unavailable: "
                    f"{att.filename} ({att.mime_type}) - the API could not process this "
                    "image, so no visual details are available from it.]"
                )
            continue
        extracted = att.extract_text()
        if extracted:
            entries.append(f"[Content of {att.filename}]\n{extracted}")
        else:
            entries.append(
                f"[Attached file: {att.filename} ({att.mime_type}) - content could not be extracted]"
            )
    return entries


def failed_image_attachment_names(attachments: list[Attachment] | None) -> list[str]:
    return [att.filename for att in attachments or [] if att.is_image]
