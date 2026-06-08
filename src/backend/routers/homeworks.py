# crud routes for homeworks. assignment 6 adds role-aware filtering so each
# user only sees the homeworks their role allows.
import random
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File, Response
from sqlalchemy.orm import Session

from schemas import (
    HomeworkCreate, HomeworkUpdate,
    HomeworkResponse, PaginatedHomeworks,
)
from database import get_db
from models import (
    Homework, Student, Subject, SchoolClass, User,
    CLASS_ROSTER, ROLE_ADMIN, ROLE_TEACHER, ROLE_USER,
)
from serialize import homework_to_dict, subject_by_name, class_by_name
from auth import get_current_user
from role_filters import (
    homework_visible_filter, can_see_homework, can_post_homework,
    can_grade_homework,
)

router = APIRouter()


def _find_homework(db: Session, hw_id: int) -> Homework:
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(status_code=404, detail=f"Tema cu id={hw_id} nu a fost găsită")
    return hw


# auto fill the student roster (legacy demo behavior so the existing pie chart
# stays populated when an admin creates a homework). teachers can create
# homeworks without auto-filling, since real students will submit themselves.
def _auto_assign_students(db: Session, hw: Homework) -> None:
    class_name = hw.assigned_class.name
    names = CLASS_ROSTER.get(class_name, [])
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ungraded_count = random.randint(2, 3)
    ungraded_idx = set(random.sample(range(len(names)), min(ungraded_count, len(names))))
    for i, name in enumerate(names):
        grade = None if i in ungraded_idx else random.randint(1, 10)
        db.add(Student(
            homework_id=hw.id,
            name=name,
            date_time=now,
            grade=grade,
        ))


# pre-create empty Student rows for every real student user in this class so
# the teacher's gradebook is populated even before anyone submits
def _attach_real_students(db: Session, hw: Homework) -> None:
    rows = db.query(User).filter(
        User.class_id == hw.class_id,
        User.role.has(name="student"),
    ).all()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for u in rows:
        # skip if a row already exists for this (homework, user)
        existing = db.query(Student).filter_by(
            homework_id=hw.id, user_id=u.id
        ).first()
        if existing:
            continue
        db.add(Student(
            homework_id=hw.id,
            user_id=u.id,
            name=u.name,
            date_time=now,
            grade=None,
        ))


@router.post("", response_model=HomeworkResponse, status_code=201)
def create_homework(
    body: HomeworkCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # resolve subject and class names to lookup row ids
    try:
        subj = subject_by_name(db, body.subject)
        cls  = class_by_name(db, body.assignedClass)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"Lookup not seeded: {e}")

    # assignment 6, only admin or a teacher with a matching assignment can post
    if not can_post_homework(db, user, cls.id, subj.id):
        raise HTTPException(
            status_code=403,
            detail="Nu poți crea teme pentru această clasă și materie",
        )

    hw = Homework(
        title=body.title,
        subject_id=subj.id,
        class_id=cls.id,
        due_date=date.fromisoformat(body.dueDate),
        description=body.description,
        file_name=body.fileName,
        created_by_user_id=user.id,
    )
    db.add(hw)
    db.flush()  # need hw.id before inserting students

    # attach real student users for this class so the teacher has a gradebook
    _attach_real_students(db, hw)
    # for admins, also seed the legacy roster so the pie chart has data
    if user.role and user.role.name == ROLE_ADMIN:
        _auto_assign_students(db, hw)

    db.commit()
    db.refresh(hw)
    # notify all students in the class + their parents that a new homework
    # landed. swallowed silently if anything goes wrong, never blocks the
    # success response.
    try:
        from notifications import notify_homework_created
        notify_homework_created(db, hw)
    except Exception as _e:
        import logging; logging.getLogger(__name__).warning("notify_homework_created failed: %s", _e)
    return homework_to_dict(hw)


@router.get("", response_model=PaginatedHomeworks)
def list_homeworks(
        page:     int = Query(default=1,  ge=1),
        pageSize: int = Query(default=10, ge=1, le=100),
        subject:  str | None = Query(default=None),
        assignedClass: str | None = Query(default=None),
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    q = db.query(Homework)
    if subject:
        q = q.join(Subject).filter(Subject.name == subject)
    if assignedClass:
        q = q.join(SchoolClass).filter(SchoolClass.name == assignedClass)

    # assignment 6, narrow by role
    role_filter = homework_visible_filter(db, user)
    if role_filter is not None:
        q = q.filter(role_filter)

    total = q.count()
    totalPages = max(1, -(-total // pageSize))
    items = q.order_by(Homework.id.desc()).offset((page - 1) * pageSize).limit(pageSize).all()

    return PaginatedHomeworks(
        items=[HomeworkResponse(**homework_to_dict(h)) for h in items],
        total=total,
        page=page,
        pageSize=pageSize,
        totalPages=totalPages,
    )


@router.get("/{hw_id}", response_model=HomeworkResponse)
def get_homework(
    hw_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _find_homework(db, hw_id)
    if not can_see_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Nu ai acces la această temă")
    return homework_to_dict(hw)


@router.put("/{hw_id}", response_model=HomeworkResponse)
def update_homework(
    hw_id: int, body: HomeworkUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _find_homework(db, hw_id)
    if not can_grade_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Nu poți modifica această temă")
    data = body.model_dump(exclude_unset=True)
    if "title" in data:
        hw.title = data["title"]
    if "subject" in data:
        try:
            hw.subject_id = subject_by_name(db, data["subject"]).id
        except KeyError:
            raise HTTPException(status_code=422, detail="Materie inexistenta")
    if "assignedClass" in data:
        try:
            hw.class_id = class_by_name(db, data["assignedClass"]).id
        except KeyError:
            raise HTTPException(status_code=422, detail="Clasa inexistenta")
    if "dueDate" in data:
        hw.due_date = date.fromisoformat(data["dueDate"])
    if "description" in data:
        hw.description = data["description"]
    if "fileName" in data:
        hw.file_name = data["fileName"]
    db.commit()
    db.refresh(hw)
    return homework_to_dict(hw)


# homework attachment, teacher uploads bytes after creating the homework so
# that students can download the PDF/image the teacher prepared
MAX_HOMEWORK_FILE_BYTES = 2 * 1024 * 1024  # 2 MB

@router.post("/{hw_id}/attachment")
async def upload_attachment(
    hw_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _find_homework(db, hw_id)
    if not can_grade_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Doar autorul temei poate atașa un fișier")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Niciun fișier")
    blob = await file.read()
    if len(blob) > MAX_HOMEWORK_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Fișierul este prea mare (max 2 MB)")
    hw.file_blob = blob
    hw.file_name = file.filename
    db.commit()
    return {"ok": True, "fileName": file.filename, "size": len(blob)}


@router.get("/{hw_id}/attachment")
def download_attachment(
    hw_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _find_homework(db, hw_id)
    if not can_see_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Nu ai acces la această temă")
    if not hw.file_blob:
        raise HTTPException(status_code=404, detail="Tema nu are fișier atașat")
    return Response(
        content=hw.file_blob,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{hw.file_name or "tema"}"'},
    )


# deleting a homework cascades to students and comments thanks to the FK ondelete
@router.delete("/{hw_id}", status_code=204)
def delete_homework(
    hw_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = _find_homework(db, hw_id)
    if not can_grade_homework(db, user, hw):
        raise HTTPException(status_code=403, detail="Nu poți șterge această temă")
    db.delete(hw)
    db.commit()
