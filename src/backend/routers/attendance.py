"""
PREZENȚĂ (attendance) router. Teacher marks daily attendance for the class
they teach; students/parents read their own absences only.

Access rules:
  - mark (POST):   teacher with a teacher_assignment for that class, or admin
  - list (GET):    admin/teacher with assignment for the class see everyone;
                   student sees own; parent sees their children's
  - my (GET):      student sees own, parent sees their children's, anyone
                   else returns []
"""
from datetime import datetime, date as date_cls
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Attendance, User, SchoolClass, teacher_assignment,
    ROLE_ADMIN, ROLE_USER, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)
from auth import get_current_user


router = APIRouter()


# valid status values; kept tight so the UI doesn't get surprises
VALID_STATUSES = {"present", "absent", "late", "excused"}


def _teacher_owns_class(db: Session, user: User, class_id: int) -> bool:
    """Admin owns everything. Under the new access model, any teacher is
    effectively a teacher of every class for the subjects they teach, so
    any teacher with at least one assignment can mark attendance for any
    class."""
    if user.role and user.role.name == ROLE_ADMIN:
        return True
    if not user.role or user.role.name != ROLE_TEACHER:
        return False
    return db.execute(
        select(teacher_assignment.c.user_id).where(
            teacher_assignment.c.user_id == user.id
        )
    ).first() is not None


class AttendanceMark(BaseModel):
    studentUserId: int
    status:        str
    note:          Optional[str] = None


class AttendanceBulkRequest(BaseModel):
    classId: int
    date:    str               # ISO date
    marks:   list[AttendanceMark]


@router.post("/bulk")
def bulk_mark(
    body: AttendanceBulkRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upsert attendance for an entire class on one date in one request."""
    if not _teacher_owns_class(db, user, body.classId):
        raise HTTPException(status_code=403, detail="Nu poți marca prezența la această clasă")
    try:
        on = date_cls.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Dată invalidă (format YYYY-MM-DD)")

    now = datetime.utcnow()
    affected = 0
    notified_student_ids: list[int] = []
    for m in body.marks:
        if m.status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Status invalid: {m.status}")
        # verify the student is actually in this class
        st = db.get(User, m.studentUserId)
        if not st or not st.role or st.role.name != ROLE_STUDENT or st.class_id != body.classId:
            continue
        existing = db.query(Attendance).filter_by(
            class_id=body.classId, student_user_id=m.studentUserId, date=on,
        ).first()
        new_absent = m.status in ("absent", "late")
        was_absent = bool(existing and existing.status in ("absent", "late"))
        if existing:
            existing.status     = m.status
            existing.note       = m.note
            existing.created_by_user_id = user.id
            existing.created_at = now
        else:
            db.add(Attendance(
                class_id=body.classId,
                student_user_id=m.studentUserId,
                date=on,
                status=m.status,
                note=m.note,
                created_by_user_id=user.id,
                created_at=now,
            ))
        affected += 1
        # only notify on absent/late, and only when the state changed
        if new_absent and not was_absent:
            notified_student_ids.append(m.studentUserId)

    db.commit()

    # fan out notifications to absent students + their parents
    try:
        if notified_student_ids:
            from notifications import _push, _parent_ids_for_children
            day_label = on.isoformat()
            title = f"Absență înregistrată ({day_label})"
            body_text = "Ai fost marcat absent / întârziat azi."
            link = "/attendance"
            parent_ids = _parent_ids_for_children(db, notified_student_ids)
            _push(db, notified_student_ids + parent_ids,
                  kind="attendance_marked", title=title, body=body_text, link=link)
    except Exception as _e:
        import logging; logging.getLogger(__name__).warning("attendance notify failed: %s", _e)

    return {"ok": True, "affected": affected}


def _serialize(a: Attendance) -> dict:
    return {
        "id":              a.id,
        "classId":         a.class_id,
        "studentUserId":   a.student_user_id,
        "studentName":     a.student.name if a.student else None,
        "date":            a.date.isoformat(),
        "status":          a.status,
        "note":            a.note,
        "markedBy":        a.created_by.name if a.created_by else None,
        "createdAt":       a.created_at.isoformat() + "Z",
    }


@router.get("/class/{class_id}")
def list_for_class(
    class_id: int,
    on:    Optional[str] = Query(default=None, alias="date"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Full attendance for one class on one date. Teacher/admin only."""
    if not _teacher_owns_class(db, user, class_id):
        raise HTTPException(status_code=403, detail="Nu ai acces la prezența acestei clase")
    q = db.query(Attendance).filter(Attendance.class_id == class_id)
    if on:
        try:
            q = q.filter(Attendance.date == date_cls.fromisoformat(on))
        except ValueError:
            raise HTTPException(status_code=422, detail="Dată invalidă")
    rows = q.order_by(Attendance.date.desc(), Attendance.id.desc()).all()
    return [_serialize(r) for r in rows]


@router.get("/roster/{class_id}")
def class_roster(
    class_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Roster of real student users in a class, so the teacher's mark page
    can render the list with one row per student."""
    if not _teacher_owns_class(db, user, class_id):
        raise HTTPException(status_code=403, detail="Nu ai acces la această clasă")
    students = db.query(User).filter(
        User.class_id == class_id,
        User.role.has(name=ROLE_STUDENT),
    ).order_by(User.name.asc()).all()
    return [
        {"userId": s.id, "name": s.name, "email": s.email}
        for s in students
    ]


@router.get("/me")
def my_attendance(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Student → own attendance. Parent → children's attendance grouped per child."""
    role = user.role.name if user.role else None
    if role == ROLE_STUDENT:
        rows = (
            db.query(Attendance)
            .filter(Attendance.student_user_id == user.id)
            .order_by(Attendance.date.desc())
            .all()
        )
        return {"viewKind": "student", "rows": [_serialize(r) for r in rows]}
    if role == ROLE_PARENT:
        children = []
        for c in user.children:
            rows = (
                db.query(Attendance)
                .filter(Attendance.student_user_id == c.id)
                .order_by(Attendance.date.desc())
                .all()
            )
            children.append({
                "userId": c.id, "name": c.name,
                "class": {"id": c.school_class.id, "name": c.school_class.name} if c.school_class else None,
                "rows": [_serialize(r) for r in rows],
            })
        return {"viewKind": "parent", "children": children}
    # admin/teacher/user get nothing here — they go through /class/{id}
    return {"viewKind": "none", "rows": []}


@router.get("/teacher/classes")
def teacher_classes(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List of (class_id, class_name) the teacher can mark attendance for.
    For admin, returns every class."""
    role = user.role.name if user.role else None
    if role == ROLE_ADMIN:
        rows = db.query(SchoolClass).order_by(SchoolClass.name).all()
        return [{"id": r.id, "name": r.name} for r in rows]
    if role != ROLE_TEACHER:
        raise HTTPException(status_code=403, detail="Doar profesorii/adminul")
    # under the new model the teacher has access to every class for the
    # subjects they teach, so the dropdown shows all 8
    has_any = db.execute(
        select(teacher_assignment.c.user_id).where(
            teacher_assignment.c.user_id == user.id
        )
    ).first() is not None
    if not has_any:
        return []
    rows = db.query(SchoolClass).order_by(SchoolClass.name).all()
    return [{"id": r.id, "name": r.name} for r in rows]
