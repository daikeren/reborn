from __future__ import annotations

from collections import OrderedDict

from app.monitoring.types import ExecutionStatus

_MAX_COMPLETED = 50


class ExecutionTracker:
    def __init__(self) -> None:
        self._active: dict[str, ExecutionStatus] = {}
        self._completed: OrderedDict[str, ExecutionStatus] = OrderedDict()

    def start_execution(
        self,
        session_key: str,
        *,
        channel: str | None = None,
        backend: str | None = None,
    ) -> ExecutionStatus:
        execution = ExecutionStatus(
            session_key=session_key,
            channel=channel,
            backend=backend,
        )
        self._active[session_key] = execution
        return execution

    def finish_execution(self, session_key: str) -> None:
        execution = self._active.pop(session_key, None)
        if execution is None:
            return
        self._completed[session_key] = execution
        while len(self._completed) > _MAX_COMPLETED:
            self._completed.popitem(last=False)

    def get_active(self, session_key: str) -> ExecutionStatus | None:
        return self._active.get(session_key)

    def list_active(self) -> list[ExecutionStatus]:
        return list(self._active.values())

    def get_completed(self, session_key: str) -> ExecutionStatus | None:
        return self._completed.get(session_key)

    def list_completed(self) -> list[ExecutionStatus]:
        return list(reversed(self._completed.values()))


_tracker: ExecutionTracker | None = None


def get_tracker() -> ExecutionTracker:
    global _tracker
    if _tracker is None:
        _tracker = ExecutionTracker()
    return _tracker
