# graphql schema, optional silver challenge, same data as the rest endpoints
# reuse the pydantic models from schemas.py so validation rules only live in one place
# the data layer is sqlalchemy now, every resolver opens its own session
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List

import strawberry
from pydantic import ValidationError

import schemas
from database import SessionLocal
from models import (
    Homework as HomeworkModel,
    Student as StudentModel,
    Comment as CommentModel,
    Subject, SchoolClass,
)
from serialize import subject_by_name, class_by_name


# object types, basicly the shape of the data the client gets back

@strawberry.type
class Student:
    id: int
    homeworkId: int
    name: str
    dateTime: str
    grade: Optional[int]


@strawberry.type
class Comment:
    id: int
    homeworkId: int
    author: str
    text: str
    createdAt: str


@strawberry.type
class Homework:
    id: int
    title: str
    subject: str
    assignedClass: str
    dueDate: str
    description: Optional[str]
    fileName: Optional[str]

    @strawberry.field
    def students(self) -> List[Student]:
        db = SessionLocal()
        try:
            rows = db.query(StudentModel).filter_by(homework_id=self.id).all()
            return [_student_from_orm(s) for s in rows]
        finally:
            db.close()

    @strawberry.field
    def comments(self) -> List[Comment]:
        db = SessionLocal()
        try:
            rows = db.query(CommentModel).filter_by(homework_id=self.id).all()
            return [_comment_from_orm(c) for c in rows]
        finally:
            db.close()


@strawberry.type
class PaginatedHomeworks:
    items: List[Homework]
    total: int
    page: int
    pageSize: int
    totalPages: int


@strawberry.type
class GradeBucket:
    grade: str
    count: int


@strawberry.type
class HomeworkStatistics:
    homeworkId: int
    totalStudents: int
    passed: int
    failed: int
    ungraded: int
    averageGrade: Optional[float]
    gradeDistribution: List[GradeBucket]


@strawberry.type
class CommentStatistics:
    homeworkId: int
    totalComments: int
    uniqueAuthors: int
    averageTextLength: float
    topAuthor: Optional[str]


# input types for mutations, one full input and one patch input per entity

@strawberry.input
class HomeworkInput:
    title: str
    subject: str
    assignedClass: str
    dueDate: str
    description: Optional[str] = None
    fileName: Optional[str] = None


@strawberry.input
class HomeworkPatch:
    title: Optional[str] = None
    subject: Optional[str] = None
    assignedClass: Optional[str] = None
    dueDate: Optional[str] = None
    description: Optional[str] = None
    fileName: Optional[str] = None


@strawberry.input
class StudentInput:
    name: str
    dateTime: str
    grade: Optional[int] = None


@strawberry.input
class StudentPatch:
    name: Optional[str] = None
    dateTime: Optional[str] = None
    grade: Optional[int] = None


@strawberry.input
class CommentInput:
    author: str
    text: str


@strawberry.input
class CommentPatch:
    author: Optional[str] = None
    text: Optional[str] = None


# small helpers, build the strawberry type from an orm row

def _homework_from_orm(hw: HomeworkModel) -> Homework:
    return Homework(
        id=hw.id,
        title=hw.title,
        subject=hw.subject.name if hw.subject else "",
        assignedClass=hw.assigned_class.name if hw.assigned_class else "",
        dueDate=hw.due_date.isoformat() if hw.due_date else "",
        description=hw.description,
        fileName=hw.file_name,
    )


def _student_from_orm(s: StudentModel) -> Student:
    return Student(
        id=s.id, homeworkId=s.homework_id, name=s.name,
        dateTime=s.date_time, grade=s.grade,
    )


def _comment_from_orm(c: CommentModel) -> Comment:
    return Comment(
        id=c.id, homeworkId=c.homework_id, author=c.author,
        text=c.text, createdAt=c.created_at,
    )


# runs the data through the pydantic model, if validation fails we turn it into a graphql error

def _validate(pydantic_cls, **data):
    try:
        return pydantic_cls(**data)
    except ValidationError as e:
        # only show the first error, keeps the client response short
        first = e.errors()[0]
        msg = first.get("msg", "Date invalide")
        raise Exception(msg)


def _require_homework(db, hw_id: int) -> HomeworkModel:
    hw = db.get(HomeworkModel, hw_id)
    if not hw:
        raise Exception(f"Tema cu id={hw_id} nu a fost găsită")
    return hw


# all the read only fields, same shape as the rest get endpoints

@strawberry.type
class Query:
    @strawberry.field
    def homeworks(
        self,
        page: int = 1,
        pageSize: int = 10,
        subject: Optional[str] = None,
        assignedClass: Optional[str] = None,
    ) -> PaginatedHomeworks:
        db = SessionLocal()
        try:
            q = db.query(HomeworkModel)
            if subject:
                q = q.join(Subject).filter(Subject.name == subject)
            if assignedClass:
                q = q.join(SchoolClass).filter(SchoolClass.name == assignedClass)
            total = q.count()
            totalPages = max(1, -(-total // pageSize))
            rows = q.order_by(HomeworkModel.id).offset((page - 1) * pageSize).limit(pageSize).all()
            return PaginatedHomeworks(
                items=[_homework_from_orm(h) for h in rows],
                total=total, page=page, pageSize=pageSize, totalPages=totalPages,
            )
        finally:
            db.close()

    @strawberry.field
    def homework(self, id: int) -> Optional[Homework]:
        db = SessionLocal()
        try:
            hw = db.get(HomeworkModel, id)
            return _homework_from_orm(hw) if hw else None
        finally:
            db.close()

    @strawberry.field
    def students(self, homeworkId: int) -> List[Student]:
        db = SessionLocal()
        try:
            return [_student_from_orm(s) for s in db.query(StudentModel).filter_by(homework_id=homeworkId).all()]
        finally:
            db.close()

    @strawberry.field
    def homeworkStatistics(self, homeworkId: int) -> HomeworkStatistics:
        db = SessionLocal()
        try:
            _require_homework(db, homeworkId)
            students = db.query(StudentModel).filter_by(homework_id=homeworkId).all()
            graded = [s for s in students if s.grade is not None]
            passed = [s for s in graded if s.grade >= 5]
            failed = [s for s in graded if s.grade < 5]
            ungraded = [s for s in students if s.grade is None]
            avg = round(sum(s.grade for s in graded) / len(graded), 2) if graded else None
            buckets = {str(g): 0 for g in range(10, 4, -1)}
            buckets["<5"] = 0
            buckets["FĂRĂ NOTĂ"] = 0
            for s in students:
                if s.grade is None:
                    buckets["FĂRĂ NOTĂ"] += 1
                elif s.grade < 5:
                    buckets["<5"] += 1
                else:
                    buckets[str(s.grade)] += 1
            return HomeworkStatistics(
                homeworkId=homeworkId,
                totalStudents=len(students),
                passed=len(passed),
                failed=len(failed),
                ungraded=len(ungraded),
                averageGrade=avg,
                gradeDistribution=[GradeBucket(grade=k, count=v) for k, v in buckets.items()],
            )
        finally:
            db.close()

    @strawberry.field
    def comments(self, homeworkId: int) -> List[Comment]:
        db = SessionLocal()
        try:
            _require_homework(db, homeworkId)
            return [_comment_from_orm(c) for c in db.query(CommentModel).filter_by(homework_id=homeworkId).all()]
        finally:
            db.close()

    @strawberry.field
    def commentStatistics(self, homeworkId: int) -> CommentStatistics:
        db = SessionLocal()
        try:
            _require_homework(db, homeworkId)
            items = db.query(CommentModel).filter_by(homework_id=homeworkId).all()
            authors = [c.author for c in items]
            counts: dict = {}
            for a in authors:
                counts[a] = counts.get(a, 0) + 1
            top = max(counts, key=counts.get) if counts else None
            avg_len = (sum(len(c.text) for c in items) / len(items)) if items else 0.0
            return CommentStatistics(
                homeworkId=homeworkId,
                totalComments=len(items),
                uniqueAuthors=len(set(authors)),
                averageTextLength=round(avg_len, 2),
                topAuthor=top,
            )
        finally:
            db.close()


# every write operation lives here, create update delete for each entity

@strawberry.type
class Mutation:
    # homework create, update, delete
    @strawberry.mutation
    def createHomework(self, input: HomeworkInput) -> Homework:
        v = _validate(schemas.HomeworkCreate, **strawberry.asdict(input))
        db = SessionLocal()
        try:
            try:
                subj = subject_by_name(db, v.subject)
                cls  = class_by_name(db, v.assignedClass)
            except KeyError as e:
                raise Exception(f"Lookup not seeded: {e}")
            hw = HomeworkModel(
                title=v.title,
                subject_id=subj.id,
                class_id=cls.id,
                due_date=date.fromisoformat(v.dueDate),
                description=v.description,
                file_name=v.fileName,
            )
            db.add(hw)
            db.flush()
            # same auto assign as the rest route does so both paths behave the same
            from routers.homeworks import _auto_assign_students
            _auto_assign_students(db, hw)
            db.commit()
            db.refresh(hw)
            return _homework_from_orm(hw)
        finally:
            db.close()

    @strawberry.mutation
    def updateHomework(self, id: int, patch: HomeworkPatch) -> Homework:
        db = SessionLocal()
        try:
            hw = _require_homework(db, id)
            data = {k: v for k, v in strawberry.asdict(patch).items() if v is not None}
            v = _validate(schemas.HomeworkUpdate, **data)
            d = v.model_dump(exclude_unset=True)
            if "title"   in d: hw.title = d["title"]
            if "subject" in d:
                hw.subject_id = subject_by_name(db, d["subject"]).id
            if "assignedClass" in d:
                hw.class_id = class_by_name(db, d["assignedClass"]).id
            if "dueDate" in d:
                hw.due_date = date.fromisoformat(d["dueDate"])
            if "description" in d: hw.description = d["description"]
            if "fileName"    in d: hw.file_name   = d["fileName"]
            db.commit()
            db.refresh(hw)
            return _homework_from_orm(hw)
        finally:
            db.close()

    @strawberry.mutation
    def deleteHomework(self, id: int) -> bool:
        db = SessionLocal()
        try:
            hw = _require_homework(db, id)
            db.delete(hw)
            db.commit()
            return True
        finally:
            db.close()

    # student crud, always nested under a homework
    @strawberry.mutation
    def createStudent(self, homeworkId: int, input: StudentInput) -> Student:
        db = SessionLocal()
        try:
            _require_homework(db, homeworkId)
            v = _validate(schemas.StudentCreate, **strawberry.asdict(input))
            s = StudentModel(
                homework_id=homeworkId,
                name=v.name, date_time=v.dateTime, grade=v.grade,
            )
            db.add(s)
            db.commit()
            db.refresh(s)
            return _student_from_orm(s)
        finally:
            db.close()

    @strawberry.mutation
    def updateStudent(self, homeworkId: int, id: int, patch: StudentPatch) -> Student:
        db = SessionLocal()
        try:
            _require_homework(db, homeworkId)
            s = db.query(StudentModel).filter_by(id=id, homework_id=homeworkId).first()
            if not s:
                raise Exception(f"Elevul cu id={id} nu a fost găsit pentru tema {homeworkId}")
            data = {k: v for k, v in strawberry.asdict(patch).items() if v is not None}
            v = _validate(schemas.StudentUpdate, **data)
            d = v.model_dump(exclude_unset=True)
            if "name"     in d: s.name      = d["name"]
            if "dateTime" in d: s.date_time = d["dateTime"]
            if "grade"    in d: s.grade     = d["grade"]
            db.commit()
            db.refresh(s)
            return _student_from_orm(s)
        finally:
            db.close()

    @strawberry.mutation
    def deleteStudent(self, homeworkId: int, id: int) -> bool:
        db = SessionLocal()
        try:
            _require_homework(db, homeworkId)
            s = db.query(StudentModel).filter_by(id=id, homework_id=homeworkId).first()
            if not s:
                raise Exception(f"Elevul cu id={id} nu a fost găsit pentru tema {homeworkId}")
            db.delete(s)
            db.commit()
            return True
        finally:
            db.close()

    # comment crud, the new 1 to many entity i added for the assignment
    @strawberry.mutation
    def createComment(self, homeworkId: int, input: CommentInput) -> Comment:
        db = SessionLocal()
        try:
            _require_homework(db, homeworkId)
            v = _validate(schemas.CommentCreate, **strawberry.asdict(input))
            c = CommentModel(
                homework_id=homeworkId,
                author=v.author, text=v.text,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
            db.add(c)
            db.commit()
            db.refresh(c)
            return _comment_from_orm(c)
        finally:
            db.close()

    @strawberry.mutation
    def updateComment(self, homeworkId: int, id: int, patch: CommentPatch) -> Comment:
        db = SessionLocal()
        try:
            _require_homework(db, homeworkId)
            c = db.query(CommentModel).filter_by(id=id, homework_id=homeworkId).first()
            if not c:
                raise Exception(f"Comentariul cu id={id} nu a fost găsit pentru tema {homeworkId}")
            data = {k: v for k, v in strawberry.asdict(patch).items() if v is not None}
            v = _validate(schemas.CommentUpdate, **data)
            d = v.model_dump(exclude_unset=True)
            if "author" in d: c.author = d["author"]
            if "text"   in d: c.text   = d["text"]
            db.commit()
            db.refresh(c)
            return _comment_from_orm(c)
        finally:
            db.close()

    @strawberry.mutation
    def deleteComment(self, homeworkId: int, id: int) -> bool:
        db = SessionLocal()
        try:
            _require_homework(db, homeworkId)
            c = db.query(CommentModel).filter_by(id=id, homework_id=homeworkId).first()
            if not c:
                raise Exception(f"Comentariul cu id={id} nu a fost găsit pentru tema {homeworkId}")
            db.delete(c)
            db.commit()
            return True
        finally:
            db.close()


schema = strawberry.Schema(query=Query, mutation=Mutation)
