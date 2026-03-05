from __future__ import annotations

import asyncio
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from loguru import logger

from app.channels.slack import create_slack_app
from app.channels.telegram import create_telegram_app
from app.config import settings
from app.history_ui import HISTORY_LIST_PAGE_HTML, render_history_detail_page
from app.logging import configure_logging
from app.monitoring.tracker import get_tracker
from app.monitoring.ui import MONITOR_PAGE_HTML
from app.scheduler import shutdown_scheduler, start_scheduler
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
    if shutil.which("gog") is None:
        logger.warning("gogcli (gog) not found on PATH; Google Workspace features will not work")

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
    logger.info("Session store initialized at {}", db_path)

    # Telegram (long polling in background task)
    tg_app = None
    if settings.telegram_enabled:
        tg_app = create_telegram_app(settings.telegram_bot_token, manager)
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
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
        _slack_app, slack_handler = create_slack_app(
            bot_token=settings.slack_bot_token,
            app_token=settings.slack_app_token,
            session_manager=manager,
        )
        slack_task = asyncio.create_task(slack_handler.start_async())
        logger.info("Slack Socket Mode started for allowed_user_id={}", settings.allowed_slack_user_id)
    else:
        logger.info("Slack channel disabled (no token configured)")

    # Scheduler (proactive jobs — requires Telegram for delivery)
    if tg_app is not None:
        await start_scheduler(tg_app.bot)
        logger.info("Scheduler startup completed")
    else:
        logger.info("Scheduler skipped (requires Telegram for delivery)")

    yield

    # --- Shutdown ---
    logger.info("Service shutdown started")
    shutdown_scheduler()
    if tg_app is not None:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
    if slack_handler is not None:
        await slack_handler.close_async()
    if slack_task is not None:
        slack_task.cancel()
    store.close()
    logger.info("Service shutdown complete")


app = FastAPI(title="Reeve", lifespan=lifespan)


def _store() -> SessionStore:
    store: SessionStore | None = getattr(app.state, "session_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Session store not ready")
    return store


@app.get("/health")
async def health():
    stats = _store().get_active_stats()
    return {"status": "ok", **stats}


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
                "sdk_session_id": s.sdk_session_id,
                "created_at": s.created_at,
                "last_active": s.last_active,
                "message_count": s.message_count,
                "first_user_message": s.first_user_message,
            }
            for s in sessions
        ]
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
    }


def _execution_detail(ex):
    return {
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
        "error_message": ex.error_message,
        "events": [
            {"kind": e.kind.value, "timestamp": e.timestamp, "data": e.data}
            for e in ex.events
        ],
    }


@app.get("/monitor", response_class=HTMLResponse)
async def monitor_page():
    return MONITOR_PAGE_HTML


@app.get("/api/monitor/active")
async def monitor_active():
    return [_execution_summary(ex) for ex in get_tracker().list_active()]


@app.get("/api/monitor/active/{session_key:path}")
async def monitor_active_detail(session_key: str):
    ex = get_tracker().get_active(session_key)
    if ex is None:
        raise HTTPException(status_code=404, detail="No active execution for this session")
    return _execution_detail(ex)


@app.get("/api/monitor/completed")
async def monitor_completed():
    return [_execution_summary(ex) for ex in get_tracker().list_completed()]


@app.get("/api/monitor/completed/{session_key:path}")
async def monitor_completed_detail(session_key: str):
    ex = get_tracker().get_completed(session_key)
    if ex is None:
        raise HTTPException(status_code=404, detail="No completed execution for this session")
    return _execution_detail(ex)
