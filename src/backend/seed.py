# seed helpers, fills the lookup tables, the role/permission rows and the demo users
# called from main.py and from the test fixtures, all idempotent
from sqlalchemy.orm import Session

from models import (
    Subject, SchoolClass, Role, Permission, User,
    SUBJECT_NAMES, CLASS_NAMES, PERMISSIONS, ROLE_PERMISSIONS, DEMO_USERS,
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

    db.commit()
