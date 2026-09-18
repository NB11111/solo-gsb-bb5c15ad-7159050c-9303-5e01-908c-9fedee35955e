"""SQLite 连接管理与初始化。"""
import os
import sqlite3
from contextlib import contextmanager

# 默认把数据库放在工作目录的 data/ 下，容器中通过挂载卷持久化
DB_PATH = os.environ.get("AUDIT_DB_PATH", os.path.join("data", "audit.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    from_party  TEXT NOT NULL,
    to_party    TEXT NOT NULL,
    location    TEXT,
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (sample_id) REFERENCES samples (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_sample ON events (sample_id);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """启动时调用：确保数据目录与表结构存在。"""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ---------- samples ----------

def create_sample(conn: sqlite3.Connection, code: str, name: str,
                  description: str | None) -> sqlite3.Row:
    cur = conn.execute(
        "INSERT INTO samples (code, name, description) VALUES (?, ?, ?)",
        (code, name, description),
    )
    return conn.execute("SELECT * FROM samples WHERE id = ?",
                        (cur.lastrowid,)).fetchone()


def list_samples(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM samples ORDER BY created_at DESC, id DESC"
    ).fetchall()


def get_sample(conn: sqlite3.Connection, sample_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM samples WHERE id = ?",
                        (sample_id,)).fetchone()


def update_sample(conn: sqlite3.Connection, sample_id: int, code: str,
                  name: str, description: str | None) -> sqlite3.Row | None:
    conn.execute(
        "UPDATE samples SET code = ?, name = ?, description = ? WHERE id = ?",
        (code, name, description, sample_id),
    )
    return get_sample(conn, sample_id)


def delete_sample(conn: sqlite3.Connection, sample_id: int) -> None:
    conn.execute("DELETE FROM samples WHERE id = ?", (sample_id,))


# ---------- events ----------

def create_event(conn: sqlite3.Connection, sample_id: int, occurred_at: str,
                 from_party: str, to_party: str, location: str | None,
                 note: str | None) -> sqlite3.Row:
    cur = conn.execute(
        """INSERT INTO events
           (sample_id, occurred_at, from_party, to_party, location, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (sample_id, occurred_at, from_party, to_party, location, note),
    )
    return get_event(conn, cur.lastrowid)


def list_events(conn: sqlite3.Connection, sample_id: int) -> list[sqlite3.Row]:
    # id 顺序即录入顺序，审计模块据此判断“逆序”
    return conn.execute(
        "SELECT * FROM events WHERE sample_id = ? ORDER BY id", (sample_id,)
    ).fetchall()


def get_event(conn: sqlite3.Connection, event_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM events WHERE id = ?",
                        (event_id,)).fetchone()


def update_event(conn: sqlite3.Connection, event_id: int, occurred_at: str,
                 from_party: str, to_party: str, location: str | None,
                 note: str | None) -> sqlite3.Row | None:
    conn.execute(
        """UPDATE events SET occurred_at = ?, from_party = ?, to_party = ?,
           location = ?, note = ? WHERE id = ?""",
        (occurred_at, from_party, to_party, location, note, event_id),
    )
    return get_event(conn, event_id)


def delete_event(conn: sqlite3.Connection, event_id: int) -> None:
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
