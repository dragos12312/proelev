"""
ANUNȚURI router — MS-Teams style per-(class, subject) channels.

Each channel has two kinds of rows in subject_channel_post:
  - "post"   text only, anyone in the channel may write
  - "file"   binary resource, only teachers/admin may upload, anyone may read

Membership:
  - admin/user: every channel
  - teacher:    every (class, subject) they have a teacher_assignment for
  - student:    every (class, subject) where class == their class and a
                teacher_assignment exists for that pair
  - parent:     read-only on every channel their children are in

Posts fan out a notification to the rest of the channel so people see new
content next time they look at the bell.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import (
    SubjectChannelPost, User, SchoolClass, Subject,
    teacher_assignment, parent_child,
    ROLE_ADMIN, ROLE_USER, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)
from auth import get_current_user


router = APIRouter()
MAX_RESOURCE_BYTES = 5 * 1024 * 1024  # 5 MB resource files


def _user_channels(db: Session, user: User) -> list[tuple[int, int]]:
    """Return the list of (class_id, subject_id) channels this user can read.

    Access model (post-redesign):
      - admin/user : every (class, subject) combo in the catalog
      - teacher    : every CLASS × every subject they teach (so a Matematică
                     teacher sees the Matematică channel for 1A through 4B)
      - student    : every SUBJECT × their own class
      - parent     : every SUBJECT × each child's class
    A channel "exists" implicitly even without any teacher_assignment row.
    """
    role = user.role.name if user.role else None
    from models import SchoolClass, Subject as SubjModel

    all_class_ids   = [c.id for c in db.query(SchoolClass).all()]
    all_subject_ids = [s.id for s in db.query(SubjModel).all()]

    if role in (ROLE_ADMIN, ROLE_USER):
        return [(c, s) for c in all_class_ids for s in all_subject_ids]
    if role == ROLE_TEACHER:
        # subjects this teacher is assigned to (any class)
        sub_ids = [r[0] for r in db.execute(
            select(teacher_assignment.c.subject_id).where(
                teacher_assignment.c.user_id == user.id
            ).distinct()
        ).all()]
        return [(c, s) for c in all_class_ids for s in sub_ids]
    if role == ROLE_STUDENT:
        if user.class_id is None:
            return []
        return [(user.class_id, s) for s in all_subject_ids]
    if role == ROLE_PARENT:
        out: set[tuple[int, int]] = set()
        for child in user.children:
            if child.class_id is None:
                continue
            for s in all_subject_ids:
                out.add((child.class_id, s))
        return list(out)
    return []


def _can_read(db: Session, user: User, class_id: int, subject_id: int) -> bool:
    return (class_id, subject_id) in set(_user_channels(db, user))


def _can_post_text(db: Session, user: User, class_id: int, subject_id: int) -> bool:
    role = user.role.name if user.role else None
    if role in (ROLE_ADMIN, ROLE_TEACHER, ROLE_STUDENT, ROLE_USER):
        return _can_read(db, user, class_id, subject_id)
    return False  # parents are read-only


def _can_post_file(db: Session, user: User, class_id: int, subject_id: int) -> bool:
    role = user.role.name if user.role else None
    if role == ROLE_ADMIN:
        return _can_read(db, user, class_id, subject_id)
    if role == ROLE_TEACHER:
        # teacher can upload to any (class, subject) where subject is one they teach
        return _can_read(db, user, class_id, subject_id) and db.execute(
            select(teacher_assignment.c.user_id).where(
                teacher_assignment.c.user_id    == user.id,
                teacher_assignment.c.subject_id == subject_id,
            )
        ).first() is not None
    return False


@router.get("/mine")
def my_channels(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Channels the caller can see, decorated with the class/subject names
    plus the last post's timestamp so the UI can show "Matematică 4A · post
    azi" badges."""
    pairs = _user_channels(db, user)
    out = []
    for cid, sid in pairs:
        cls = db.get(SchoolClass, cid)
        sub = db.get(Subject,     sid)
        if not (cls and sub):
            continue
        last = (
            db.query(SubjectChannelPost)
            .filter_by(class_id=cid, subject_id=sid)
            .order_by(SubjectChannelPost.created_at.desc())
            .first()
        )
        post_count = db.query(SubjectChannelPost).filter_by(
            class_id=cid, subject_id=sid, kind="post",
        ).count()
        file_count = db.query(SubjectChannelPost).filter_by(
            class_id=cid, subject_id=sid, kind="file",
        ).count()
        out.append({
            "classId":    cid,
            "subjectId":  sid,
            "className":  cls.name,
            "subjectName": sub.name,
            "lastActivity": last.created_at.isoformat() + "Z" if last else None,
            "postCount": post_count,
            "fileCount": file_count,
        })
    # most recently active first
    out.sort(key=lambda r: r["lastActivity"] or "", reverse=True)
    return out


def _serialize_post(p: SubjectChannelPost) -> dict:
    return {
        "id":         p.id,
        "kind":       p.kind,
        "authorId":   p.author_user_id,
        "authorName": p.author.name if p.author else "(șters)",
        "text":       p.text,
        "fileName":   p.file_name,
        "hasFile":    bool(p.file_blob),
        "createdAt":  p.created_at.isoformat() + "Z",
    }


@router.get("/{class_id}/{subject_id}")
def channel_feed(
    class_id: int, subject_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Both posts and files for a single channel, newest first."""
    if not _can_read(db, user, class_id, subject_id):
        raise HTTPException(status_code=403, detail="Nu ai acces la acest canal")
    rows = (
        db.query(SubjectChannelPost)
        .filter_by(class_id=class_id, subject_id=subject_id)
        .order_by(SubjectChannelPost.created_at.desc(), SubjectChannelPost.id.desc())
        .all()
    )
    cls = db.get(SchoolClass, class_id)
    sub = db.get(Subject,     subject_id)
    role = user.role.name if user.role else None
    return {
        "className":     cls.name if cls else None,
        "subjectName":   sub.name if sub else None,
        "canPostText":   _can_post_text(db, user, class_id, subject_id),
        "canPostFile":   _can_post_file(db, user, class_id, subject_id),
        "myRole":        role,
        "posts": [_serialize_post(r) for r in rows],
    }


def _notify_channel_members(
    db: Session, class_id: int, subject_id: int, author: User,
    *, kind: str, title: str, body: str,
) -> None:
    """Push a notification to every channel member except the author."""
    try:
        from notifications import _push
        members = set()
        # teachers for this pair
        rows = db.execute(
            select(teacher_assignment.c.user_id).where(
                teacher_assignment.c.class_id   == class_id,
                teacher_assignment.c.subject_id == subject_id,
            )
        ).all()
        for (uid,) in rows: members.add(uid)
        # students in this class
        students = db.query(User).filter(
            User.class_id == class_id, User.role.has(name=ROLE_STUDENT)
        ).all()
        for s in students: members.add(s.id)
        # parents of those students
        if students:
            ppairs = db.execute(
                select(parent_child.c.parent_user_id).where(
                    parent_child.c.child_user_id.in_([s.id for s in students])
                )
            ).all()
            for (pid,) in ppairs: members.add(pid)
        # drop the author themselves
        members.discard(author.id)
        if not members:
            return
        link = f"/channels/{class_id}/{subject_id}"
        _push(db, list(members), kind=kind, title=title, body=body, link=link)
    except Exception as _e:
        import logging; logging.getLogger(__name__).warning("channel notify failed: %s", _e)


@router.post("/{class_id}/{subject_id}/post")
def create_text_post(
    class_id: int, subject_id: int,
    text: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_post_text(db, user, class_id, subject_id):
        raise HTTPException(status_code=403, detail="Nu poți posta în acest canal")
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Postarea nu poate fi goală")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Postarea este prea lungă (max 2000 caractere)")
    row = SubjectChannelPost(
        class_id=class_id, subject_id=subject_id, author_user_id=user.id,
        kind="post", text=text, created_at=datetime.utcnow(),
    )
    db.add(row); db.commit(); db.refresh(row)

    cls = db.get(SchoolClass, class_id)
    sub = db.get(Subject,     subject_id)
    snippet = text if len(text) <= 80 else text[:77] + "…"
    _notify_channel_members(
        db, class_id, subject_id, user,
        kind="channel_post",
        title=f"Postare nouă: {sub.name if sub else ''} {cls.name if cls else ''}".strip(),
        body=f"{user.name}: {snippet}",
    )
    return _serialize_post(row)


@router.post("/{class_id}/{subject_id}/file")
async def upload_resource(
    class_id: int, subject_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_post_file(db, user, class_id, subject_id):
        raise HTTPException(status_code=403, detail="Doar profesorul poate încărca resurse")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Niciun fișier")
    blob = await file.read()
    if len(blob) > MAX_RESOURCE_BYTES:
        raise HTTPException(status_code=413, detail="Fișierul este prea mare (max 5 MB)")
    row = SubjectChannelPost(
        class_id=class_id, subject_id=subject_id, author_user_id=user.id,
        kind="file", file_name=file.filename, file_blob=blob,
        created_at=datetime.utcnow(),
    )
    db.add(row); db.commit(); db.refresh(row)

    cls = db.get(SchoolClass, class_id)
    sub = db.get(Subject,     subject_id)
    _notify_channel_members(
        db, class_id, subject_id, user,
        kind="channel_file",
        title=f"Resursă nouă: {sub.name if sub else ''} {cls.name if cls else ''}".strip(),
        body=f"{user.name} a încărcat {file.filename}",
    )
    return _serialize_post(row)


@router.get("/post/{post_id}/file")
def download_resource(
    post_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(SubjectChannelPost, post_id)
    if not row or row.kind != "file" or not row.file_blob:
        raise HTTPException(status_code=404, detail="Resursă inexistentă")
    if not _can_read(db, user, row.class_id, row.subject_id):
        raise HTTPException(status_code=403, detail="Nu ai acces")
    return Response(
        content=row.file_blob,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row.file_name or "fisier"}"'},
    )


@router.delete("/post/{post_id}", status_code=204)
def delete_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Author or admin can delete. Teachers can also delete anything in
    channels they own (so they moderate their class)."""
    row = db.get(SubjectChannelPost, post_id)
    if not row:
        raise HTTPException(status_code=404, detail="Postare inexistentă")
    role = user.role.name if user.role else None
    is_admin     = role == ROLE_ADMIN
    is_author    = row.author_user_id == user.id
    is_owner     = role == ROLE_TEACHER and db.execute(
        select(teacher_assignment.c.user_id).where(
            teacher_assignment.c.user_id    == user.id,
            teacher_assignment.c.class_id   == row.class_id,
            teacher_assignment.c.subject_id == row.subject_id,
        )
    ).first() is not None
    if not (is_admin or is_author or is_owner):
        raise HTTPException(status_code=403, detail="Nu poți șterge această postare")
    db.delete(row); db.commit()
