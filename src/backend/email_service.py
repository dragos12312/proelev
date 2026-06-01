"""
Mock email service. Writes messages to a TinyDB collection so the frontend
can render a fake inbox. Replaces real SMTP for the lab demo, the user
sees the email codes show up in real time in a panel.

Each message is a tinydb doc:
    {id, to, subject, body, code, created_at}
"""
import os
import threading
from datetime import datetime

from tinydb import TinyDB, Query


EMAIL_DB_PATH = os.environ.get("EMAIL_DB_PATH", "./email.json")

_lock = threading.Lock()
_db = TinyDB(EMAIL_DB_PATH)
_inbox = _db.table("inbox")


def _next_id() -> int:
    docs = _inbox.all()
    return (max(d.get("id", 0) for d in docs) + 1) if docs else 1


def reset() -> None:
    """Wipe the inbox, used by tests."""
    with _lock:
        _db.drop_tables()
        global _inbox
        _inbox = _db.table("inbox")


def reload(path: str) -> None:
    """Re-open the inbox at a different file, used by tests via EMAIL_DB_PATH."""
    global _db, _inbox
    with _lock:
        _db.close()
        _db = TinyDB(path)
        _inbox = _db.table("inbox")


def send(to: str, subject: str, body: str, code: str = "") -> dict:
    """Pretend to send an email. Returns the stored row.
    code is broken out separately so the frontend can render it nicely."""
    with _lock:
        msg = {
            "id":         _next_id(),
            "to":         to.lower(),
            "subject":    subject,
            "body":       body,
            "code":       code,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        _inbox.insert(msg)
        return msg


def inbox_for(email: str) -> list[dict]:
    """All messages addressed to this email, newest first."""
    with _lock:
        Msg = Query()
        items = list(_inbox.search(Msg.to == email.lower()))
        items.sort(key=lambda m: m["id"], reverse=True)
        return items


def all_messages() -> list[dict]:
    """Admin view of every message ever sent, newest first."""
    with _lock:
        items = list(_inbox.all())
        items.sort(key=lambda m: m["id"], reverse=True)
        return items
