from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect persisted session/message history from sessions.db",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("workspace/sessions.db"),
        help="Path to sqlite database (default: workspace/sessions.db)",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List recent sessions from sessions table",
    )
    parser.add_argument(
        "--session-key",
        type=str,
        default=None,
        help="Filter messages by session_key",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max rows to show (default: 100)",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Only include messages created_at >= this ISO timestamp",
    )
    return parser.parse_args()


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def list_sessions(conn: sqlite3.Connection, limit: int) -> int:
    rows = conn.execute(
        """
        SELECT session_key, sdk_session_id, created_at, last_active, message_count
        FROM sessions
        ORDER BY last_active DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    if not rows:
        print("No sessions found.")
        return 0

    print("session_key\tsdk_session_id\tcreated_at\tlast_active\tmessage_count")
    for row in rows:
        print(
            f"{row['session_key']}\t{row['sdk_session_id']}\t{row['created_at']}\t"
            f"{row['last_active']}\t{row['message_count']}"
        )
    return 0


def list_messages(
    conn: sqlite3.Connection,
    *,
    session_key: str | None,
    since: str | None,
    limit: int,
) -> int:
    if not table_exists(conn, "messages"):
        print("messages table not found. This DB predates history persistence.")
        return 0

    where: list[str] = []
    params: list[str | int] = []

    if session_key:
        where.append("session_key = ?")
        params.append(session_key)
    if since:
        where.append("created_at >= ?")
        params.append(since)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)

    rows = conn.execute(
        f"""
        SELECT id, session_key, sdk_session_id, role, content, created_at
        FROM messages
        {where_sql}
        ORDER BY id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()

    if not rows:
        print("No messages found.")
        return 0

    for row in reversed(rows):
        sdk = row["sdk_session_id"] or "-"
        print(
            f"[{row['created_at']}] {row['session_key']} {row['role']} "
            f"(sdk_session_id={sdk})"
        )
        print(row["content"])
        print("-" * 80)

    return 0


def main() -> int:
    args = parse_args()

    if args.limit <= 0:
        print("--limit must be > 0", file=sys.stderr)
        return 2

    db_path = args.db
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        if args.list_sessions:
            return list_sessions(conn, args.limit)
        return list_messages(
            conn,
            session_key=args.session_key,
            since=args.since,
            limit=args.limit,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
