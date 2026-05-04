# students are always scoped to a specific homework, hence the nested /homeworks/{id}/students urls
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from schemas import (
    StudentCreate, StudentUpdate,
    StudentResponse, PaginatedStudents,
    HomeworkStatistics, GradeDistribution,
)
from database import get_db
from models import Homework, Student
from serialize import student_to_dict

router = APIRouter()


# makes sure the parent homework actually exists before we do anything with its students
def _require_homework(db: Session, hw_id: int) -> Homework:
    hw = db.get(Homework, hw_id)
    if not hw:
        raise HTTPException(status_code=404, detail=f"Tema cu id={hw_id} nu a fost găsită")
    return hw


# look up one student under a specific homework
def _find_student(db: Session, hw_id: int, student_id: int) -> Student:
    s = db.query(Student).filter_by(id=student_id, homework_id=hw_id).first()
    if not s:
        raise HTTPException(
            status_code=404,
            detail=f"Elevul cu id={student_id} nu a fost găsit pentru tema {hw_id}"
        )
    return s


# basic crud below, create, list, get, update, delete

@router.post("/{hw_id}/students", response_model=StudentResponse, status_code=201)
def add_student(hw_id: int, body: StudentCreate, db: Session = Depends(get_db)):
    _require_homework(db, hw_id)
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
    db: Session = Depends(get_db),
):
    _require_homework(db, hw_id)
    q = db.query(Student).filter_by(homework_id=hw_id)
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
def get_student(hw_id: int, student_id: int, db: Session = Depends(get_db)):
    _require_homework(db, hw_id)
    return student_to_dict(_find_student(db, hw_id, student_id))


@router.put("/{hw_id}/students/{student_id}", response_model=StudentResponse)
def update_student(hw_id: int, student_id: int, body: StudentUpdate, db: Session = Depends(get_db)):
    _require_homework(db, hw_id)
    s = _find_student(db, hw_id, student_id)
    data = body.model_dump(exclude_unset=True)
    if "name"     in data: s.name      = data["name"]
    if "dateTime" in data: s.date_time = data["dateTime"]
    if "grade"    in data: s.grade     = data["grade"]
    db.commit()
    db.refresh(s)
    return student_to_dict(s)


@router.delete("/{hw_id}/students/{student_id}", status_code=204)
def delete_student(hw_id: int, student_id: int, db: Session = Depends(get_db)):
    _require_homework(db, hw_id)
    s = _find_student(db, hw_id, student_id)
    db.delete(s)
    db.commit()


# all the numbers the stats page needs, computed on the fly from the students list
@router.get("/{hw_id}/statistics", response_model=HomeworkStatistics)
def get_statistics(hw_id: int, db: Session = Depends(get_db)):
    _require_homework(db, hw_id)
    students = db.query(Student).filter_by(homework_id=hw_id).all()

    # split into passed, failed and still ungraded
    graded   = [s for s in students if s.grade is not None]
    passed   = [s for s in graded   if s.grade >= 5]
    failed   = [s for s in graded   if s.grade <  5]
    ungraded = [s for s in students if s.grade is None]

    avg = round(sum(s.grade for s in graded) / len(graded), 2) if graded else None

    # one bucket per grade from 10 down to 5, plus one for under 5 and one for no grade
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
