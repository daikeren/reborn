from __future__ import annotations

from collections import OrderedDict
from uuid import uuid4

from app.monitoring.types import ExecutionStatus

_MAX_COMPLETED = 50


class ExecutionTracker:
    def __init__(self) -> None:
        self._active_by_id: dict[str, ExecutionStatus] = {}
        self._active_by_session: dict[str, str] = {}
        self._completed_by_id: OrderedDict[str, ExecutionStatus] = OrderedDict()

    def start_execution(
        self,
        session_key: str,
        *,
        execution_id: str | None = None,
        channel: str | None = None,
        backend: str | None = None,
    ) -> ExecutionStatus:
        execution = ExecutionStatus(
            session_key=session_key,
            execution_id=execution_id or uuid4().hex,
            channel=channel,
            backend=backend,
        )
        self._active_by_id[execution.execution_id] = execution
        self._active_by_session[session_key] = execution.execution_id
        return execution

    def finish_execution(self, execution_id: str) -> None:
        execution = self._active_by_id.pop(execution_id, None)
        if execution is None:
            return
        current_active = self._active_by_session.get(execution.session_key)
        if current_active == execution_id:
            self._active_by_session.pop(execution.session_key, None)
        self._completed_by_id[execution.execution_id] = execution
        while len(self._completed_by_id) > _MAX_COMPLETED:
            self._completed_by_id.popitem(last=False)

    def get_active(self, execution_id: str) -> ExecutionStatus | None:
        return self._active_by_id.get(execution_id)

    def get_active_for_session(self, session_key: str) -> ExecutionStatus | None:
        execution_id = self._active_by_session.get(session_key)
        if execution_id is None:
            return None
        return self._active_by_id.get(execution_id)

    def list_active(self) -> list[ExecutionStatus]:
        return list(self._active_by_id.values())

    def get_completed(self, execution_id: str) -> ExecutionStatus | None:
        return self._completed_by_id.get(execution_id)

    def get_latest_completed_for_session(
        self, session_key: str
    ) -> ExecutionStatus | None:
        for execution in reversed(self._completed_by_id.values()):
            if execution.session_key == session_key:
                return execution
        return None

    def list_completed(self) -> list[ExecutionStatus]:
        return list(reversed(self._completed_by_id.values()))

    def list_for_session(
        self,
        session_key: str,
        *,
        limit: int = 20,
    ) -> list[ExecutionStatus]:
        items: list[ExecutionStatus] = []
        active = self.get_active_for_session(session_key)
        if active is not None:
            items.append(active)
        for execution in reversed(self._completed_by_id.values()):
            if execution.session_key != session_key:
                continue
            items.append(execution)
            if len(items) >= limit:
                break
        return items


_tracker: ExecutionTracker | None = None


def get_tracker() -> ExecutionTracker:
    global _tracker
    if _tracker is None:
        _tracker = ExecutionTracker()
    return _tracker
