"""
Helpers and router for the per-user notification feed.

Design notes
------------
* one Notification row per recipient — a single homework that goes out to
  20 students + 30 parents fans out to 50 rows. that's fine, sqlite handles it
  and it keeps the read/unread state per user trivial.
* `create_*` helpers commit on their own. callers wrap their own commit before
  calling, so the notification surviving doesn't depend on the caller's tx.
* the API is small: list / unread_count / mark_read / mark_all_read. newest
  first, optional `unread_only` filter, hard cap of 100 rows per page.
"""
from datetime import datetime
from typing import Iterable

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from models import (
    Notification, User, Homework, Student,
    parent_child, ROLE_TEACHER, ROLE_STUDENT,
)
from auth import get_current_user


router = APIRouter()


# ─── creation helpers, called by other routers after they commit ─────────

def _push(db: Session, user_ids: Iterable[int], *, kind: str, title: str,
          body: str | None = None, link: str | None = None) -> None:
    """Insert one Notification row per user_id and commit. Safe to call with
    an empty / duplicate user_ids iterable; dedupes silently."""
    seen = set()
    now = datetime.utcnow()
    rows = []
    for uid in user_ids:
        if uid is None or uid in seen:
            continue
        seen.add(uid)
        rows.append(Notification(
            user_id=uid, kind=kind, title=title, body=body, link=link,
            created_at=now,
        ))
    if not rows:
        return
    db.add_all(rows)
    db.commit()


def _parent_ids_for_children(db: Session, child_ids: Iterable[int]) -> list[int]:
    """Resolve every parent_user_id that's linked to any of these children."""
    cids = [c for c in child_ids if c is not None]
    if not cids:
        return []
    from sqlalchemy import select
    rows = db.execute(
        select(parent_child.c.parent_user_id).where(
            parent_child.c.child_user_id.in_(cids)
        )
    ).all()
    return [r[0] for r in rows]


def notify_homework_created(db: Session, hw: Homework) -> None:
    """Every student in the class + every parent of those students."""
    students = db.query(User).filter(
        User.class_id == hw.class_id,
        User.role.has(name=ROLE_STUDENT),
    ).all()
    student_ids = [s.id for s in students]
    parent_ids  = _parent_ids_for_children(db, student_ids)

    subj = hw.subject.name if hw.subject else "?"
    cls  = hw.assigned_class.name if hw.assigned_class else "?"
    title = f"Temă nouă la {subj}"
    body  = f"{hw.title} ({cls}), termen {hw.due_date.isoformat()}"
    link  = f"/homeworks/{hw.id}"

    _push(db, student_ids + parent_ids,
          kind="homework_new", title=title, body=body, link=link)


def notify_submission_uploaded(db: Session, hw: Homework, submitter: User) -> None:
    """The teacher who created the homework gets pinged when one of their
    students uploads. For legacy admin-posted homeworks, no-op."""
    if hw.created_by_user_id is None:
        return
    title = "Tema a fost trimisă"
    body  = f"{submitter.name} a încărcat {hw.title}"
    link  = f"/homeworks/{hw.id}"
    _push(db, [hw.created_by_user_id],
          kind="submission_new", title=title, body=body, link=link)


def notify_grade_given(db: Session, hw: Homework, student_row: Student,
                       grade: int | None, feedback: str | None) -> None:
    """Notify the student (if they're a real user) plus all their parents."""
    if student_row.user_id is None:
        return
    student_ids = [student_row.user_id]
    parent_ids  = _parent_ids_for_children(db, student_ids)

    subj = hw.subject.name if hw.subject else "?"
    if grade is not None:
        title = f"Notă nouă la {subj}: {grade}"
    else:
        title = f"Feedback nou la {subj}"
    body = hw.title
    if feedback:
        body = f"{hw.title} — {feedback}"
    link = f"/homeworks/{hw.id}"

    _push(db, student_ids + parent_ids,
          kind="grade_given", title=title, body=body, link=link)


def notify_chat_message(recipient_ids: list[int], *, author_name: str,
                        text: str, room_id: int) -> None:
    """Called from the websocket handler. Opens its own session because the
    WS doesn't carry the FastAPI request scope, then commits + closes."""
    if not recipient_ids:
        return
    snippet = (text or "").strip().replace("\n", " ")
    if len(snippet) > 80:
        snippet = snippet[:77] + "…"
    title = f"Mesaj nou de la {author_name}"
    body  = snippet or "(fără text)"
    # chat tab handles the room selection itself, the messages view reads ?room=<id>
    link = f"/messages?room={room_id}"
    db = SessionLocal()
    try:
        _push(db, recipient_ids,
              kind="chat_message", title=title, body=body, link=link)
    finally:
        db.close()


# ─── REST router ─────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id:        int
    kind:      str
    title:     str
    body:      str | None = None
    link:      str | None = None
    createdAt: str
    read:      bool


def _serialize(n: Notification) -> dict:
    return {
        "id":        n.id,
        "kind":      n.kind,
        "title":     n.title,
        "body":      n.body,
        "link":      n.link,
        "createdAt": n.created_at.isoformat() + "Z",
        "read":      n.read_at is not None,
    }


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = Query(default=False),
    limit:       int  = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        q = q.filter(Notification.read_at.is_(None))
    rows = q.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()
    return [_serialize(r) for r in rows]


@router.get("/unread_count")
def unread_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.read_at.is_(None),
    ).count()
    return {"count": c}


@router.post("/{nid}/read")
def mark_read(
    nid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = db.get(Notification, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notificare inexistentă")
    if n.read_at is None:
        n.read_at = datetime.utcnow()
        db.commit()
    return {"ok": True}


@router.post("/read_all")
def mark_all_read(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.read_at.is_(None),
    ).update({Notification.read_at: now}, synchronize_session=False)
    db.commit()
    return {"ok": True}
