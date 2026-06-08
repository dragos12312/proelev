"""
TESTE router. A test is a teacher-announced assessment (separate from a
homework). One Test row + one TestGrade row per student. Date is allowed
to be in the past so the contest demo can backdate.

Big-improvement detection
-------------------------
After a grade lands, we look up the student's previous TestGrade in the
same subject (newest test before this one). If the diff is >= 3 we record
a TestImprovement row, which the frontend's splash component polls for.
"""
from datetime import datetime, date as date_cls
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Test, TestGrade, TestImprovement, User, SchoolClass, Subject,
    teacher_assignment, parent_child,
    ROLE_ADMIN, ROLE_USER, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)
from auth import get_current_user


router = APIRouter()
BIG_IMPROVEMENT_DELTA = 3   # the splash threshold the user asked for


# ─── helpers ────────────────────────────────────────────────────────────

def _teacher_owns(db: Session, user: User, class_id: int, subject_id: int) -> bool:
    if user.role and user.role.name == ROLE_ADMIN:
        return True
    if not user.role or user.role.name != ROLE_TEACHER:
        return False
    return db.execute(
        select(teacher_assignment.c.user_id).where(
            teacher_assignment.c.user_id    == user.id,
            teacher_assignment.c.class_id   == class_id,
            teacher_assignment.c.subject_id == subject_id,
        )
    ).first() is not None


def _tests_visible_to(db: Session, user: User):
    """Return a Test query filtered to what this user is allowed to see."""
    role = user.role.name if user.role else None
    q = db.query(Test)
    if role in (ROLE_ADMIN, ROLE_USER):
        return q
    if role == ROLE_TEACHER:
        # everything for the (class, subject) pairs they teach, plus anything
        # they created themselves
        pairs = db.execute(
            select(teacher_assignment.c.class_id, teacher_assignment.c.subject_id)
            .where(teacher_assignment.c.user_id == user.id)
        ).all()
        if not pairs:
            return q.filter(Test.created_by_user_id == user.id)
        return q.filter(
            (Test.created_by_user_id == user.id) | (
                (Test.class_id.in_([c for c, _ in pairs])) &
                (Test.subject_id.in_([s for _, s in pairs]))
            )
        )
    if role == ROLE_STUDENT:
        if user.class_id is None:
            return q.filter(Test.id == -1)
        return q.filter(Test.class_id == user.class_id)
    if role == ROLE_PARENT:
        cids = [c.class_id for c in user.children if c.class_id]
        if not cids:
            return q.filter(Test.id == -1)
        return q.filter(Test.class_id.in_(cids))
    return q.filter(Test.id == -1)


def _serialize_test(t: Test, *, with_grades: bool = False) -> dict:
    out = {
        "id":            t.id,
        "title":         t.title,
        "description":   t.description,
        "classId":       t.class_id,
        "className":     t.school_class.name if t.school_class else None,
        "subjectId":     t.subject_id,
        "subjectName":   t.subject.name if t.subject else None,
        "scheduledDate": t.scheduled_date.isoformat() if t.scheduled_date else None,
        "createdById":   t.created_by_user_id,
        "createdByName": t.created_by.name if t.created_by else None,
        "createdAt":     t.created_at.isoformat() + "Z" if t.created_at else None,
    }
    if with_grades:
        out["grades"] = [
            {
                "id":          g.id,
                "studentUserId": g.student_user_id,
                "studentName": g.student.name if g.student else None,
                "grade":       g.grade,
                "feedback":    g.feedback,
                "gradedAt":    g.graded_at.isoformat() + "Z" if g.graded_at else None,
            }
            for g in sorted(t.grades, key=lambda x: (x.student.name if x.student else ""))
        ]
    return out


# ─── list / create ──────────────────────────────────────────────────────

class TestCreate(BaseModel):
    classId:        int
    subjectId:      int
    title:          str
    description:    Optional[str] = None
    scheduledDate:  str               # ISO; allowed to be in the past


@router.post("")
def create_test(
    body: TestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _teacher_owns(db, user, body.classId, body.subjectId):
        raise HTTPException(status_code=403, detail="Nu poți anunța test pentru această clasă/materie")
    try:
        sched = date_cls.fromisoformat(body.scheduledDate)
    except ValueError:
        raise HTTPException(status_code=422, detail="Dată invalidă (format YYYY-MM-DD)")
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Titlul este obligatoriu")

    t = Test(
        class_id=body.classId,
        subject_id=body.subjectId,
        title=body.title.strip(),
        description=(body.description or "").strip() or None,
        scheduled_date=sched,
        created_by_user_id=user.id,
        created_at=datetime.utcnow(),
    )
    db.add(t)
    db.flush()

    # pre-create blank TestGrade rows for every real student in the class so
    # the teacher's grading view has a populated roster immediately
    students = db.query(User).filter(
        User.class_id == body.classId,
        User.role.has(name=ROLE_STUDENT),
    ).all()
    for st in students:
        db.add(TestGrade(test_id=t.id, student_user_id=st.id))

    db.commit()
    db.refresh(t)

    # notify students + parents about the new announced test
    try:
        from notifications import _push, _parent_ids_for_children
        student_ids = [s.id for s in students]
        parent_ids  = _parent_ids_for_children(db, student_ids)
        cls  = db.get(SchoolClass, body.classId)
        sub  = db.get(Subject,     body.subjectId)
        title = f"Test anunțat: {sub.name if sub else ''} ({cls.name if cls else ''})"
        body_text = f"{t.title} — programat {t.scheduled_date.isoformat()}"
        _push(db, student_ids + parent_ids,
              kind="test_announced", title=title, body=body_text, link="/tests")
    except Exception as _e:
        import logging; logging.getLogger(__name__).warning("test announce notify failed: %s", _e)

    return _serialize_test(t, with_grades=True)


@router.get("")
def list_tests(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = _tests_visible_to(db, user).order_by(Test.scheduled_date.desc(), Test.id.desc()).limit(100).all()
    return [_serialize_test(t) for t in rows]


@router.get("/{test_id}")
def get_test(
    test_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(Test, test_id)
    if not t:
        raise HTTPException(status_code=404, detail="Testul nu există")
    # role-aware visibility — same filter as list
    visible = _tests_visible_to(db, user).filter(Test.id == test_id).first()
    if not visible:
        raise HTTPException(status_code=403, detail="Nu ai acces la acest test")
    role = user.role.name if user.role else None
    out = _serialize_test(t, with_grades=True)
    # students/parents only see their own / their child's grade rows
    if role == ROLE_STUDENT:
        out["grades"] = [g for g in out["grades"] if g["studentUserId"] == user.id]
    elif role == ROLE_PARENT:
        child_ids = {c.id for c in user.children}
        out["grades"] = [g for g in out["grades"] if g["studentUserId"] in child_ids]
    return out


# ─── grading ────────────────────────────────────────────────────────────

class GradeOne(BaseModel):
    studentUserId: int
    grade:         Optional[int] = None
    feedback:      Optional[str] = None


class GradeBulk(BaseModel):
    grades: list[GradeOne]


def _previous_test_grade(db: Session, student_id: int, subject_id: int, before_date: date_cls, exclude_test_id: int) -> Optional[TestGrade]:
    """Most recent graded TestGrade for the student in this subject, before
    the new test's date. We tie-break on test.id descending so two tests on
    the same day still order deterministically."""
    return (
        db.query(TestGrade)
        .join(Test, TestGrade.test_id == Test.id)
        .filter(
            TestGrade.student_user_id == student_id,
            Test.subject_id           == subject_id,
            TestGrade.grade.isnot(None),
            Test.id                    != exclude_test_id,
            Test.scheduled_date         <= before_date,
        )
        .order_by(Test.scheduled_date.desc(), Test.id.desc())
        .first()
    )


def _maybe_record_improvement(db: Session, t: Test, g: TestGrade) -> None:
    """If the new grade is >= 3 points higher than the student's previous test
    grade in the same subject, drop a TestImprovement row + a notification."""
    if g.grade is None:
        return
    prev = _previous_test_grade(db, g.student_user_id, t.subject_id, t.scheduled_date, t.id)
    if not prev or prev.grade is None:
        return
    if g.grade - prev.grade < BIG_IMPROVEMENT_DELTA:
        return
    db.add(TestImprovement(
        student_user_id=g.student_user_id,
        subject_id=t.subject_id,
        previous_test_id=prev.test_id,
        new_test_id=t.id,
        old_grade=prev.grade,
        new_grade=g.grade,
        created_at=datetime.utcnow(),
    ))
    # also drop a regular notification so the parent sees the good news
    try:
        from notifications import _push, _parent_ids_for_children
        title = f"Progres remarcabil la {t.subject.name if t.subject else ''}!"
        body_text = f"De la {prev.grade} la {g.grade} (+{g.grade - prev.grade} puncte)"
        parent_ids = _parent_ids_for_children(db, [g.student_user_id])
        _push(db, [g.student_user_id] + parent_ids,
              kind="big_improvement", title=title, body=body_text, link="/tests")
    except Exception as _e:
        import logging; logging.getLogger(__name__).warning("improvement notify failed: %s", _e)


@router.post("/{test_id}/grade")
def grade_one(
    test_id: int,
    body: GradeOne,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(Test, test_id)
    if not t:
        raise HTTPException(status_code=404, detail="Testul nu există")
    if not (
        (user.role and user.role.name == ROLE_ADMIN) or
        (t.created_by_user_id == user.id) or
        _teacher_owns(db, user, t.class_id, t.subject_id)
    ):
        raise HTTPException(status_code=403, detail="Nu poți nota acest test")
    if body.grade is not None and not (1 <= body.grade <= 10):
        raise HTTPException(status_code=422, detail="Nota trebuie să fie între 1 și 10")

    # find or create the grade row
    g = db.query(TestGrade).filter_by(test_id=test_id, student_user_id=body.studentUserId).first()
    if not g:
        # student must actually be in the class to be gradeable
        st = db.get(User, body.studentUserId)
        if not st or st.class_id != t.class_id:
            raise HTTPException(status_code=400, detail="Elevul nu face parte din această clasă")
        g = TestGrade(test_id=test_id, student_user_id=body.studentUserId)
        db.add(g)
        db.flush()

    g.grade             = body.grade
    g.feedback          = body.feedback
    g.graded_by_user_id = user.id
    g.graded_at         = datetime.utcnow()
    db.commit()
    db.refresh(g)

    # improvement check fires on every grade update
    _maybe_record_improvement(db, t, g)
    db.commit()
    return {
        "id":            g.id,
        "studentUserId": g.student_user_id,
        "grade":         g.grade,
        "feedback":      g.feedback,
        "gradedAt":      g.graded_at.isoformat() + "Z" if g.graded_at else None,
    }


@router.post("/{test_id}/grade_bulk")
def grade_bulk(
    test_id: int,
    body: GradeBulk,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(Test, test_id)
    if not t:
        raise HTTPException(status_code=404, detail="Testul nu există")
    if not (
        (user.role and user.role.name == ROLE_ADMIN) or
        (t.created_by_user_id == user.id) or
        _teacher_owns(db, user, t.class_id, t.subject_id)
    ):
        raise HTTPException(status_code=403, detail="Nu poți nota acest test")

    updated = 0
    for entry in body.grades:
        if entry.grade is not None and not (1 <= entry.grade <= 10):
            raise HTTPException(status_code=422, detail=f"Nota invalidă pentru elevul {entry.studentUserId}")
        g = db.query(TestGrade).filter_by(test_id=test_id, student_user_id=entry.studentUserId).first()
        if not g:
            st = db.get(User, entry.studentUserId)
            if not st or st.class_id != t.class_id:
                continue
            g = TestGrade(test_id=test_id, student_user_id=entry.studentUserId)
            db.add(g); db.flush()
        g.grade             = entry.grade
        g.feedback          = entry.feedback
        g.graded_by_user_id = user.id
        g.graded_at         = datetime.utcnow()
        db.commit()
        db.refresh(g)
        _maybe_record_improvement(db, t, g)
        updated += 1
    db.commit()
    return {"updated": updated}


# ─── big-improvement splash feed ────────────────────────────────────────

@router.get("/improvements/pending")
def pending_improvements(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return any unack'd improvement events for this student. Parents see
    their children's. Returns at most one row at a time so the splash shows
    them one after another."""
    role = user.role.name if user.role else None
    if role == ROLE_STUDENT:
        target_ids = [user.id]
    elif role == ROLE_PARENT:
        target_ids = [c.id for c in user.children]
    else:
        return []
    if not target_ids:
        return []
    rows = (
        db.query(TestImprovement)
        .filter(
            TestImprovement.student_user_id.in_(target_ids),
            TestImprovement.ack_at.is_(None),
        )
        .order_by(TestImprovement.created_at.asc(), TestImprovement.id.asc())
        .limit(1)
        .all()
    )
    out = []
    for r in rows:
        out.append({
            "id":          r.id,
            "studentUserId": r.student_user_id,
            "subjectName": r.subject.name if r.subject else None,
            "oldGrade":    r.old_grade,
            "newGrade":    r.new_grade,
            "delta":       r.new_grade - r.old_grade,
            "testTitle":   r.new_test.title if r.new_test else None,
            "createdAt":   r.created_at.isoformat() + "Z",
        })
    return out


@router.post("/improvements/{imp_id}/ack")
def ack_improvement(
    imp_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(TestImprovement, imp_id)
    if not r:
        raise HTTPException(status_code=404, detail="Eveniment inexistent")
    role = user.role.name if user.role else None
    # only the student themselves (or one of their parents) can ack
    if role == ROLE_STUDENT and r.student_user_id != user.id:
        raise HTTPException(status_code=403, detail="Nu este al tău")
    if role == ROLE_PARENT and r.student_user_id not in {c.id for c in user.children}:
        raise HTTPException(status_code=403, detail="Nu este copilul tău")
    if role not in (ROLE_STUDENT, ROLE_PARENT):
        raise HTTPException(status_code=403, detail="Doar elevul sau părintele")
    if r.ack_at is None:
        r.ack_at = datetime.utcnow()
        db.commit()
    return {"ok": True}


# ─── lookups for the teacher's create form ──────────────────────────────

@router.get("/lookups/my_assignments")
def my_assignments(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the (class, subject) pairs the caller can announce a test for."""
    role = user.role.name if user.role else None
    if role == ROLE_ADMIN:
        # admin can announce for any class+subject combination
        cls_rows = db.query(SchoolClass).order_by(SchoolClass.name).all()
        sub_rows = db.query(Subject).order_by(Subject.name).all()
        pairs = []
        for cls in cls_rows:
            for sub in sub_rows:
                pairs.append({"classId": cls.id, "className": cls.name,
                              "subjectId": sub.id, "subjectName": sub.name})
        return pairs
    if role != ROLE_TEACHER:
        return []
    rows = db.execute(
        select(teacher_assignment.c.class_id, teacher_assignment.c.subject_id).where(
            teacher_assignment.c.user_id == user.id
        )
    ).all()
    out = []
    for cid, sid in rows:
        cls = db.get(SchoolClass, cid)
        sub = db.get(Subject,     sid)
        if cls and sub:
            out.append({"classId": cls.id, "className": cls.name,
                        "subjectId": sub.id, "subjectName": sub.name})
    return out
