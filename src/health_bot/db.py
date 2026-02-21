import sqlite3
from pathlib import Path

def _ensure_user_columns(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}

    if "reminders_enabled" not in cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN reminders_enabled INTEGER NOT NULL DEFAULT 1"
        )

    if "reminder_time" not in cols:
        # HH:MM in user's timezone
        conn.execute("ALTER TABLE users ADD COLUMN reminder_time TEXT")

def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_db(conn: sqlite3.Connection, schema_path: str = "db/schema.sql") -> None:
    schema = Path(schema_path).read_text(encoding="utf-8")
    conn.executescript(schema)
    _ensure_user_columns(conn)
    conn.commit()