from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from loguru import logger
from pydantic import BaseModel, Field

from app.agent.skills import inspect_skills
from app.channels.slack import create_slack_app
from app.channels.telegram import create_telegram_app
from app.config import settings
from app.dashboard_ui import DASHBOARD_PAGE_HTML
from app.history_ui import HISTORY_LIST_PAGE_HTML, render_history_detail_page
from app.logging import configure_logging
from app.monitoring.tracker import get_tracker
from app.monitoring.ui import MONITOR_PAGE_HTML
from app.orchestrator import ExecutionService, InteractiveExecutionRequest
from app.scheduler import shutdown_scheduler, start_scheduler
from app.scheduler.admin import (
    get_job_definition,
    list_job_definitions,
    save_job_definition,
)
from app.scheduler.prompts import JobPrompt
from app.scheduler.runner import reload_scheduler, run_job_now
from app.setup.engine import inspect_setup
from app.sessions.manager import SessionManager
from app.sessions.store import SessionStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info(
        "Service startup: workspace_dir={}, timezone={}, backend={}",
        settings.workspace_dir,
        settings.timezone,
        settings.agent_backend,
    )

    # --- Startup ---
    if not settings.telegram_enabled and not settings.slack_enabled:
        raise RuntimeError(
            "At least one channel must be configured. "
            "Set TELEGRAM_BOT_TOKEN + ALLOWED_TELEGRAM_USER_ID and/or "
            "SLACK_BOT_TOKEN + SLACK_APP_TOKEN + ALLOWED_SLACK_USER_ID in .env"
        )

    db_path = settings.workspace_dir / "sessions.db"
    store = SessionStore(db_path)
    app.state.session_store = store
    manager = SessionManager(store)
    app.state.session_manager = manager
    execution_service = ExecutionService(store, manager)
    app.state.execution_service = execution_service
    logger.info("Session store initialized at {}", db_path)

    # Telegram (long polling in background task)
    tg_app = None
    if settings.telegram_enabled:
        telegram_bot_token = settings.telegram_bot_token
        assert telegram_bot_token is not None
        tg_app = create_telegram_app(telegram_bot_token, manager, execution_service)
        await tg_app.initialize()
        await tg_app.start()
        updater = tg_app.updater
        if updater is None:
            raise RuntimeError("Telegram updater is unavailable")
        await updater.start_polling(drop_pending_updates=True)
        logger.info(
            "Telegram polling started for allowed_user_id={}",
            settings.allowed_telegram_user_id,
        )
    else:
        logger.info("Telegram channel disabled (no token configured)")

    # Slack (Socket Mode in background task)
    slack_handler = None
    slack_task = None
    if settings.slack_enabled:
        slack_bot_token = settings.slack_bot_token
        slack_app_token = settings.slack_app_token
        assert slack_bot_token is not None
        assert slack_app_token is not None
        _slack_app, slack_handler = create_slack_app(
            bot_token=slack_bot_token,
            app_token=slack_app_token,
            session_manager=manager,
            execution_service=execution_service,
        )
        slack_task = asyncio.create_task(slack_handler.start_async())
        logger.info(
            "Slack Socket Mode started for allowed_user_id={}",
            settings.allowed_slack_user_id,
        )
    else:
        logger.info("Slack channel disabled (no token configured)")

    # Scheduler (proactive jobs — requires Telegram for delivery)
    if tg_app is not None:
        await start_scheduler(tg_app.bot, execution_service)
        logger.info("Scheduler startup completed")
    else:
        logger.info("Scheduler skipped (requires Telegram for delivery)")

    yield

    # --- Shutdown ---
    logger.info("Service shutdown started")
    shutdown_scheduler()
    if tg_app is not None:
        updater = tg_app.updater
        if updater is not None:
            await updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
    if slack_handler is not None:
        await slack_handler.close_async()
    if slack_task is not None:
        slack_task.cancel()
    store.close()
    logger.info("Service shutdown complete")


app = FastAPI(title="Reborn", lifespan=lifespan)


class SendWebMessageRequest(BaseModel):
    message: str = Field(min_length=1)


class SendOperatorNoteRequest(BaseModel):
    note: str = Field(min_length=1)


class UpdateJobRequest(BaseModel):
    schedule: str | None = None
    tools: list[str] = Field(default_factory=list)
    max_turns: int = Field(default=10, ge=1)
    suppress_token: str | None = None
    enabled: bool = True
    prompt: str = Field(min_length=1)


def _store() -> SessionStore:
    store: SessionStore | None = getattr(app.state, "session_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Session store not ready")
    return store


def _manager() -> SessionManager:
    manager: SessionManager | None = getattr(app.state, "session_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Session manager not ready")
    return manager


def _execution_service() -> ExecutionService:
    execution_service: ExecutionService | None = getattr(
        app.state,
        "execution_service",
        None,
    )
    if execution_service is None:
        raise HTTPException(status_code=503, detail="Execution service not ready")
    return execution_service


def _channel_for_session(session_key: str, chat_key: str | None = None) -> str:
    base = chat_key or session_key
    if base.startswith("telegram:"):
        return "telegram"
    if base.startswith("slack:"):
        return "slack"
    if session_key.startswith("scheduler:"):
        return "scheduler"
    if session_key.startswith("web:"):
        return "web"
    return "default"


def _session_actions(session_key: str, chat_key: str | None = None) -> list[str]:
    channel = _channel_for_session(session_key, chat_key)
    if channel in {"web", "telegram"}:
        return ["reset"]
    return []


def _telegram_enabled() -> bool:
    enabled = getattr(settings, "telegram_enabled", None)
    if enabled is not None:
        return bool(enabled)
    return bool(
        getattr(settings, "telegram_bot_token", None)
        and getattr(settings, "allowed_telegram_user_id", None)
    )


def _slack_enabled() -> bool:
    enabled = getattr(settings, "slack_enabled", None)
    if enabled is not None:
        return bool(enabled)
    return bool(
        getattr(settings, "slack_bot_token", None)
        and getattr(settings, "slack_app_token", None)
        and getattr(settings, "allowed_slack_user_id", None)
    )


@app.get("/health")
async def health():
    stats = _store().get_active_stats()
    return {"status": "ok", **stats}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return DASHBOARD_PAGE_HTML


@app.get("/api/dashboard/overview")
async def dashboard_overview():
    tracker = get_tracker()
    return {
        "health": _store().get_active_stats(),
        "active_executions": len(tracker.list_active()),
        "completed_executions": len(tracker.list_completed()),
        "backend": settings.agent_backend,
        "chat_model": settings.chat_model,
        "background_model": settings.background_model,
        "workspace_dir": str(settings.workspace_dir),
        "timezone": settings.timezone,
        "channels": {
            "telegram": {
                "configured": _telegram_enabled(),
                "allowed_user_id": settings.allowed_telegram_user_id,
            },
            "slack": {
                "configured": _slack_enabled(),
                "allowed_user_id": settings.allowed_slack_user_id,
            },
        },
    }


@app.get("/api/dashboard/sessions")
async def dashboard_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    channel: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    store = _store()
    page_value = page if isinstance(page, int) else page.default
    page_size_value = page_size if isinstance(page_size, int) else page_size.default
    channel_value = channel if isinstance(channel, str) else None
    status_value = status if isinstance(status, str) else None
    normalized_q = q.strip() if isinstance(q, str) and q else None
    if status_value:
        base_total = store.count_session_summaries(
            channel=channel_value,
            query=normalized_q,
        )
        pool = store.search_session_summaries(
            channel=channel_value,
            query=normalized_q,
            limit=max(base_total, 1),
            offset=0,
        )
        filtered = [
            item
            for item in pool
            if _session_summary_payload(item)["execution_status"] == status_value
        ]
        total = len(filtered)
        total_pages = max(1, (total + page_size_value - 1) // page_size_value)
        safe_page = min(page_value, total_pages)
        offset = (safe_page - 1) * page_size_value
        sessions = filtered[offset : offset + page_size_value]
    else:
        total = store.count_session_summaries(
            channel=channel_value,
            query=normalized_q,
        )
        total_pages = max(1, (total + page_size_value - 1) // page_size_value)
        safe_page = min(page_value, total_pages)
        offset = (safe_page - 1) * page_size_value
        sessions = store.search_session_summaries(
            channel=channel_value,
            query=normalized_q,
            limit=page_size_value,
            offset=offset,
        )

    return {
        "page": safe_page,
        "page_size": page_size_value,
        "total": total,
        "total_pages": total_pages,
        "sessions": [_session_summary_payload(item) for item in sessions],
    }


@app.get("/api/dashboard/sessions/{session_key:path}")
async def dashboard_session_detail(session_key: str):
    store = _store()
    record = store.get(session_key)
    messages = store.query_messages(session_key=session_key, limit=500)
    tracker = get_tracker()
    summary = {
        "session_key": session_key,
        "chat_key": record.chat_key if record is not None else None,
        "sdk_session_id": record.sdk_session_id if record is not None else None,
        "created_at": record.created_at if record is not None else None,
        "last_active": record.last_active if record is not None else None,
        "message_count": record.message_count if record is not None else len(messages),
    }
    chat_key = record.chat_key if record is not None else None
    return {
        "session_key": session_key,
        "channel": _channel_for_session(session_key, chat_key),
        "summary": summary,
        "pending_question": _manager().has_pending_question(chat_key or session_key),
        "available_actions": _session_actions(session_key, chat_key),
        "messages": [
            {
                "id": m.id,
                "session_key": m.session_key,
                "sdk_session_id": m.sdk_session_id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in messages
        ],
        "executions": [
            _execution_summary(item) for item in tracker.list_for_session(session_key)
        ],
    }


@app.post("/api/dashboard/sessions/{session_key:path}/reset")
async def dashboard_reset_session(session_key: str):
    store = _store()
    record = store.get(session_key)
    channel = _channel_for_session(session_key, record.chat_key if record else None)
    if channel == "web":
        new_session_key = f"web:session:{uuid4().hex}"
        store.create_placeholder_session(new_session_key)
        return {"ok": True, "new_session_key": new_session_key}
    if channel == "telegram":
        reply = await _manager().reset_telegram_session(
            record.chat_key if record and record.chat_key else session_key
        )
        return {"ok": True, "message": reply}
    if channel == "slack":
        raise HTTPException(status_code=409, detail="Slack reset unsupported in MVP")
    raise HTTPException(
        status_code=400, detail="Reset is not available for this session"
    )


@app.post("/api/dashboard/web/sessions")
async def dashboard_create_web_session():
    session_key = f"web:session:{uuid4().hex}"
    _store().create_placeholder_session(session_key)
    return {"session_key": session_key}


@app.get("/api/dashboard/web/sessions/{session_key:path}")
async def dashboard_web_session_detail(session_key: str):
    if not session_key.startswith("web:session:"):
        raise HTTPException(status_code=404, detail="Not a web session")
    return await dashboard_session_detail(session_key)


@app.post("/api/dashboard/web/sessions/{session_key:path}/messages")
async def dashboard_send_web_message(
    session_key: str,
    body: SendWebMessageRequest,
):
    if not session_key.startswith("web:session:"):
        raise HTTPException(status_code=404, detail="Not a web session")
    if _store().get(session_key) is None:
        _store().create_placeholder_session(session_key)
    execution_id = _execution_service().start_interactive(
        InteractiveExecutionRequest(
            session_key=session_key,
            channel="web",
            message=body.message.strip(),
        )
    )
    return {"session_key": session_key, "execution_id": execution_id}


@app.post("/api/dashboard/web/sessions/{session_key:path}/notes")
async def dashboard_send_operator_note(
    session_key: str,
    body: SendOperatorNoteRequest,
):
    if not session_key.startswith("web:session:"):
        raise HTTPException(status_code=404, detail="Not a web session")
    if _store().get(session_key) is None:
        _store().create_placeholder_session(session_key)
    note_text = body.note.strip()
    execution_id = _execution_service().start_interactive(
        InteractiveExecutionRequest(
            session_key=session_key,
            channel="web",
            message=f"[Operator note from dashboard]\n{note_text}",
            persist_user_message=True,
            stored_role="note",
            stored_message=note_text,
        )
    )
    return {"session_key": session_key, "execution_id": execution_id}


@app.get("/api/dashboard/executions/{execution_id}")
async def dashboard_execution_detail(execution_id: str):
    execution = _execution_service().get_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    payload = _execution_detail(execution)
    payload["messages"] = [
        {
            "id": m.id,
            "session_key": m.session_key,
            "sdk_session_id": m.sdk_session_id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at,
        }
        for m in _store().query_messages(session_key=execution.session_key, limit=200)
    ]
    return payload


@app.post("/api/dashboard/executions/{execution_id}/cancel")
async def dashboard_cancel_execution(execution_id: str):
    cancelled = _execution_service().cancel_execution(execution_id)
    if not cancelled:
        raise HTTPException(status_code=409, detail="Execution is not running")
    return {"ok": True, "execution_id": execution_id}


@app.get("/api/dashboard/jobs")
async def dashboard_jobs():
    return {"jobs": [_job_payload(item) for item in list_job_definitions()]}


@app.get("/api/dashboard/jobs/{name}")
async def dashboard_job_detail(name: str):
    definition = get_job_definition(name)
    if definition is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_payload(definition)


@app.put("/api/dashboard/jobs/{name}")
async def dashboard_update_job(name: str, body: UpdateJobRequest):
    prompt = JobPrompt(
        prompt=body.prompt,
        tools=body.tools,
        max_turns=body.max_turns,
        suppress_token=body.suppress_token,
        schedule=body.schedule,
        enabled=body.enabled,
    )
    definition = save_job_definition(name, prompt)
    await reload_scheduler()
    return _job_payload(definition)


@app.post("/api/dashboard/jobs/{name}/run")
async def dashboard_run_job(name: str):
    if get_job_definition(name) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    ok = await run_job_now(name)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Scheduler is not available because Telegram delivery is disabled",
        )
    return {"ok": True, "name": name}


@app.post("/api/dashboard/jobs/{name}/enable")
async def dashboard_enable_job(name: str):
    definition = get_job_definition(name)
    if definition is None:
        raise HTTPException(status_code=404, detail="Job not found")
    saved = save_job_definition(
        name,
        JobPrompt(
            prompt=definition.prompt.prompt,
            tools=definition.prompt.tools,
            max_turns=definition.prompt.max_turns,
            suppress_token=definition.prompt.suppress_token,
            schedule=definition.prompt.schedule,
            enabled=True,
        ),
    )
    await reload_scheduler()
    return _job_payload(saved)


@app.post("/api/dashboard/jobs/{name}/disable")
async def dashboard_disable_job(name: str):
    definition = get_job_definition(name)
    if definition is None:
        raise HTTPException(status_code=404, detail="Job not found")
    saved = save_job_definition(
        name,
        JobPrompt(
            prompt=definition.prompt.prompt,
            tools=definition.prompt.tools,
            max_turns=definition.prompt.max_turns,
            suppress_token=definition.prompt.suppress_token,
            schedule=definition.prompt.schedule,
            enabled=False,
        ),
    )
    await reload_scheduler()
    return _job_payload(saved)


@app.get("/api/dashboard/config")
async def dashboard_config():
    inspection = asdict(inspect_setup())
    inspection["runtime"] = {
        "backend": settings.agent_backend,
        "workspace_dir": str(settings.workspace_dir),
        "timezone": settings.timezone,
        "chat_model": settings.chat_model,
        "background_model": settings.background_model,
        "telegram_enabled": _telegram_enabled(),
        "slack_enabled": _slack_enabled(),
    }
    return inspection


@app.get("/api/dashboard/skills")
async def dashboard_skills():
    return {
        "skills": [
            {
                "name": item.name,
                "path": str(item.path),
                "status": item.status,
                "description": item.description,
                "error": item.error,
            }
            for item in inspect_skills()
        ]
    }


@app.get("/history", response_class=HTMLResponse)
async def history_page():
    return HISTORY_LIST_PAGE_HTML


@app.get("/history/session/{session_key:path}", response_class=HTMLResponse)
async def history_detail_page(session_key: str):
    return render_history_detail_page(session_key)


@app.get("/api/history/sessions")
async def history_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    store = _store()
    total = store.count_sessions()
    total_pages = max(1, (total + page_size - 1) // page_size)
    safe_page = min(page, total_pages)
    offset = (safe_page - 1) * page_size
    sessions = store.list_session_summaries(limit=page_size, offset=offset)
    return {
        "page": safe_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "sessions": [
            {
                "session_key": s.session_key,
                "chat_key": s.chat_key,
                "sdk_session_id": s.sdk_session_id,
                "created_at": s.created_at,
                "last_active": s.last_active,
                "message_count": s.message_count,
                "first_user_message": s.first_user_message,
            }
            for s in sessions
        ],
    }


@app.get("/api/history/messages")
async def history_messages(
    session_key: str = Query(...),
    limit: int = Query(default=200, ge=1, le=2000),
    since: str | None = Query(default=None),
):
    messages = _store().query_messages(
        session_key=session_key,
        limit=limit,
        since=since,
    )
    return {
        "messages": [
            {
                "id": m.id,
                "session_key": m.session_key,
                "sdk_session_id": m.sdk_session_id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in messages
        ]
    }


# --- Monitoring ---


def _execution_summary(ex):
    return {
        "execution_id": ex.execution_id,
        "session_key": ex.session_key,
        "channel": ex.channel,
        "backend": ex.backend,
        "started_at": ex.started_at,
        "status": ex.status,
        "current_turn": ex.current_turn,
        "tools_used": ex.tools_used,
        "event_count": len(ex.events),
        "completed_at": ex.completed_at,
        "elapsed_ms": ex.elapsed_ms,
        "partial_reply": ex.partial_reply,
    }


def _execution_detail(ex):
    return {
        "execution_id": ex.execution_id,
        "session_key": ex.session_key,
        "channel": ex.channel,
        "backend": ex.backend,
        "started_at": ex.started_at,
        "status": ex.status,
        "current_turn": ex.current_turn,
        "tools_used": ex.tools_used,
        "completed_at": ex.completed_at,
        "elapsed_ms": ex.elapsed_ms,
        "reply_preview": ex.reply_preview,
        "partial_reply": ex.partial_reply,
        "error_message": ex.error_message,
        "events": [
            {"kind": e.kind.value, "timestamp": e.timestamp, "data": e.data}
            for e in ex.events
        ],
    }


def _session_summary_payload(summary) -> dict:
    tracker = get_tracker()
    active = tracker.get_active_for_session(summary.session_key)
    latest = active or tracker.get_latest_completed_for_session(summary.session_key)
    channel = _channel_for_session(summary.session_key, summary.chat_key)
    return {
        "session_key": summary.session_key,
        "chat_key": summary.chat_key,
        "sdk_session_id": summary.sdk_session_id,
        "created_at": summary.created_at,
        "last_active": summary.last_active,
        "message_count": summary.message_count,
        "first_user_message": summary.first_user_message,
        "channel": channel,
        "execution_status": latest.status if latest is not None else "idle",
        "last_execution_id": latest.execution_id if latest is not None else None,
    }


def _job_payload(defn) -> dict:
    tracker = get_tracker()
    last_execution = tracker.get_latest_completed_for_session(f"scheduler:{defn.name}")
    return {
        "name": defn.name,
        "source": defn.source,
        "path": str(defn.path),
        "schedule": defn.prompt.schedule,
        "tools": defn.prompt.tools,
        "max_turns": defn.prompt.max_turns,
        "suppress_token": defn.prompt.suppress_token,
        "enabled": defn.prompt.enabled,
        "prompt": defn.prompt.prompt,
        "last_execution": (
            _execution_summary(last_execution) if last_execution is not None else None
        ),
    }


@app.get("/monitor", response_class=HTMLResponse)
async def monitor_page():
    return MONITOR_PAGE_HTML


@app.get("/api/monitor/active")
async def monitor_active():
    return [_execution_summary(ex) for ex in get_tracker().list_active()]


@app.get("/api/monitor/active/{session_key:path}")
async def monitor_active_detail(session_key: str):
    ex = get_tracker().get_active_for_session(session_key)
    if ex is None:
        raise HTTPException(
            status_code=404, detail="No active execution for this session"
        )
    return _execution_detail(ex)


@app.get("/api/monitor/completed")
async def monitor_completed():
    return [_execution_summary(ex) for ex in get_tracker().list_completed()]


@app.get("/api/monitor/completed/{session_key:path}")
async def monitor_completed_detail(session_key: str):
    ex = get_tracker().get_latest_completed_for_session(session_key)
    if ex is None:
        raise HTTPException(
            status_code=404, detail="No completed execution for this session"
        )
    return _execution_detail(ex)
