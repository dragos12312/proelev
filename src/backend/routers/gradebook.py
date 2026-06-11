"""
CATALOG (gradebook) router. Returns the right slice of grades per role:

  student  -> their own grades across every homework they've been on
  parent   -> same as student, but for each of their children
  teacher  -> for each (class, subject) they teach, a table of
              students × homeworks → grade
  admin    -> same shape as teacher, but every class/subject in the school

This wraps existing Homework/Student rows; no new tables required.
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from database import get_db
from models import (
    Homework, Student, User, SchoolClass, Subject, teacher_assignment,
    Test, TestGrade, BehaviorGrade,
    ROLE_ADMIN, ROLE_USER, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)
from auth import get_current_user


router = APIRouter()


def _student_view(db: Session, student_user: User) -> dict:
    """Every homework + test the student has a row on, plus their behavior
    grade. Average combines both homework and test grades."""
    if student_user.class_id is None:
        return {"name": student_user.name, "class": None, "rows": [], "tests": [], "behavior": None}

    rows = (
        db.query(Student, Homework)
        .join(Homework, Student.homework_id == Homework.id)
        .filter(Student.user_id == student_user.id)
        .order_by(Homework.due_date.desc(), Homework.id.desc())
        .all()
    )
    out = []
    grades_only = []
    for s, hw in rows:
        out.append({
            "homeworkId": hw.id,
            "title":      hw.title,
            "subject":    hw.subject.name if hw.subject else None,
            "dueDate":    hw.due_date.isoformat() if hw.due_date else None,
            "grade":      s.grade,
            "feedback":   s.feedback,
            "submitted":  s.submitted_at is not None,
        })
        if s.grade is not None:
            grades_only.append(s.grade)

    # test grades for this student
    test_rows = (
        db.query(TestGrade, Test)
        .join(Test, TestGrade.test_id == Test.id)
        .filter(TestGrade.student_user_id == student_user.id)
        .order_by(Test.scheduled_date.desc(), Test.id.desc())
        .all()
    )
    tests_out = []
    for tg, t in test_rows:
        tests_out.append({
            "testId":    t.id,
            "title":     t.title,
            "subject":   t.subject.name if t.subject else None,
            "date":      t.scheduled_date.isoformat() if t.scheduled_date else None,
            "grade":     tg.grade,
            "feedback":  tg.feedback,
        })
        if tg.grade is not None:
            grades_only.append(tg.grade)

    avg = round(sum(grades_only) / len(grades_only), 2) if grades_only else None

    # most recent behavior grade
    beh = (
        db.query(BehaviorGrade)
        .filter(BehaviorGrade.student_user_id == student_user.id)
        .order_by(BehaviorGrade.created_at.desc())
        .first()
    )
    behavior_payload = None
    if beh:
        behavior_payload = {
            "id":     beh.id,
            "period": beh.period,
            "grade":  beh.grade,
            "note":   beh.note,
        }

    cls = student_user.school_class
    return {
        "userId":   student_user.id,
        "name":     student_user.name,
        "class":    {"id": cls.id, "name": cls.name} if cls else None,
        "average":  avg,
        "rows":     out,
        "tests":    tests_out,
        "behavior": behavior_payload,
    }


def _teacher_view(db: Session, teacher_user: User) -> list[dict]:
    """For each (class, subject) the teacher is assigned to, build a
    students × homeworks → grade matrix."""
    pairs = db.execute(
        select(teacher_assignment.c.class_id, teacher_assignment.c.subject_id)
        .where(teacher_assignment.c.user_id == teacher_user.id)
    ).all()
    return [_class_subject_matrix(db, cid, sid) for cid, sid in pairs]


def _admin_view(db: Session) -> list[dict]:
    """Every (class, subject) combination that actually has homeworks."""
    pairs = db.execute(
        select(Homework.class_id, Homework.subject_id).distinct()
    ).all()
    return [_class_subject_matrix(db, cid, sid) for cid, sid in pairs]


def _class_subject_matrix(db: Session, class_id: int, subject_id: int) -> dict:
    """One block of the teacher/admin gradebook. Builds the homework columns,
    the student rows, and the grade cells."""
    cls = db.get(SchoolClass, class_id)
    sub = db.get(Subject,     subject_id)

    homeworks = (
        db.query(Homework)
        .filter(Homework.class_id == class_id, Homework.subject_id == subject_id)
        .order_by(Homework.due_date.asc(), Homework.id.asc())
        .all()
    )
    hw_ids = [h.id for h in homeworks]

    # students that actually have a row on at least one of these homeworks
    # (covers both real student users and legacy roster names)
    if hw_ids:
        student_rows = (
            db.query(Student)
            .filter(Student.homework_id.in_(hw_ids))
            .order_by(Student.name.asc(), Student.id.asc())
            .all()
        )
    else:
        student_rows = []

    # group by student name so a kid that appears in N homeworks gets one row
    by_name: dict[str, dict] = {}
    for s in student_rows:
        if s.name not in by_name:
            by_name[s.name] = {
                "name":   s.name,
                "userId": s.user_id,
                "grades": {},
            }
        by_name[s.name]["grades"][s.homework_id] = {
            "grade":    s.grade,
            "feedback": s.feedback,
            "submitted": s.submitted_at is not None,
        }

    # per-student average + class average for the bottom row
    students_out = []
    for row in by_name.values():
        nums = [g["grade"] for g in row["grades"].values() if g["grade"] is not None]
        row["average"] = round(sum(nums) / len(nums), 2) if nums else None
        students_out.append(row)

    all_grades = [
        g["grade"] for r in students_out for g in r["grades"].values()
        if g["grade"] is not None
    ]
    class_avg = round(sum(all_grades) / len(all_grades), 2) if all_grades else None

    return {
        "class":   {"id": cls.id, "name": cls.name} if cls else None,
        "subject": {"id": sub.id, "name": sub.name} if sub else None,
        "homeworks": [
            {"id": h.id, "title": h.title,
             "dueDate": h.due_date.isoformat() if h.due_date else None}
            for h in homeworks
        ],
        "students": students_out,
        "classAverage": class_avg,
    }


@router.get("")
def my_gradebook(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Top-level dispatch. Returns a different shape per role; the frontend
    keys off `viewKind` to pick the right component."""
    role = user.role.name if user.role else None

    if role == ROLE_STUDENT:
        return {"viewKind": "student", "data": _student_view(db, user)}

    if role == ROLE_PARENT:
        children = [
            _student_view(db, c) for c in user.children
        ]
        return {"viewKind": "parent", "children": children}

    if role == ROLE_TEACHER:
        return {"viewKind": "teacher", "blocks": _teacher_view(db, user)}

    if role in (ROLE_ADMIN, ROLE_USER):
        return {"viewKind": "admin", "blocks": _admin_view(db)}

    raise HTTPException(status_code=403, detail="Rolul tău nu are catalog")
