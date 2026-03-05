from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class AgentError(Exception):
    pass


@dataclass
class Attachment:
    filename: str       # "photo.jpg", "document.pdf"
    mime_type: str      # "image/jpeg", "application/pdf"
    data: bytes         # raw file content

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")

    def extract_text(self) -> str | None:
        """Try to extract readable text from the attachment.

        Returns extracted text, or None if extraction fails or is unsupported.
        """
        if self.mime_type == "application/pdf":
            try:
                import fitz  # pymupdf

                doc = fitz.open(stream=self.data, filetype="pdf")
                pages = [page.get_text() for page in doc]
                doc.close()
                text = "\n".join(pages).strip()
                return text or None
            except Exception:
                logger.debug("PDF text extraction failed: %s", self.filename, exc_info=True)
                return None
        if self.mime_type.startswith("text/") or self.mime_type in (
            "application/json",
            "application/xml",
            "application/javascript",
        ):
            try:
                return self.data.decode("utf-8")
            except (UnicodeDecodeError, ValueError):
                return None
        return None


@dataclass
class AgentResult:
    text: str
    session_id: str | None
