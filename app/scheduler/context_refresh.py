from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.agent.skills import load_all_skills
from app.sessions.store import SessionStore

CONTEXT_REFRESH_JOB = "context_refresh"
CONTEXT_REFRESH_WINDOW_DAYS = 7
CONTEXT_REFRESH_MAX_MESSAGES = 250


def build_context_refresh_prompt(
    base_prompt: str,
    store: SessionStore,
    *,
    now: datetime | None = None,
) -> str:
    history = build_recent_history(store, now=now)
    skills = build_skill_summaries()
    return f"{history}\n\n{skills}\n\n{base_prompt}"


def build_recent_history(
    store: SessionStore,
    *,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=CONTEXT_REFRESH_WINDOW_DAYS)).isoformat()
    messages = store.query_recent_messages(
        since=cutoff,
        limit=CONTEXT_REFRESH_MAX_MESSAGES,
        exclude_session_prefixes=("scheduler:",),
    )

    lines = ["## Recent Message History"]
    if not messages:
        lines.append("- No recent non-scheduler messages found in the last 7 days.")
        return "\n".join(lines)

    for message in messages:
        content = _squash_whitespace(message.content)
        lines.append(
            f"- [{message.created_at}] [{message.session_key}] [{message.role}] {content}"
        )
    return "\n".join(lines)


def build_skill_summaries() -> str:
    skills = load_all_skills()
    lines = ["## Available Skill Summaries"]
    if not skills:
        lines.append("- No installed skills were found.")
        return "\n".join(lines)

    for name, definition in skills.items():
        description = _squash_whitespace(definition.description)
        lines.append(f"- {name}: {description}")
    return "\n".join(lines)


def _squash_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
