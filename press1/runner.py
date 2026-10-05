"""Campaign runner: python -m press1.runner

The bot and the web panel only *request* a start or stop by writing to the
campaign_state row; this single worker process does the dialing. That keeps one
campaign at a time no matter how many web workers or control surfaces exist.
"""
import json
import logging
import os
import threading
import time
from pathlib import Path

from . import db, dialer

log = logging.getLogger("press1.runner")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
BUSY = ("pending", "running", "stopping")


class Busy(Exception):
    pass


def contacts_path():
    return UPLOAD_DIR / "contacts.csv"


def get(conn=None):
    if conn is None:
        with db.connect() as c:
            return get(c)
    r = conn.execute("SELECT * FROM campaign_state WHERE id = 1").fetchone()
    return {"name": r["name"], "status": r["status"], "progress": json.loads(r["progress"] or "{}"),
            "message": r["message"], "notified": bool(r["notified"]), "updated_at": r["updated_at"],
            "busy": r["status"] in BUSY}


def _set(conn, **fields):
    if "progress" in fields:
        fields["progress"] = json.dumps(fields["progress"])
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE campaign_state SET {cols}, updated_at = datetime('now') WHERE id = 1",
                 tuple(fields.values()))


def save_contacts(data):
    """Store an uploaded CSV as the contact list and dry-run it (no calls)."""
    if get()["busy"]:
        raise Busy(get()["name"])
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    tmp = contacts_path().with_suffix(".tmp")
    tmp.write_bytes(data)
    try:
        stats = dialer.run(str(tmp), "dry-run", dry_run=True)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(contacts_path())
    return stats


def request_start(name):
    if not contacts_path().exists():
        raise FileNotFoundError("upload contacts first")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if get(conn)["busy"]:
            raise Busy(get(conn)["name"])
        _set(conn, name=name, status="pending", progress={}, message="", notified=1)


def request_stop():
    """Returns True if something was running or waiting to start."""
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        st = get(conn)["status"]
        if st == "pending":
            _set(conn, status="stopped", message="cancelled before start")
        elif st == "running":
            _set(conn, status="stopping")
        return st in BUSY


def mark_notified():
    with db.connect() as conn:
        _set(conn, notified=1)


def _run_one(name):
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            if get()["status"] == "stopping":
                stop.set()
            time.sleep(1)

    def progress(stats):
        with db.connect() as conn:
            _set(conn, progress=stats)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        stats = dialer.run(str(contacts_path()), name, stop=stop, on_progress=progress)
        final = "stopped" if stop.is_set() else "done"
        with db.connect() as conn:
            _set(conn, status=final, progress=stats, message="", notified=0)
    except Exception as e:
        log.exception("campaign %s failed", name)
        with db.connect() as conn:
            _set(conn, status="failed", message=str(e)[:300], notified=0)
    finally:
        stop.set()


def recover():
    """A worker that died mid-campaign leaves 'running'; don't pretend it still is."""
    with db.connect() as conn:
        if get(conn)["status"] in ("running", "stopping"):
            _set(conn, status="failed", message="runner restarted during the campaign", notified=0)


def step():
    """Start the pending campaign, if any. Returns True if one ran."""
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        st = get(conn)
        if st["status"] != "pending":
            return False
        _set(conn, status="running")
    db.load_settings()
    log.info("starting campaign %s", st["name"])
    _run_one(st["name"])
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    recover()
    log.info("runner ready")
    while True:
        try:
            if not step():
                time.sleep(1)
        except Exception:
            log.exception("runner loop error")
            time.sleep(5)


if __name__ == "__main__":
    main()
