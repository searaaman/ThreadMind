import sqlite3

conn = sqlite3.connect("threadmind.db")

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    role TEXT,
    message TEXT
)
""")

conn.commit()
conn.close()

def save_message(user_id, role, message):
    conn = sqlite3.connect("threadmind.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO conversations (user_id, role, message)
        VALUES (?, ?, ?)
        """,
        (user_id, role, message)
    )

    conn.commit()
    conn.close()

def get_history(user_id):
    conn = sqlite3.connect("threadmind.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, message
        FROM conversations
        WHERE user_id = ?
        """,
        (user_id,)
    )

    rows = cursor.fetchall()

    conn.close()

    history = []

    for role, message in rows:
        history.append(f"{role}: {message}")

    return history