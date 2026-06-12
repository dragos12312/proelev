"""
ORAR (timetable) router. Returns a weekly schedule for a given class.

The grid is hard-coded for demo purposes; in a real deployment this would
come from a dedicated table. It's tied to the subjects we seed so the
frontend can render "Matematică, prof. Ionescu" cells reliably.
"""
import random
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from database import get_db
from models import (
    User, SchoolClass, Subject, TimetableSlot, teacher_assignment,
    ROLE_ADMIN, ROLE_USER, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)
from auth import get_current_user


router = APIRouter()


# canonical weekly periods. each class gets the same five-day block 08:00-13:00
PERIODS = [
    ("1", "08:00", "08:50"),
    ("2", "09:00", "09:50"),
    ("3", "10:00", "10:50"),
    ("4", "11:00", "11:50"),
    ("5", "12:00", "12:50"),
]
DAYS = ["Luni", "Marți", "Miercuri", "Joi", "Vineri"]


# hard-coded subject grid per class. five days × five periods. blank string
# means "free period". the names line up with the seeded Subject rows.
_TIMETABLE = {
    "1A": [
        ["Matematică",        "Limba Română",   "Științele naturii", "Limba Engleză",  "Educație fizică"],
        ["Limba Română",      "Matematică",     "Limba Engleză",     "Istorie",        "Geografie"],
        ["Științele naturii", "Educație fizică","Matematică",        "Limba Română",   "Limba Engleză"],
        ["Limba Engleză",     "Istorie",        "Limba Română",      "Matematică",     "Științele naturii"],
        ["Geografie",         "Limba Română",   "Matematică",        "Educație fizică","Istorie"],
    ],
    "1B": [
        ["Limba Română",      "Matematică",     "Istorie",           "Limba Engleză",  "Geografie"],
        ["Matematică",        "Limba Română",   "Științele naturii", "Educație fizică","Limba Engleză"],
        ["Limba Engleză",     "Geografie",      "Matematică",        "Limba Română",   "Istorie"],
        ["Științele naturii", "Limba Engleză",  "Limba Română",      "Matematică",     "Educație fizică"],
        ["Educație fizică",   "Istorie",        "Limba Română",      "Geografie",      "Matematică"],
    ],
    "2A": [
        ["Matematică",        "Științele naturii","Limba Română",    "Istorie",        "Limba Engleză"],
        ["Limba Română",      "Limba Engleză",  "Matematică",        "Geografie",      "Educație fizică"],
        ["Geografie",         "Matematică",     "Educație fizică",   "Limba Română",   "Științele naturii"],
        ["Istorie",           "Limba Română",   "Limba Engleză",     "Matematică",     "Geografie"],
        ["Limba Engleză",     "Educație fizică","Științele naturii", "Limba Română",   "Matematică"],
    ],
    "2B": [
        ["Limba Română",      "Matematică",     "Limba Engleză",     "Educație fizică","Istorie"],
        ["Matematică",        "Geografie",      "Limba Română",      "Științele naturii","Limba Engleză"],
        ["Limba Engleză",     "Limba Română",   "Istorie",           "Matematică",     "Geografie"],
        ["Științele naturii", "Educație fizică","Matematică",        "Limba Română",   "Limba Engleză"],
        ["Istorie",           "Limba Română",   "Geografie",         "Educație fizică","Matematică"],
    ],
    "3A": [
        ["Matematică",        "Limba Română",   "Istorie",           "Limba Engleză",  "Educație fizică"],
        ["Limba Română",      "Matematică",     "Geografie",         "Științele naturii","Limba Engleză"],
        ["Geografie",         "Istorie",        "Matematică",        "Limba Română",   "Limba Engleză"],
        ["Limba Engleză",     "Educație fizică","Limba Română",      "Matematică",     "Științele naturii"],
        ["Științele naturii", "Limba Română",   "Educație fizică",   "Istorie",        "Matematică"],
    ],
    "3B": [
        ["Limba Engleză",     "Matematică",     "Limba Română",      "Educație fizică","Geografie"],
        ["Matematică",        "Limba Română",   "Științele naturii", "Istorie",        "Limba Engleză"],
        ["Limba Română",      "Geografie",      "Matematică",        "Limba Engleză",  "Educație fizică"],
        ["Istorie",           "Limba Engleză",  "Limba Română",      "Matematică",     "Geografie"],
        ["Educație fizică",   "Științele naturii","Istorie",         "Limba Română",   "Matematică"],
    ],
    "4A": [
        ["Matematică",        "Limba Română",   "Limba Engleză",     "Geografie",      "Educație fizică"],
        ["Limba Română",      "Matematică",     "Istorie",           "Științele naturii","Limba Engleză"],
        ["Limba Engleză",     "Geografie",      "Matematică",        "Limba Română",   "Istorie"],
        ["Științele naturii", "Limba Română",   "Educație fizică",   "Matematică",     "Limba Engleză"],
        ["Educație fizică",   "Istorie",        "Limba Română",      "Geografie",      "Matematică"],
    ],
    "4B": [
        ["Limba Română",      "Matematică",     "Educație fizică",   "Limba Engleză",  "Istorie"],
        ["Matematică",        "Limba Engleză",  "Limba Română",      "Geografie",      "Științele naturii"],
        ["Geografie",         "Matematică",     "Limba Română",      "Educație fizică","Istorie"],
        ["Limba Engleză",     "Limba Română",   "Științele naturii", "Matematică",     "Educație fizică"],
        ["Istorie",           "Limba Română",   "Matematică",        "Limba Engleză",  "Geografie"],
    ],
}


def _teachers_for_class_subject(db: Session) -> dict[tuple[int, int], list[str]]:
    """Map (class_id, subject_id) → list of teacher display names. We use
    the actual teacher_assignment rows so the orar matches who's teaching."""
    rows = db.execute(
        select(teacher_assignment.c.class_id,
               teacher_assignment.c.subject_id,
               teacher_assignment.c.user_id)
    ).all()
    out: dict[tuple[int, int], list[str]] = {}
    for cls_id, sub_id, uid in rows:
        u = db.get(User, uid)
        if not u:
            continue
        out.setdefault((cls_id, sub_id), []).append(u.name)
    return out


@router.get("")
def get_timetable(
    class_name: str | None = Query(default=None, alias="class"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resolve which class's timetable to show.

    - student/parent (no class param): student's class / first child's class
    - teacher (no class param): one of their assigned classes
    - admin (no class param): defaults to 4A
    - class_name param overrides for admin/teacher only; students/parents
      can't peek at other classes' timetables
    """
    role = user.role.name if user.role else None

    # figure out the target class
    target_class_name: str | None = None
    if role == ROLE_STUDENT:
        target_class_name = user.school_class.name if user.school_class else None
    elif role == ROLE_PARENT:
        kids = [c for c in user.children if c.school_class]
        if class_name:
            # parents can pick which child's class to see, but only their own kids
            target_class_name = next(
                (c.school_class.name for c in kids if c.school_class.name == class_name),
                None,
            )
        else:
            target_class_name = kids[0].school_class.name if kids else None
    elif role in (ROLE_TEACHER, ROLE_ADMIN, ROLE_USER):
        if class_name:
            target_class_name = class_name
        elif role == ROLE_TEACHER:
            # first class the teacher's assigned to
            row = db.execute(
                select(teacher_assignment.c.class_id).where(
                    teacher_assignment.c.user_id == user.id
                ).limit(1)
            ).first()
            if row:
                cls = db.get(SchoolClass, row[0])
                target_class_name = cls.name if cls else None
        else:
            target_class_name = "4A"

    cls = db.query(SchoolClass).filter_by(name=target_class_name).first() if target_class_name else None
    if not cls:
        raise HTTPException(status_code=404, detail="Orarul nu este disponibil pentru această clasă")

    # If admin has generated a real timetable, prefer those rows. Otherwise
    # fall back to the hard-coded grid so the demo still works on a fresh
    # install before anyone clicks "Generează orar".
    db_rows = db.query(TimetableSlot).filter_by(class_id=cls.id).all()
    days_out = []
    if db_rows:
        by_dp = {(r.day, r.period): r for r in db_rows}
        for di, day in enumerate(DAYS):
            slots = []
            for pi, (pnum, start, end) in enumerate(PERIODS):
                period_num = int(pnum)
                cell = {
                    "period": pnum, "start": start, "end": end,
                    "subject": None, "teachers": [],
                }
                row = by_dp.get((di, period_num))
                if row:
                    cell["subject"]  = row.subject.name if row.subject else None
                    cell["teachers"] = [row.teacher.name] if row.teacher else []
                slots.append(cell)
            days_out.append({"day": day, "slots": slots})
    else:
        if target_class_name not in _TIMETABLE:
            raise HTTPException(status_code=404, detail="Orarul nu este disponibil pentru această clasă")
        subjects_lookup = {s.name: s for s in db.query(Subject).all()}
        teachers_lookup = _teachers_for_class_subject(db)
        grid = _TIMETABLE[target_class_name]
        for di, day in enumerate(DAYS):
            slots = []
            for pi, (pnum, start, end) in enumerate(PERIODS):
                subj_name = grid[pi][di] if pi < len(grid) and di < len(grid[0]) else ""
                cell = {
                    "period": pnum, "start": start, "end": end,
                    "subject": subj_name or None,
                    "teachers": [],
                }
                if subj_name and subj_name in subjects_lookup:
                    sub = subjects_lookup[subj_name]
                    cell["teachers"] = teachers_lookup.get((cls.id, sub.id), [])
                slots.append(cell)
            days_out.append({"day": day, "slots": slots})

    return {
        "class":   {"id": cls.id, "name": cls.name},
        "periods": [{"period": p, "start": s, "end": e} for (p, s, e) in PERIODS],
        "days":    days_out,
        "available_classes": sorted([c.name for c in db.query(SchoolClass).all()]),
        "source":  "generated" if db_rows else "default",
    }


# ── auto-generator ──────────────────────────────────────────────────

# Weekly hours per subject. Tunable for the demo. Total must fit in
# 5 days × 5 periods = 25 slots; we sum to 22 so some periods stay free.
DEFAULT_HOURS = {
    "Matematică":        5,
    "Limba Română":      5,
    "Științele naturii": 3,
    "Limba Engleză":     3,
    "Istorie":           2,
    "Geografie":         2,
    "Educație fizică":   2,
}


def _generate_timetable(db: Session) -> dict:
    """Greedy scheduler:
      for each class, fill 5 days × 5 periods with subjects chosen by their
      remaining weekly-hours budget. Constraints:
        * a teacher can't be in two classes at the same (day, period)
        * a subject can appear at most once per day per class (mostly avoids
          double-blocks — exception is when there's no other choice)
    The result is deterministic-ish per run thanks to a fixed shuffle seed,
    so admins get repeatable demos.
    """
    rng = random.Random(42)

    db.query(TimetableSlot).delete()
    db.commit()

    classes  = sorted(db.query(SchoolClass).all(), key=lambda c: c.name)
    subjects = sorted(db.query(Subject).all(),     key=lambda s: s.name)

    # one teacher per (class, subject) if seeded; otherwise None
    teacher_for: dict[tuple[int, int], int | None] = {}
    rows = db.execute(
        select(teacher_assignment.c.class_id, teacher_assignment.c.subject_id,
               teacher_assignment.c.user_id)
    ).all()
    for cid, sid, uid in rows:
        teacher_for.setdefault((cid, sid), uid)

    # teacher_id, day, period -> taken
    teacher_busy: set[tuple[int, int, int]] = set()
    n_placed = 0

    for cls in classes:
        # remaining hours this class needs per subject
        remaining = {s.id: DEFAULT_HOURS.get(s.name, 2) for s in subjects}
        # subjects already placed today (per day)
        per_day: dict[int, set[int]] = {d: set() for d in range(5)}

        for day in range(5):
            for period in range(1, 6):
                # try to place a subject:
                #   strict pass — respect "max 1/day"
                placed = _try_place(
                    db, cls, day, period, subjects, remaining, per_day,
                    teacher_for, teacher_busy, rng,
                    allow_same_day=False,
                )
                if not placed:
                    # relaxed pass — if all "fresh" subjects are exhausted
                    # for this day, let one repeat in this slot
                    placed = _try_place(
                        db, cls, day, period, subjects, remaining, per_day,
                        teacher_for, teacher_busy, rng,
                        allow_same_day=True,
                    )
                if placed:
                    n_placed += 1

    db.commit()
    return {"slotsPlaced": n_placed, "classes": len(classes)}


def _try_place(
    db: Session,
    cls: SchoolClass,
    day: int, period: int,
    subjects: list[Subject],
    remaining: dict[int, int],
    per_day: dict[int, set[int]],
    teacher_for: dict[tuple[int, int], int | None],
    teacher_busy: set[tuple[int, int, int]],
    rng: random.Random,
    *, allow_same_day: bool,
) -> bool:
    """Pick the best-fit subject for this slot. Prefers subjects with more
    remaining hours so they spread out."""
    candidates = []
    for sub in subjects:
        if remaining[sub.id] <= 0:
            continue
        if not allow_same_day and sub.id in per_day[day]:
            continue
        teacher_id = teacher_for.get((cls.id, sub.id))
        if teacher_id is not None and (teacher_id, day, period) in teacher_busy:
            continue
        candidates.append((sub, teacher_id))
    if not candidates:
        return False
    # primary key: most-remaining-hours; tie-broken by random shuffle so it
    # doesn't always pick the alphabetically-first subject
    rng.shuffle(candidates)
    candidates.sort(key=lambda x: -remaining[x[0].id])
    sub, teacher_id = candidates[0]
    db.add(TimetableSlot(
        class_id=cls.id, subject_id=sub.id,
        teacher_user_id=teacher_id,
        day=day, period=period,
    ))
    remaining[sub.id] -= 1
    per_day[day].add(sub.id)
    if teacher_id is not None:
        teacher_busy.add((teacher_id, day, period))
    return True


@router.post("/generate")
def generate_timetable(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admin-only. Rebuilds every class's timetable from scratch."""
    if not user.role or user.role.name != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Doar adminul")
    summary = _generate_timetable(db)
    return {"ok": True, **summary}


@router.delete("/clear")
def clear_timetable(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admin-only. Clears all generated slots so the fallback grid takes over."""
    if not user.role or user.role.name != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Doar adminul")
    n = db.query(TimetableSlot).delete()
    db.commit()
    return {"ok": True, "deleted": n}
