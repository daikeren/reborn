from __future__ import annotations

import time

_seen_events: dict[str, float] = {}
_DEDUP_TTL = 300  # 5 minutes


def is_duplicate_event(event_id: str) -> bool:
    """Check whether *event_id* was processed recently."""
    now = time.monotonic()
    expired = [
        key for key, seen_at in _seen_events.items() if now - seen_at > _DEDUP_TTL
    ]
    for key in expired:
        del _seen_events[key]
    if event_id in _seen_events:
        return True
    _seen_events[event_id] = now
    return False
