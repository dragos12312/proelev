# students are always scoped to a specific homework, hence the nested
# /homeworks/{id}/students urls. assignment 6 extends them with submission
# (student uploads text + optional file) and grading (teacher fills grade +
# feedback). list and stats are role-aware so students/parents only see what
# they should.
import base64
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File, Form, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from schemas import (
    StudentCreate, StudentUpdate,
    StudentResponse, PaginatedStudents,
    HomeworkStatistics, GradeDistribution,
)
from database import get_db
from models import (
    Homework, Student, User,
    ROLE_ADMIN, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT, ROLE_USER,
)
from serialize import student_to_dict
from auth import get_current_user
from role_filters import can_see_homework, can_grade_homework

router = APIRouter()


def _require_homework(db: Session, hw_id: int) -> Homework:
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(status_code=404, detail=f"Tema cu id={hw_id} nu a fost găsită")
    return hw


def _find_student(db: Session, hw_id: int, student_id: int) -> Student:
    s = db.query(Student).filter_by(id=student_id, homework_id=hw_id).first()
    if not s:
        raise HTTPException(
            status_code=404,
            detail=f"Elevul cu id={student_id} nu a fost găsit pentru tema {hw_id}"
        )
    return s


def _filtered_students(db: Session, user: User, hw: Homework):
    """Return the subset of student rows the caller is allowed to see."""
    role = user.role.name if user.role else None
    q = db.query(Student).filter_by(homework_id=hw.id)
    if role in (ROLE_ADMIN, ROLE_USER):
        return q
    if role == ROLE_TEACHER:
        # teachers see all submissions for homeworks they can grade
        if can_grade_homework(db, user, hw):
            return q
        # teachers who only see the homework (not own) get no students
        return q.filter(Student.id == -1)
    if role == ROLE_STUDENT:
        # student only sees their own submission row
        return q.filter(Student.user_id == user.id)
    if role == ROLE_PARENT:
        child_ids = [c.id for c in user.children]
        return q.filter(Student.user_id.in_(child_ids))
    return q.filter(Student.id == -1)


# ─── plain CRUD (admin convenience, untouched logic) ─────────────────────

@router.post("/{hw_id}/students", response_model=StudentResponse, status_code=201)
def add_student(
    hw_id: int, body: StudentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _require_homework(db, hw_id)
    if not can_grade_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Nu poți adăuga elevi aici")
    s = Student(
        homework_id=hw_id,
        name=body.name,
        date_time=body.dateTime,
        grade=body.grade,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return student_to_dict(s)


@router.get("/{hw_id}/students", response_model=PaginatedStudents)
def list_students(
    hw_id:    int,
    page:     int = Query(default=1,  ge=1),
    pageSize: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _require_homework(db, hw_id)
    if not can_see_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Nu ai acces la această temă")

    q = _filtered_students(db, user, hw)
    total = q.count()
    totalPages = max(1, -(-total // pageSize))
    items = q.order_by(Student.id).offset((page - 1) * pageSize).limit(pageSize).all()

    return PaginatedStudents(
        items=[StudentResponse(**student_to_dict(s)) for s in items],
        total=total,
        page=page,
        pageSize=pageSize,
        totalPages=totalPages,
    )


@router.get("/{hw_id}/students/{student_id}", response_model=StudentResponse)
def get_student(
    hw_id: int, student_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _require_homework(db, hw_id)
    if not can_see_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Nu ai acces la această temă")
    s = _find_student(db, hw_id, student_id)
    # row-level check, student/parent only see their own
    role = user.role.name if user.role else None
    if role == ROLE_STUDENT and s.user_id != user.id:
        raise HTTPException(status_code=403, detail="Nu ai acces la acest elev")
    if role == ROLE_PARENT and s.user_id not in {c.id for c in user.children}:
        raise HTTPException(status_code=403, detail="Nu ai acces la acest elev")
    return student_to_dict(s)


@router.put("/{hw_id}/students/{student_id}", response_model=StudentResponse)
def update_student(
    hw_id: int, student_id: int, body: StudentUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _require_homework(db, hw_id)
    if not can_grade_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Doar profesorul poate modifica")
    s = _find_student(db, hw_id, student_id)
    data = body.model_dump(exclude_unset=True)
    if "name"     in data: s.name      = data["name"]
    if "dateTime" in data: s.date_time = data["dateTime"]
    if "grade"    in data: s.grade     = data["grade"]
    db.commit()
    db.refresh(s)
    return student_to_dict(s)


@router.delete("/{hw_id}/students/{student_id}", status_code=204)
def delete_student(
    hw_id: int, student_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _require_homework(db, hw_id)
    if not can_grade_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Doar profesorul poate șterge")
    s = _find_student(db, hw_id, student_id)
    db.delete(s)
    db.commit()


# ─── assignment 6: submit + grade ────────────────────────────────────────

MAX_SUBMISSION_BYTES = 1 * 1024 * 1024  # 1 MB


@router.post("/{hw_id}/submit", response_model=StudentResponse)
async def submit_homework(
    hw_id: int,
    text: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Student uploads their submission. Body is multipart:
       text (optional string) + file (optional binary).
       Updates or inserts the Student row tied to this user + homework."""
    role = user.role.name if user.role else None
    if role != ROLE_STUDENT:
        raise HTTPException(status_code=403, detail="Doar elevii pot trimite teme")
    hw = _require_homework(db, hw_id)
    if not can_see_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Tema nu este pentru clasa ta")

    if not text and (file is None or not file.filename):
        raise HTTPException(status_code=400, detail="Trimite text sau atașează un fișier")

    file_bytes: Optional[bytes] = None
    file_name:  Optional[str]   = None
    if file is not None and file.filename:
        file_bytes = await file.read()
        if file_bytes is not None and len(file_bytes) > MAX_SUBMISSION_BYTES:
            raise HTTPException(status_code=413, detail="Fișierul este prea mare (max 1 MB)")
        file_name = file.filename

    s = db.query(Student).filter_by(homework_id=hw_id, user_id=user.id).first()
    if not s:
        s = Student(
            homework_id=hw_id,
            user_id=user.id,
            name=user.name,
            date_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        db.add(s)

    s.submitted_at         = datetime.utcnow()
    s.submission_text      = (text or None)
    if file_bytes is not None:
        s.submission_blob      = file_bytes
        s.submission_file_name = file_name
    db.commit()
    db.refresh(s)
    # notify the teacher who created this homework that a student turned it in
    try:
        from notifications import notify_submission_uploaded
        notify_submission_uploaded(db, hw, user)
    except Exception as _e:
        import logging; logging.getLogger(__name__).warning("notify_submission_uploaded failed: %s", _e)
    return student_to_dict(s)


class GradeBody(BaseModel):
    grade:    Optional[int] = None
    feedback: Optional[str] = None


@router.put("/{hw_id}/students/{student_id}/grade", response_model=StudentResponse)
def grade_submission(
    hw_id: int, student_id: int, body: GradeBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _require_homework(db, hw_id)
    if not can_grade_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Nu poți nota această temă")
    s = _find_student(db, hw_id, student_id)
    if body.grade is not None:
        if not (1 <= body.grade <= 10):
            raise HTTPException(status_code=422, detail="Nota trebuie să fie între 1 și 10")
        s.grade = body.grade
    if body.feedback is not None:
        s.feedback = body.feedback
    db.commit()
    db.refresh(s)
    # notify the student (and their parents) that a grade / feedback landed
    try:
        from notifications import notify_grade_given
        notify_grade_given(db, hw, s, body.grade, body.feedback)
    except Exception as _e:
        import logging; logging.getLogger(__name__).warning("notify_grade_given failed: %s", _e)
    return student_to_dict(s)


@router.get("/{hw_id}/students/{student_id}/file")
def download_submission_file(
    hw_id: int, student_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream back the uploaded file bytes for a submission. Visibility follows
    the same rules as the student row itself."""
    hw = _require_homework(db, hw_id)
    if not can_see_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Nu ai acces la această temă")
    s = _find_student(db, hw_id, student_id)
    role = user.role.name if user.role else None
    if role == ROLE_STUDENT and s.user_id != user.id:
        raise HTTPException(status_code=403, detail="Nu ai acces")
    if role == ROLE_PARENT and s.user_id not in {c.id for c in user.children}:
        raise HTTPException(status_code=403, detail="Nu ai acces")
    if not s.submission_blob:
        raise HTTPException(status_code=404, detail="Niciun fișier")
    return Response(
        content=s.submission_blob,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{s.submission_file_name or "submission"}"'},
    )


# ─── statistics, locked down for student/parent ──────────────────────────

@router.get("/{hw_id}/statistics", response_model=HomeworkStatistics)
def get_statistics(
    hw_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _require_homework(db, hw_id)
    role = user.role.name if user.role else None
    if role in (ROLE_STUDENT, ROLE_PARENT):
        raise HTTPException(status_code=403, detail="Statisticile nu sunt vizibile pentru rolul tău")
    if not can_see_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Nu ai acces la această temă")

    students = db.query(Student).filter_by(homework_id=hw_id).all()

    graded   = [s for s in students if s.grade is not None]
    passed   = [s for s in graded   if s.grade >= 5]
    failed   = [s for s in graded   if s.grade <  5]
    ungraded = [s for s in students if s.grade is None]

    avg = round(sum(s.grade for s in graded) / len(graded), 2) if graded else None

    buckets = {str(g): 0 for g in range(10, 4, -1)}
    buckets["<5"]        = 0
    buckets["FĂRĂ NOTĂ"] = 0
    for s in students:
        if s.grade is None:
            buckets["FĂRĂ NOTĂ"] += 1
        elif s.grade < 5:
            buckets["<5"] += 1
        else:
            buckets[str(s.grade)] += 1

    distribution = [GradeDistribution(grade=k, count=v) for k, v in buckets.items()]

    return HomeworkStatistics(
        homeworkId=hw_id,
        totalStudents=len(students),
        passed=len(passed),
        failed=len(failed),
        ungraded=len(ungraded),
        averageGrade=avg,
        gradeDistribution=distribution,
    )
