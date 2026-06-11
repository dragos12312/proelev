"""
School-wide announcements (anunțuri generale). Admin posts → everyone sees.
Shown as a banner on the subject grid page.

Different from /channels announcements which are scoped to one (class, subject).
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import (
    SchoolAnnouncement, User, ROLE_ADMIN,
)
from auth import get_current_user


router = APIRouter()


KINDS = {"info", "warning", "event"}


def _serialize(a: SchoolAnnouncement) -> dict:
    return {
        "id":            a.id,
        "title":         a.title,
        "body":          a.body,
        "kind":          a.kind,
        "createdByName": a.created_by.name if a.created_by else None,
        "createdAt":     a.created_at.isoformat() + "Z",
        "pinned":        bool(a.pinned),
    }


class CreateAnnouncement(BaseModel):
    title: str
    body:  Optional[str] = None
    kind:  Optional[str] = "info"


@router.get("")
def list_announcements(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(SchoolAnnouncement)
        .filter(SchoolAnnouncement.pinned == 1)
        .order_by(SchoolAnnouncement.created_at.desc())
        .limit(20)
        .all()
    )
    return [_serialize(r) for r in rows]


@router.post("")
def create_announcement(
    body: CreateAnnouncement,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.role or user.role.name != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Doar adminul")
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="Titlul este obligatoriu")
    kind = (body.kind or "info").strip().lower()
    if kind not in KINDS:
        kind = "info"
    a = SchoolAnnouncement(
        title=title[:200],
        body=(body.body or "").strip() or None,
        kind=kind,
        created_by_user_id=user.id,
        created_at=datetime.utcnow(),
        pinned=1,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    # ping every user with a notification so it pops up in the bell feed too
    try:
        from notifications import _push
        all_user_ids = [u.id for u in db.query(User).all() if u.id != user.id]
        if all_user_ids:
            _push(db, all_user_ids,
                  kind="school_announcement",
                  title=f"Anunț general: {a.title}",
                  body=(a.body or "")[:120],
                  link="/main")
    except Exception as _e:
        import logging; logging.getLogger(__name__).warning("school announce notify failed: %s", _e)
    return _serialize(a)


@router.delete("/{ann_id}", status_code=204)
def archive_announcement(
    ann_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.role or user.role.name != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Doar adminul")
    a = db.get(SchoolAnnouncement, ann_id)
    if not a:
        raise HTTPException(status_code=404, detail="Inexistent")
    a.pinned = 0
    db.commit()
