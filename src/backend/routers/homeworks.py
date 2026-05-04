# crud routes for homeworks, also handles pagination for the infinite scroll
# everything goes through sqlalchemy now, no more in memory lists
import random
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from schemas import (
    HomeworkCreate, HomeworkUpdate,
    HomeworkResponse, PaginatedHomeworks,
)
from database import get_db
from models import Homework, Student, Subject, SchoolClass, CLASS_ROSTER
from serialize import homework_to_dict, subject_by_name, class_by_name

router = APIRouter()


# small helper, looks up one homework by id or raises 404
def _find_homework(db: Session, hw_id: int) -> Homework:
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(status_code=404, detail=f"Tema cu id={hw_id} nu a fost găsită")
    return hw


# when a homework is created we auto fill the student list from the class roster
# most students get a random grade 1 to 10, but 2 or 3 are left ungraded
# so the stats page still shows a fara nota slice in the pie
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


@router.post("", response_model=HomeworkResponse, status_code=201)
def create_homework(body: HomeworkCreate, db: Session = Depends(get_db)):
    # resolve subject and class names to lookup row ids
    try:
        subj = subject_by_name(db, body.subject)
        cls  = class_by_name(db, body.assignedClass)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"Lookup not seeded: {e}")

    hw = Homework(
        title=body.title,
        subject_id=subj.id,
        class_id=cls.id,
        due_date=date.fromisoformat(body.dueDate),
        description=body.description,
        file_name=body.fileName,
    )
    db.add(hw)
    db.flush()  # need hw.id before inserting students
    _auto_assign_students(db, hw)
    db.commit()
    db.refresh(hw)
    return homework_to_dict(hw)


@router.get("", response_model=PaginatedHomeworks)
def list_homeworks(
        page:     int = Query(default=1,  ge=1),
        pageSize: int = Query(default=10, ge=1, le=100),
        subject:  str | None = Query(default=None),
        assignedClass: str | None = Query(default=None),
        db: Session = Depends(get_db),
):
    # build the query with optional filters, both come from the lookup tables
    q = db.query(Homework)
    if subject:
        q = q.join(Subject).filter(Subject.name == subject)
    if assignedClass:
        q = q.join(SchoolClass).filter(SchoolClass.name == assignedClass)

    total = q.count()
    totalPages = max(1, -(-total // pageSize))
    items = q.order_by(Homework.id).offset((page - 1) * pageSize).limit(pageSize).all()

    return PaginatedHomeworks(
        items=[HomeworkResponse(**homework_to_dict(h)) for h in items],
        total=total,
        page=page,
        pageSize=pageSize,
        totalPages=totalPages,
    )


@router.get("/{hw_id}", response_model=HomeworkResponse)
def get_homework(hw_id: int, db: Session = Depends(get_db)):
    hw = _find_homework(db, hw_id)
    return homework_to_dict(hw)


@router.put("/{hw_id}", response_model=HomeworkResponse)
def update_homework(hw_id: int, body: HomeworkUpdate, db: Session = Depends(get_db)):
    hw = _find_homework(db, hw_id)
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


# deleting a homework cascades to students and comments thanks to the FK ondelete
@router.delete("/{hw_id}", status_code=204)
def delete_homework(hw_id: int, db: Session = Depends(get_db)):
    hw = _find_homework(db, hw_id)
    db.delete(hw)
    db.commit()
