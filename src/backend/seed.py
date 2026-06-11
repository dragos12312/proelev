# seed helpers, fills the lookup tables, the role/permission rows and the demo users
# called from main.py and from the test fixtures, all idempotent
from sqlalchemy.orm import Session

from datetime import date, datetime, timedelta

from models import (
    Subject, SchoolClass, Role, Permission, User, Homework, Student,
    BehaviorGrade, SchoolAnnouncement, Test, TestGrade,
    teacher_assignment, parent_child,
    SUBJECT_NAMES, CLASS_NAMES, PERMISSIONS, ROLE_PERMISSIONS, DEMO_USERS,
    ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)
from auth import hash_password


def seed_lookups(db: Session) -> None:
    # subjects and classes for the homework form drop downs
    existing_subjects = {s.name for s in db.query(Subject).all()}
    for name in SUBJECT_NAMES:
        if name not in existing_subjects:
            db.add(Subject(name=name))

    existing_classes = {c.name for c in db.query(SchoolClass).all()}
    for name in CLASS_NAMES:
        if name not in existing_classes:
            db.add(SchoolClass(name=name))

    # one row per permission code, only created the first time
    existing_perms = {p.code: p for p in db.query(Permission).all()}
    for code in PERMISSIONS:
        if code not in existing_perms:
            p = Permission(code=code)
            db.add(p)
            existing_perms[code] = p
    db.flush()

    # roles and the role to permission links
    existing_roles = {r.name: r for r in db.query(Role).all()}
    for role_name, perm_codes in ROLE_PERMISSIONS.items():
        role = existing_roles.get(role_name)
        if not role:
            role = Role(name=role_name)
            db.add(role)
            db.flush()
            existing_roles[role_name] = role
        # set the permission list to match the canonical mapping each time
        # so dropping a perm from ROLE_PERMISSIONS removes it from the role too
        role.permissions = [existing_perms[c] for c in perm_codes]

    # demo users, only created the first time, passwords stored as bcrypt hashes
    # silver, every demo user also gets a security question so the 3rd login
    # factor works out of the box. answer is normalized lowercase.
    for u in DEMO_USERS:
        existing = db.query(User).filter_by(email=u["email"]).first()
        if not existing:
            db.add(User(
                email=u["email"],
                password_hash=hash_password(u["password"]),
                name=u["name"],
                role_id=existing_roles[u["role"]].id,
                security_question="Care este numele aplicației?",
                security_answer_hash=hash_password("proelev"),
            ))
    db.flush()

    # ── assignment 6: wire up demo teacher / student / parent relationships ──
    # all idempotent, only added if not already there
    _wire_demo_relations(db, existing_classes_by_name(db), existing_subjects_by_name(db))

    db.commit()

    # ── contest demo content: a few homeworks + submissions + grades so the
    # judges see a populated app without having to click anything. only seeds
    # when the homework table is empty so it never duplicates.
    _maybe_seed_demo_content(db)


def existing_classes_by_name(db: Session) -> dict[str, SchoolClass]:
    return {c.name: c for c in db.query(SchoolClass).all()}


def existing_subjects_by_name(db: Session) -> dict[str, Subject]:
    return {s.name: s for s in db.query(Subject).all()}


def _wire_demo_relations(db: Session, classes: dict, subjects: dict) -> None:
    """For the seeded prof@ / elev@ / parinte@ accounts, ensure:
      - prof teaches Matematică for class 4A
      - elev belongs to class 4A
      - parinte has elev as a child
    """
    prof    = db.query(User).filter_by(email="prof@proelev.ro").first()
    elev    = db.query(User).filter_by(email="elev@proelev.ro").first()
    parinte = db.query(User).filter_by(email="parinte@proelev.ro").first()

    class_4a = classes.get("4A")
    math     = subjects.get("Matematică")

    # student in 4A
    if elev and class_4a and elev.class_id != class_4a.id:
        elev.class_id = class_4a.id

    # teacher of Matematică 4A
    if prof and class_4a and math:
        already = db.execute(
            teacher_assignment.select().where(
                teacher_assignment.c.user_id    == prof.id,
                teacher_assignment.c.class_id   == class_4a.id,
                teacher_assignment.c.subject_id == math.id,
            )
        ).first()
        if not already:
            db.execute(teacher_assignment.insert().values(
                user_id=prof.id, class_id=class_4a.id, subject_id=math.id,
            ))

    # parent of elev
    if parinte and elev:
        already = db.execute(
            parent_child.select().where(
                parent_child.c.parent_user_id == parinte.id,
                parent_child.c.child_user_id  == elev.id,
            )
        ).first()
        if not already:
            db.execute(parent_child.insert().values(
                parent_user_id=parinte.id, child_user_id=elev.id,
            ))

    # extra demo students in 4A so the roster / catalog look populated
    student_role = db.query(Role).filter_by(name=ROLE_STUDENT).first()
    cls_4a = classes.get("4A")
    extras = [
        ("elev2@proelev.ro", "Elev1234", "Andrei Popescu"),
        ("elev3@proelev.ro", "Elev1234", "Maria Ionescu"),
        ("elev4@proelev.ro", "Elev1234", "Tudor Marin"),
    ]
    if student_role and cls_4a:
        for email, pw, name in extras:
            existing = db.query(User).filter_by(email=email).first()
            if not existing:
                db.add(User(
                    email=email,
                    password_hash=hash_password(pw),
                    name=name,
                    role_id=student_role.id,
                    security_question="Care este numele aplicației?",
                    security_answer_hash=hash_password("proelev"),
                    class_id=cls_4a.id,
                ))

    # give the parent a second child in 4A so the multi-child flow shows up
    db.flush()
    parinte = db.query(User).filter_by(email="parinte@proelev.ro").first()
    second_child = db.query(User).filter_by(email="elev2@proelev.ro").first()
    if parinte and second_child:
        already = db.execute(
            parent_child.select().where(
                parent_child.c.parent_user_id == parinte.id,
                parent_child.c.child_user_id  == second_child.id,
            )
        ).first()
        if not already:
            db.execute(parent_child.insert().values(
                parent_user_id=parinte.id, child_user_id=second_child.id,
            ))


def _maybe_seed_demo_content(db: Session) -> None:
    """If the homework table is empty (fresh deploy on Render), drop in a
    realistic demo: three homeworks posted by prof@ to Matematică 4A, one
    already graded (elev got 9), one submitted but pending grade, and one
    upcoming. Only runs when the table is empty so we don't keep duplicating
    on every cold start."""
    if db.query(Homework).count() > 0:
        return

    prof = db.query(User).filter_by(email="prof@proelev.ro").first()
    elev = db.query(User).filter_by(email="elev@proelev.ro").first()
    classes  = existing_classes_by_name(db)
    subjects = existing_subjects_by_name(db)
    cls_4a = classes.get("4A")
    math   = subjects.get("Matematică")
    if not (prof and elev and cls_4a and math):
        return

    today = date.today()
    seed_homeworks = [
        {
            "title": "Exerciții cu fracții ordinare",
            "description": "Rezolvă exercițiile 1-12 din culegere. Atenție la simplificare.",
            "due": today - timedelta(days=3),     # already past, graded
            "state": "graded",
            "grade": 9, "feedback": "Foarte bine! Atenție la pasul 2.",
            "submission": "Am rezolvat toate exercițiile, am atașat fotografia caietului.",
        },
        {
            "title": "Probleme de geometrie - triunghiuri",
            "description": "Capitol nou. Rezolvă problemele de la pag. 48-49 și fii pregătit pentru discuție.",
            "due": today + timedelta(days=2),     # current, submitted but ungraded
            "state": "submitted",
            "submission": "Trimis mai devreme, vă rog să verificați triunghiul B.",
        },
        {
            "title": "Test recapitulativ - unități de măsură",
            "description": "Pregătire pentru testul de săptămâna viitoare. Citește tot capitolul.",
            "due": today + timedelta(days=7),     # upcoming, not yet submitted
            "state": "open",
        },
    ]

    # a school-wide announcement so the dashboard banner has content
    admin = db.query(User).filter_by(email="admin@proelev.ro").first()
    if admin:
        db.add(SchoolAnnouncement(
            title="Bun venit pe ProElev!",
            body="Aceasta este versiunea de demonstrație. Conturile pre-create sunt în pagina de login.",
            kind="info", created_by_user_id=admin.id,
            created_at=datetime.utcnow(), pinned=1,
        ))

    # behavior grade for elev so the catalog has a value to render
    if prof and elev:
        db.add(BehaviorGrade(
            student_user_id=elev.id, period="Semestrul 2 2025-2026",
            grade=10, note="Foarte implicat la ore.",
            created_by_user_id=prof.id, created_at=datetime.utcnow(),
        ))

    # a backdated test + recent test so the improvement splash has data
    # to trigger on for the demo (delta of 4 → 5 → 9)
    if prof and elev:
        t_old = Test(
            class_id=cls_4a.id, subject_id=math.id,
            title="Test inițial - fracții", description="Test recapitulativ",
            scheduled_date=today - timedelta(days=30),
            created_by_user_id=prof.id, created_at=datetime.utcnow(),
        )
        db.add(t_old); db.flush()
        db.add(TestGrade(
            test_id=t_old.id, student_user_id=elev.id, grade=5,
            feedback="Mai exersează simplificarea.",
            graded_by_user_id=prof.id, graded_at=datetime.utcnow(),
        ))

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    for hw_data in seed_homeworks:
        hw = Homework(
            title=hw_data["title"],
            subject_id=math.id,
            class_id=cls_4a.id,
            due_date=hw_data["due"],
            description=hw_data["description"],
            created_by_user_id=prof.id,
        )
        db.add(hw)
        db.flush()

        # always create the student row for elev so the demo parent sees
        # something on the gradebook even before clicking
        s = Student(
            homework_id=hw.id,
            user_id=elev.id,
            name=elev.name,
            date_time=now_str,
        )
        if hw_data["state"] in ("submitted", "graded"):
            s.submitted_at    = datetime.utcnow() - timedelta(days=1)
            s.submission_text = hw_data["submission"]
        if hw_data["state"] == "graded":
            s.grade    = hw_data["grade"]
            s.feedback = hw_data["feedback"]
        db.add(s)

    db.commit()
