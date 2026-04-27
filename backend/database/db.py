from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS phrase_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                original TEXT NOT NULL,
                corrected TEXT NOT NULL,
                explanation TEXT NOT NULL,
                response TEXT NOT NULL,
                repeat_json TEXT NOT NULL,
                mode TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS struggle_words (
                user_id TEXT NOT NULL,
                word TEXT NOT NULL,
                mistake_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY(user_id, word),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS learned_words (
                user_id TEXT NOT NULL,
                word TEXT NOT NULL,
                uses_count INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY(user_id, word),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );
            """
        )


def ensure_user(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, created_at) VALUES (?, ?)",
        (user_id, _utc_now()),
    )


def save_message(user_id: str, role: str, content: str) -> None:
    with get_connection() as conn:
        ensure_user(conn, user_id)
        conn.execute(
            """
            INSERT INTO conversation_messages (user_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, role, content, _utc_now()),
        )


def get_recent_messages(user_id: str, limit: int = 10) -> list[dict[str, str]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM conversation_messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    return [dict(row) for row in reversed(rows)]


def save_attempt(
    user_id: str,
    original: str,
    corrected: str,
    explanation: str,
    response: str,
    repeat: list[str],
    mode: str,
) -> None:
    with get_connection() as conn:
        ensure_user(conn, user_id)
        conn.execute(
            """
            INSERT INTO phrase_attempts
                (user_id, original, corrected, explanation, response, repeat_json, mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                original,
                corrected,
                explanation,
                response,
                json.dumps(repeat),
                mode,
                _utc_now(),
            ),
        )


def increment_struggle_words(user_id: str, words: list[str]) -> None:
    if not words:
        return

    with get_connection() as conn:
        ensure_user(conn, user_id)
        for word in words:
            conn.execute(
                """
                INSERT INTO struggle_words (user_id, word, mistake_count, last_seen_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, word)
                DO UPDATE SET
                    mistake_count = mistake_count + 1,
                    last_seen_at = excluded.last_seen_at
                """,
                (user_id, word, _utc_now()),
            )


def increment_learned_words(user_id: str, words: list[str]) -> None:
    if not words:
        return

    with get_connection() as conn:
        ensure_user(conn, user_id)
        for word in words:
            conn.execute(
                """
                INSERT INTO learned_words (user_id, word, uses_count, last_seen_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, word)
                DO UPDATE SET
                    uses_count = uses_count + 1,
                    last_seen_at = excluded.last_seen_at
                """,
                (user_id, word, _utc_now()),
            )


def get_struggle_words(user_id: str, limit: int = 6) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT word
            FROM struggle_words
            WHERE user_id = ?
            ORDER BY mistake_count DESC, last_seen_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    return [row["word"] for row in rows]


def get_progress(user_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_user(conn, user_id)
        stats = conn.execute(
            """
            SELECT
                COUNT(*) AS phrases,
                SUM(
                    CASE
                        WHEN LOWER(TRIM(original)) != LOWER(TRIM(corrected))
                        THEN 1 ELSE 0
                    END
                ) AS corrections
            FROM phrase_attempts
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        struggles = conn.execute(
            """
            SELECT word, mistake_count
            FROM struggle_words
            WHERE user_id = ?
            ORDER BY mistake_count DESC, last_seen_at DESC
            LIMIT 12
            """,
            (user_id,),
        ).fetchall()

        learned = conn.execute(
            """
            SELECT word, uses_count
            FROM learned_words
            WHERE user_id = ?
            ORDER BY uses_count DESC, last_seen_at DESC
            LIMIT 12
            """,
            (user_id,),
        ).fetchall()

    return {
        "user_id": user_id,
        "stats": {
            "phrases": stats["phrases"] or 0,
            "corrections": stats["corrections"] or 0,
        },
        "struggle_words": [dict(row) for row in struggles],
        "learned_words": [dict(row) for row in learned],
    }
