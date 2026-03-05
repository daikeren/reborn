from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecodedSessionId:
    backend: str
    native_id: str


def encode_session_id(backend: str, native_id: str | None) -> str | None:
    if not native_id:
        return None
    return f"{backend}:{native_id}"


def decode_session_id(value: str | None) -> DecodedSessionId | None:
    if not value or ":" not in value:
        return None
    backend, native = value.split(":", 1)
    if not backend or not native:
        return None
    return DecodedSessionId(backend=backend, native_id=native)

