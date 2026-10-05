import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS dnc (
    phone TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS calls (
    call_uuid TEXT PRIMARY KEY,
    phone TEXT NOT NULL,
    campaign TEXT NOT NULL,
    status TEXT NOT NULL,
    digit TEXT,
    amd TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@contextmanager
def connect(path=None):
    conn = sqlite3.connect(path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_dnc(conn, phone):
    return conn.execute("SELECT 1 FROM dnc WHERE phone = ?", (phone,)).fetchone() is not None


def add_dnc(conn, phone, source):
    conn.execute("INSERT OR IGNORE INTO dnc (phone, source) VALUES (?, ?)", (phone, source))


def log_call(conn, call_uuid, phone, campaign, status):
    conn.execute(
        "INSERT OR REPLACE INTO calls (call_uuid, phone, campaign, status) VALUES (?, ?, ?, ?)",
        (call_uuid, phone, campaign, status),
    )


def update_call(conn, call_uuid, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE calls SET {cols}, updated_at = datetime('now') WHERE call_uuid = ?",
        (*fields.values(), call_uuid),
    )


def phone_for_call(conn, call_uuid):
    row = conn.execute("SELECT phone FROM calls WHERE call_uuid = ?", (call_uuid,)).fetchone()
    return row["phone"] if row else None


def bind_call_uuid(conn, request_uuid, call_uuid):
    """Calls are logged by Plivo request_uuid; webhooks then carry the real CallUUID."""
    if request_uuid and call_uuid and request_uuid != call_uuid:
        conn.execute("UPDATE calls SET call_uuid = ? WHERE call_uuid = ?", (call_uuid, request_uuid))
