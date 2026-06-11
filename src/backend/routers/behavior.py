"""
"Media la purtare" — Romanian-style behavior grades. One row per
(student, period). Set by any teacher with at least one assignment (under
the new access model they're effectively a teacher of every class), or
admin. Students and parents read it.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import (
    BehaviorGrade, User, SchoolClass, teacher_assignment,
    ROLE_ADMIN, ROLE_USER, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)
from auth import get_current_user


router = APIRouter()


def _can_set_behavior(db: Session, user: User) -> bool:
    role = user.role.name if user.role else None
    if role == ROLE_ADMIN:
        return True
    if role != ROLE_TEACHER:
        return False
    return db.execute(
        select(teacher_assignment.c.user_id).where(
            teacher_assignment.c.user_id == user.id
        )
    ).first() is not None


def _serialize(b: BehaviorGrade) -> dict:
    return {
        "id":              b.id,
        "studentUserId":   b.student_user_id,
        "studentName":     b.student.name if b.student else None,
        "period":          b.period,
        "grade":           b.grade,
        "note":            b.note,
        "createdByName":   b.created_by.name if b.created_by else None,
        "createdAt":       b.created_at.isoformat() + "Z",
    }


class SetBehavior(BaseModel):
    studentUserId: int
    period:        str
    grade:         int
    note:          Optional[str] = None


@router.post("")
def set_behavior(
    body: SetBehavior,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upsert a behavior grade for one student in one period."""
    if not _can_set_behavior(db, user):
        raise HTTPException(status_code=403, detail="Doar profesorul sau adminul")
    if not (1 <= body.grade <= 10):
        raise HTTPException(status_code=422, detail="Nota trebuie să fie între 1 și 10")
    period = (body.period or "").strip()
    if not period:
        raise HTTPException(status_code=422, detail="Perioada este obligatorie")

    st = db.get(User, body.studentUserId)
    if not st or not st.role or st.role.name != ROLE_STUDENT:
        raise HTTPException(status_code=400, detail="Utilizatorul nu este elev")

    existing = db.query(BehaviorGrade).filter_by(
        student_user_id=body.studentUserId, period=period,
    ).first()
    if existing:
        existing.grade               = body.grade
        existing.note                = body.note
        existing.created_by_user_id  = user.id
        existing.created_at          = datetime.utcnow()
        b = existing
    else:
        b = BehaviorGrade(
            student_user_id=body.studentUserId,
            period=period,
            grade=body.grade,
            note=body.note,
            created_by_user_id=user.id,
            created_at=datetime.utcnow(),
        )
        db.add(b)
    db.commit()
    db.refresh(b)
    # nudge the student + their parents
    try:
        from notifications import _push, _parent_ids_for_children
        parents = _parent_ids_for_children(db, [body.studentUserId])
        _push(db, [body.studentUserId] + parents,
              kind="behavior_set",
              title=f"Notă la purtare actualizată: {b.grade}",
              body=f"Perioada: {period}",
              link="/catalog")
    except Exception as _e:
        import logging; logging.getLogger(__name__).warning("behavior notify failed: %s", _e)
    return _serialize(b)


@router.get("/class/{class_id}")
def list_for_class(
    class_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every behavior grade row for the students in a class. Teacher/admin only."""
    if not _can_set_behavior(db, user):
        raise HTTPException(status_code=403, detail="Nu ai acces")
    student_ids = [u.id for u in db.query(User).filter(
        User.class_id == class_id, User.role.has(name=ROLE_STUDENT)
    ).all()]
    if not student_ids:
        return []
    rows = (
        db.query(BehaviorGrade)
        .filter(BehaviorGrade.student_user_id.in_(student_ids))
        .order_by(BehaviorGrade.created_at.desc())
        .all()
    )
    return [_serialize(r) for r in rows]


@router.get("/me")
def my_behavior(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Student → own history. Parent → children's grouped per child."""
    role = user.role.name if user.role else None
    if role == ROLE_STUDENT:
        rows = (
            db.query(BehaviorGrade)
            .filter(BehaviorGrade.student_user_id == user.id)
            .order_by(BehaviorGrade.created_at.desc())
            .all()
        )
        return {"viewKind": "student", "rows": [_serialize(r) for r in rows]}
    if role == ROLE_PARENT:
        children = []
        for c in user.children:
            rows = (
                db.query(BehaviorGrade)
                .filter(BehaviorGrade.student_user_id == c.id)
                .order_by(BehaviorGrade.created_at.desc())
                .all()
            )
            children.append({
                "userId": c.id, "name": c.name,
                "rows":   [_serialize(r) for r in rows],
            })
        return {"viewKind": "parent", "children": children}
    return {"viewKind": "none", "rows": []}
