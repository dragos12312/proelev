"""
CATALOG (gradebook) router. Returns the right slice of grades per role:

  student  -> their own grades across every homework they've been on
  parent   -> same as student, but for each of their children
  teacher  -> for each (class, subject) they teach, a table of
              students × homeworks → grade
  admin    -> same shape as teacher, but every class/subject in the school

This wraps existing Homework/Student rows; no new tables required.
"""
import io
from fastapi import APIRouter, HTTPException, Depends, Response
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


@router.get("/export.pdf")
def export_pdf(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Render the same role-aware catalog into a printable PDF.

    Layout: title line, "generat la / pentru", then per role:
      student   -> one big table of (subject, tema, dată, notă)
                   followed by Teste table and Media la purtare line
      parent    -> the same for each child
      teacher   -> per-block summary: (class, subject), N teme, class avg
      admin     -> same as teacher
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak,
    )
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from datetime import datetime as _dt

    role = user.role.name if user.role else None
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    flow = []

    def _hdr(text, level=0):
        s = styles["Heading1"] if level == 0 else styles["Heading3"]
        flow.append(Paragraph(text, s))

    def _p(text):
        flow.append(Paragraph(text, styles["BodyText"]))

    def _table(rows, header=True):
        if not rows: return
        t = Table(rows, hAlign="LEFT")
        ts = [
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID",     (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("VALIGN",   (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ]
        if header:
            ts += [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#185FA5")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        t.setStyle(TableStyle(ts))
        flow.append(t)
        flow.append(Spacer(1, 0.3*cm))

    _hdr("CATALOG ProElev")
    _p(f"Generat la {_dt.now().strftime('%Y-%m-%d %H:%M')}")
    _p(f"Pentru: <b>{user.name}</b> ({role})")
    flow.append(Spacer(1, 0.4*cm))

    def _student_block(data: dict):
        cls_name = data.get("class", {}).get("name") if data.get("class") else "—"
        _hdr(f"{data.get('name')} — Clasa {cls_name}", level=1)
        avg = data.get("average")
        _p(f"Media generală: <b>{avg if avg is not None else '—'}</b>")
        rows = [["Materie", "Tema", "Termen", "Trimisă", "Notă"]]
        for r in data.get("rows", []):
            rows.append([
                r.get("subject") or "", r.get("title") or "",
                r.get("dueDate") or "",
                "Da" if r.get("submitted") else "Nu",
                str(r.get("grade")) if r.get("grade") is not None else "—",
            ])
        if len(rows) > 1: _table(rows)
        if data.get("tests"):
            _hdr("Teste", level=1)
            trows = [["Materie", "Test", "Dată", "Notă"]]
            for t in data["tests"]:
                trows.append([
                    t.get("subject") or "", t.get("title") or "",
                    t.get("date") or "",
                    str(t.get("grade")) if t.get("grade") is not None else "—",
                ])
            _table(trows)
        if data.get("behavior"):
            b = data["behavior"]
            _p(f"<b>Media la purtare</b> ({b.get('period')}): {b.get('grade')}")
            if b.get("note"):
                _p(f"<i>{b['note']}</i>")
        flow.append(Spacer(1, 0.4*cm))

    if role == ROLE_STUDENT:
        _student_block(_student_view(db, user))
    elif role == ROLE_PARENT:
        for c in user.children:
            _student_block(_student_view(db, c))
            flow.append(PageBreak())
    elif role == ROLE_TEACHER:
        blocks = _teacher_view(db, user)
        for b in blocks:
            cls = b.get("class") or {}
            sub = b.get("subject") or {}
            _hdr(f"{cls.get('name', '—')} · {sub.get('name', '—')}", level=1)
            _p(f"{len(b.get('homeworks', []))} teme, {len(b.get('students', []))} elevi"
               f", media clasei: {b.get('classAverage') if b.get('classAverage') is not None else '—'}")
            rows = [["Elev", "Medie"]]
            for st in b.get("students", []):
                rows.append([st.get("name") or "",
                             str(st.get("average")) if st.get("average") is not None else "—"])
            _table(rows)
    elif role in (ROLE_ADMIN, ROLE_USER):
        blocks = _admin_view(db)
        for b in blocks:
            cls = b.get("class") or {}
            sub = b.get("subject") or {}
            _hdr(f"{cls.get('name', '—')} · {sub.get('name', '—')}", level=1)
            _p(f"{len(b.get('homeworks', []))} teme, {len(b.get('students', []))} elevi"
               f", media clasei: {b.get('classAverage') if b.get('classAverage') is not None else '—'}")
    else:
        _p("Rolul tău nu are catalog.")

    doc.build(flow)
    pdf_bytes = buf.getvalue()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="catalog.pdf"'},
    )
