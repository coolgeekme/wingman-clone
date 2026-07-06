import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Message:
    role: str
    content: str
    session_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ConversationMemory:
    """SQLite-backed persistent conversation memory with session support."""

    def __init__(self, db_path: str = "./data/conversations.db", max_messages: int = 50):
        self._db_path = db_path
        self._max_messages = max_messages
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id, id)
            """)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def create_session(self, title: str = "") -> str:
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (session_id, title, now, now)
                )
                conn.commit()
        return session_id

    def list_sessions(self) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT session_id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT session_id, title, created_at, updated_at FROM sessions WHERE session_id = ?",
                (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                cursor = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return cursor.rowcount > 0

    def add(self, role: str, content: str, session_id: Optional[str] = None) -> str:
        if not session_id:
            session_id = self._get_or_create_default_session()
        
        msg = Message(role=role, content=content, session_id=session_id)
        now = datetime.utcnow().isoformat()

        with self._lock:
            with self._get_conn() as conn:
                # Ensure session exists
                existing = conn.execute(
                    "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (session_id, "", now, now)
                    )

                conn.execute(
                    "INSERT INTO messages (message_id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (msg.message_id, session_id, role, content, msg.timestamp)
                )
                # Auto-title: use first user message
                if role == "user":
                    sess = conn.execute(
                        "SELECT title FROM sessions WHERE session_id = ?", (session_id,)
                    ).fetchone()
                    if sess and not sess["title"]:
                        title = content[:80].strip()
                        conn.execute(
                            "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                            (title, now, session_id)
                        )
                    else:
                        conn.execute(
                            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                            (now, session_id)
                        )
                else:
                    conn.execute(
                        "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                        (now, session_id)
                    )
                conn.commit()

        return msg.message_id

    def get_history(self, session_id: Optional[str] = None, limit: Optional[int] = None) -> list[dict]:
        effective_limit = limit or self._max_messages
        if not session_id:
            session_id = self._get_or_create_default_session()

        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content, timestamp, message_id FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, effective_limit)
            ).fetchall()

        messages = [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"], "message_id": r["message_id"]} for r in reversed(rows)]
        return messages

    def clear(self, session_id: Optional[str] = None) -> None:
        with self._lock:
            with self._get_conn() as conn:
                if session_id:
                    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                else:
                    conn.execute("DELETE FROM messages")
                conn.commit()

    def _get_or_create_default_session(self) -> str:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT session_id FROM sessions ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            if row:
                return row["session_id"]
        return self.create_session(title="Default")

    def __len__(self) -> int:
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM messages").fetchone()
        return row["cnt"] if row else 0
