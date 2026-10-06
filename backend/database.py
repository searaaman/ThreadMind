import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.getenv(
    "THREADMIND_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "threadmind.db"),
)


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(user_id, updated_at);

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, id);

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
            """
        )
        migrate_legacy_conversations(conn)


def migrate_legacy_conversations(conn):
    """Move rows from the old flat `conversations` table into one thread per user."""
    legacy = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'"
    ).fetchone()
    if not legacy:
        return

    rows = conn.execute(
        "SELECT user_id, role, message FROM conversations ORDER BY id"
    ).fetchall()
    thread_ids = {}
    for row in rows:
        user_id = row["user_id"] or "default"
        if user_id not in thread_ids:
            ts = now()
            cur = conn.execute(
                "INSERT INTO threads (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (user_id, "Imported conversation", ts, ts),
            )
            thread_ids[user_id] = cur.lastrowid
        role = "user" if (row["role"] or "").lower() == "user" else "assistant"
        conn.execute(
            "INSERT INTO messages (thread_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (thread_ids[user_id], role, row["message"] or "", now()),
        )
    conn.execute("DROP TABLE conversations")


# Threads

def list_threads(user_id):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.*, (SELECT COUNT(*) FROM messages m WHERE m.thread_id = t.id) AS message_count
            FROM threads t
            WHERE t.user_id = ?
            ORDER BY t.updated_at DESC, t.id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_thread(user_id, thread_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM threads WHERE id = ? AND user_id = ?", (thread_id, user_id)
        ).fetchone()
    return dict(row) if row else None


def create_thread(user_id, title="New chat"):
    ts = now()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO threads (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, title, ts, ts),
        )
        thread_id = cur.lastrowid
    return get_thread(user_id, thread_id)


def rename_thread(user_id, thread_id, title):
    with connect() as conn:
        conn.execute(
            "UPDATE threads SET title = ? WHERE id = ? AND user_id = ?",
            (title, thread_id, user_id),
        )
    return get_thread(user_id, thread_id)


def delete_thread(user_id, thread_id):
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM threads WHERE id = ? AND user_id = ?", (thread_id, user_id)
        )
    return cur.rowcount > 0


# Messages

def get_messages(thread_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM messages WHERE thread_id = ? ORDER BY id",
            (thread_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_message(thread_id, role, content):
    ts = now()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (thread_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (thread_id, role, content, ts),
        )
        conn.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (ts, thread_id))
        message_id = cur.lastrowid
    return {"id": message_id, "role": role, "content": content, "created_at": ts}


def delete_last_assistant_message(thread_id):
    """Drop the trailing assistant reply so it can be regenerated."""
    with connect() as conn:
        last = conn.execute(
            "SELECT id, role FROM messages WHERE thread_id = ? ORDER BY id DESC LIMIT 1",
            (thread_id,),
        ).fetchone()
        if last and last["role"] == "assistant":
            conn.execute("DELETE FROM messages WHERE id = ?", (last["id"],))


# Memories

def list_memories(user_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM memories WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_memory(user_id, content):
    ts = now()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO memories (user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content, ts),
        )
    return {"id": cur.lastrowid, "content": content, "created_at": ts}


def delete_memory(user_id, memory_id):
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id)
        )
    return cur.rowcount > 0


def clear_memories(user_id):
    with connect() as conn:
        conn.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
