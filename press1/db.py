import sqlite3
import threading
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
CREATE INDEX IF NOT EXISTS calls_status ON calls (status);
CREATE TABLE IF NOT EXISTS settings (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Statuses that still occupy a Plivo channel / 3CX trunk line.
ACTIVE = ("queued", "answered", "transferred", "voicemail")

_initialized = set()
_init_lock = threading.Lock()


def _init(path):
    # Schema + WAL once per process: running DDL on every request takes a write
    # lock and serializes all concurrent webhooks.
    with _init_lock:
        if path in _initialized:
            return
        conn = sqlite3.connect(path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
        finally:
            conn.close()
        _initialized.add(path)


@contextmanager
def connect(path=None):
    path = path or config.DB_PATH
    _init(path)
    # busy_timeout: concurrent writers wait instead of failing with "database is locked"
    # (which turned into HTTP 500 -> Plivo got no XML -> dead air for the caller).
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def is_dnc(conn, phone):
    return conn.execute("SELECT 1 FROM dnc WHERE phone = ?", (phone,)).fetchone() is not None


def add_dnc(conn, phone, source):
    if phone:
        conn.execute("INSERT OR IGNORE INTO dnc (phone, source) VALUES (?, ?)", (phone, source))


def log_call(conn, call_uuid, phone, campaign, status):
    # The answer webhook may already have created the row under this uuid (fast pickup).
    conn.execute(
        "INSERT INTO calls (call_uuid, phone, campaign, status) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(call_uuid) DO UPDATE SET campaign = excluded.campaign",
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


def bind_call_uuid(conn, request_uuid, call_uuid, phone=""):
    """Calls are logged by Plivo request_uuid; webhooks carry the real CallUUID.

    Idempotent and race-safe: works whether the dialer has logged the call yet or not,
    and whether Plivo retries the webhook.
    """
    if not call_uuid:
        return
    if request_uuid and request_uuid != call_uuid:
        conn.execute(
            "UPDATE OR IGNORE calls SET call_uuid = ? WHERE call_uuid = ?", (call_uuid, request_uuid)
        )
    conn.execute(
        "INSERT OR IGNORE INTO calls (call_uuid, phone, campaign, status) VALUES (?, ?, '', 'queued')",
        (call_uuid, phone),
    )


def active_calls(conn):
    q = f"SELECT COUNT(*) FROM calls WHERE status IN ({','.join('?' * len(ACTIVE))})"
    return conn.execute(q, ACTIVE).fetchone()[0]


def transferred_calls(conn):
    return conn.execute("SELECT COUNT(*) FROM calls WHERE status = 'transferred'").fetchone()[0]


def expire_stale(conn, minutes):
    """Free slots whose hangup webhook was lost, so the dialer never stalls forever."""
    q = (
        f"UPDATE calls SET status = 'stale' WHERE status IN ({','.join('?' * len(ACTIVE))}) "
        f"AND updated_at < datetime('now', ?)"
    )
    return conn.execute(q, (*ACTIVE, f"-{int(minutes)} minutes")).rowcount


def get_settings(conn):
    return {r["name"]: r["value"] for r in conn.execute("SELECT name, value FROM settings")}


def set_setting(conn, name, value):
    conn.execute(
        "INSERT INTO settings (name, value) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
        (name, value),
    )


def load_settings():
    """Apply DB-stored settings to config (process-wide)."""
    with connect() as conn:
        config.apply_overrides(get_settings(conn))


def campaign_stats(conn, campaign):
    rows = conn.execute(
        "SELECT status, digit, COUNT(*) n FROM calls WHERE campaign = ? GROUP BY status, digit",
        (campaign,),
    ).fetchall()
    out = {}
    for r in rows:
        key = r["status"].split(":")[0]
        out[key] = out.get(key, 0) + r["n"]
        if r["digit"]:
            out[f"pressed_{r['digit']}"] = out.get(f"pressed_{r['digit']}", 0) + r["n"]
    return out
