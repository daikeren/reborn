from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

TELEGRAM_PENDING_NEW = "__pending_new__"
PENDING_SDK_SESSION_ID = "__pending_sdk_session__"


@dataclass
class SessionRecord:
    session_key: str
    sdk_session_id: str
    created_at: str  # ISO 8601
    last_active: str  # ISO 8601
    chat_key: str | None = None
    message_count: int = 0
    first_user_message: str | None = None


@dataclass
class MessageRecord:
    id: int
    session_key: str
    sdk_session_id: str | None
    role: str
    content: str
    created_at: str  # ISO 8601


class SessionStore:
    """SQLite-backed session store with WAL mode for concurrent safety."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_key TEXT PRIMARY KEY,
                sdk_session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_active TEXT NOT NULL,
                chat_key TEXT
            )
        """)
        self._conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """Run in-place schema migrations for pre-existing DBs."""
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "message_count" not in cols:
            self._conn.execute(
                "ALTER TABLE sessions ADD COLUMN message_count INTEGER NOT NULL DEFAULT 0"
            )
        if "chat_key" not in cols:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN chat_key TEXT")

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS telegram_chat_state (
                chat_key TEXT PRIMARY KEY,
                conversation_key TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_chat_key_last_active
            ON sessions(chat_key, last_active)
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT NOT NULL,
                sdk_session_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session_created_at
            ON messages(session_key, created_at)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_created_at
            ON messages(created_at)
        """)
        self._conn.commit()

    def get(self, session_key: str) -> SessionRecord | None:
        row = self._conn.execute(
            "SELECT session_key, sdk_session_id, created_at, last_active, chat_key, message_count "
            "FROM sessions WHERE session_key = ?",
            (session_key,),
        ).fetchone()
        if row is None:
            return None
        return self._session_record_from_row(row)

    def upsert(
        self,
        session_key: str,
        sdk_session_id: str,
        *,
        chat_key: str | None = None,
    ) -> SessionRecord:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO sessions (session_key, sdk_session_id, created_at, last_active, chat_key, message_count)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(session_key) DO UPDATE SET
                sdk_session_id = excluded.sdk_session_id,
                chat_key = COALESCE(excluded.chat_key, sessions.chat_key),
                last_active = excluded.last_active
            """,
            (session_key, sdk_session_id, now, now, chat_key),
        )
        self._conn.commit()
        rec = self.get(session_key)
        assert rec is not None
        return rec

    def create_placeholder_session(
        self,
        session_key: str,
        *,
        chat_key: str | None = None,
    ) -> SessionRecord:
        return self.upsert(
            session_key,
            PENDING_SDK_SESSION_ID,
            chat_key=chat_key,
        )

    def count_sessions(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
        return int(row[0]) if row else 0

    def count_session_summaries(
        self,
        *,
        channel: str | None = None,
        query: str | None = None,
    ) -> int:
        clauses = ["1 = 1"]
        params: list[object] = []
        if channel:
            clauses.append(self._channel_clause(channel))
        if query:
            clauses.append(
                """(
                    s.session_key LIKE ?
                    OR COALESCE(s.chat_key, '') LIKE ?
                    OR COALESCE((
                        SELECT m.content
                        FROM messages m
                        WHERE m.session_key = s.session_key AND m.role = 'user'
                        ORDER BY m.id ASC
                        LIMIT 1
                    ), '') LIKE ?
                )"""
            )
            pattern = f"%{query}%"
            params.extend([pattern, pattern, pattern])
        row = self._conn.execute(
            f"SELECT COUNT(*) FROM sessions s WHERE {' AND '.join(clauses)}",
            params,
        ).fetchone()
        return int(row[0]) if row else 0

    def list_sessions(self, limit: int = 100, offset: int = 0) -> list[SessionRecord]:
        rows = self._conn.execute(
            """
            SELECT session_key, sdk_session_id, created_at, last_active, chat_key, message_count
            FROM sessions
            ORDER BY last_active DESC
            LIMIT ?
            OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [self._session_record_from_row(row) for row in rows]

    def list_session_summaries(
        self, limit: int = 100, offset: int = 0
    ) -> list[SessionRecord]:
        return self.search_session_summaries(limit=limit, offset=offset)

    def search_session_summaries(
        self,
        *,
        channel: str | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SessionRecord]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if channel:
            clauses.append(self._channel_clause(channel))
        if query:
            clauses.append(
                """(
                    s.session_key LIKE ?
                    OR COALESCE(s.chat_key, '') LIKE ?
                    OR COALESCE((
                        SELECT m.content
                        FROM messages m
                        WHERE m.session_key = s.session_key AND m.role = 'user'
                        ORDER BY m.id ASC
                        LIMIT 1
                    ), '') LIKE ?
                )"""
            )
            pattern = f"%{query}%"
            params.extend([pattern, pattern, pattern])
        params.extend([limit, offset])
        rows = self._conn.execute(
            f"""
            SELECT
                s.session_key,
                s.sdk_session_id,
                s.created_at,
                s.last_active,
                s.chat_key,
                s.message_count,
                (
                    SELECT m.content
                    FROM messages m
                    WHERE m.session_key = s.session_key AND m.role = 'user'
                    ORDER BY m.id ASC
                    LIMIT 1
                ) AS first_user_message
            FROM sessions s
            WHERE {" AND ".join(clauses)}
            ORDER BY s.last_active DESC
            LIMIT ?
            OFFSET ?
            """,
            params,
        ).fetchall()
        return [self._session_record_from_summary_row(row) for row in rows]

    def increment_message_count(self, session_key: str) -> int:
        """Increment message_count and return the new value."""
        self._conn.execute(
            "UPDATE sessions SET message_count = message_count + 1 WHERE session_key = ?",
            (session_key,),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT message_count FROM sessions WHERE session_key = ?",
            (session_key,),
        ).fetchone()
        return row[0] if row else 0

    def append_message(
        self,
        session_key: str,
        role: str,
        content: str,
        *,
        sdk_session_id: str | None = None,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO messages (session_key, sdk_session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_key, sdk_session_id, role, content, created_at),
        )
        self._conn.commit()

    def get_messages(self, session_key: str, limit: int = 200) -> list[MessageRecord]:
        rows = self._conn.execute(
            """
            SELECT id, session_key, sdk_session_id, role, content, created_at
            FROM messages
            WHERE session_key = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_key, limit),
        ).fetchall()
        rows.reverse()
        return [MessageRecord(*row) for row in rows]

    def query_messages(
        self,
        *,
        session_key: str,
        limit: int = 200,
        since: str | None = None,
    ) -> list[MessageRecord]:
        if since:
            rows = self._conn.execute(
                """
                SELECT id, session_key, sdk_session_id, role, content, created_at
                FROM messages
                WHERE session_key = ? AND created_at >= ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_key, since, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT id, session_key, sdk_session_id, role, content, created_at
                FROM messages
                WHERE session_key = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_key, limit),
            ).fetchall()
        rows.reverse()
        return [MessageRecord(*row) for row in rows]

    def query_recent_messages(
        self,
        *,
        limit: int = 500,
        since: str | None = None,
        exclude_session_prefixes: tuple[str, ...] = (),
    ) -> list[MessageRecord]:
        where = []
        params: list[str | int] = []
        if since:
            where.append("created_at >= ?")
            params.append(since)
        for prefix in exclude_session_prefixes:
            where.append("session_key NOT LIKE ?")
            params.append(f"{prefix}%")

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        rows = self._conn.execute(
            f"""
            SELECT id, session_key, sdk_session_id, role, content, created_at
            FROM messages
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        rows.reverse()
        return [MessageRecord(*row) for row in rows]

    def get_active_stats(self) -> dict:
        """Return aggregate stats for sessions active within the last 24 hours.

        Returns dict with active_sessions count and max_message_count.
        No session keys or SDK IDs are exposed.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        row = self._conn.execute(
            """
            SELECT COUNT(*), COALESCE(MAX(message_count), 0)
            FROM sessions
            WHERE last_active > ?
            """,
            (cutoff,),
        ).fetchone()
        return {
            "active_sessions": row[0],
            "max_message_count": row[1],
        }

    def get_active_telegram_conversation(self, chat_key: str) -> str | None:
        row = self._conn.execute(
            "SELECT conversation_key FROM telegram_chat_state WHERE chat_key = ?",
            (chat_key,),
        ).fetchone()
        return str(row[0]) if row else None

    def set_active_telegram_conversation(
        self, chat_key: str, conversation_key: str
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO telegram_chat_state (chat_key, conversation_key, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_key) DO UPDATE SET
                conversation_key = excluded.conversation_key,
                updated_at = excluded.updated_at
            """,
            (chat_key, conversation_key, now),
        )
        self._conn.commit()

    def clear_active_telegram_conversation(self, chat_key: str) -> None:
        self._conn.execute(
            "DELETE FROM telegram_chat_state WHERE chat_key = ?",
            (chat_key,),
        )
        self._conn.commit()

    def mark_telegram_session_reset(self, chat_key: str) -> None:
        self.set_active_telegram_conversation(chat_key, TELEGRAM_PENDING_NEW)

    def touch(self, session_key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE sessions SET last_active = ? WHERE session_key = ?",
            (now, session_key),
        )
        self._conn.commit()

    def delete(self, session_key: str) -> None:
        self._conn.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _infer_chat_key(session_key: str, chat_key: str | None) -> str | None:
        if chat_key:
            return chat_key
        if session_key.startswith("telegram:chat:"):
            return session_key
        return None

    @staticmethod
    def _channel_clause(channel: str) -> str:
        if channel == "telegram":
            return "(s.session_key LIKE 'telegram:%' OR COALESCE(s.chat_key, '') LIKE 'telegram:%')"
        if channel == "slack":
            return "s.session_key LIKE 'slack:%'"
        if channel == "scheduler":
            return "s.session_key LIKE 'scheduler:%'"
        if channel == "web":
            return "s.session_key LIKE 'web:%'"
        return "1 = 0"

    def _session_record_from_row(self, row) -> SessionRecord:
        (
            session_key,
            sdk_session_id,
            created_at,
            last_active,
            chat_key,
            message_count,
        ) = row
        return SessionRecord(
            session_key=session_key,
            sdk_session_id=sdk_session_id,
            created_at=created_at,
            last_active=last_active,
            chat_key=self._infer_chat_key(session_key, chat_key),
            message_count=message_count,
        )

    def _session_record_from_summary_row(self, row) -> SessionRecord:
        (
            session_key,
            sdk_session_id,
            created_at,
            last_active,
            chat_key,
            message_count,
            first_user_message,
        ) = row
        return SessionRecord(
            session_key=session_key,
            sdk_session_id=sdk_session_id,
            created_at=created_at,
            last_active=last_active,
            chat_key=self._infer_chat_key(session_key, chat_key),
            message_count=message_count,
            first_user_message=first_user_message,
        )
