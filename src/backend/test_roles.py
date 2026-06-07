"""
Assignment 6 role-system tests.

Coverage:
- admin generates an invite code, can list it and revoke it
- public invite check works with valid / expired / used codes
- register with an invite produces a user of the right role plus the
  right relationships (teacher assignment, student class, parent children)
- /homeworks list is role-aware:
    teacher sees their class+subject homeworks
    student sees only their own class
    parent sees only their children's classes
- /homeworks create is restricted to admin or matching teacher
- statistics endpoint 403s for student and parent
- student submission flow + teacher grading happy path
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models import (
    User, InviteCode, Homework, Student, Role, SchoolClass, Subject,
    teacher_assignment, parent_child,
    ROLE_ADMIN, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)
from _test_login import login_three_factor
from auth import hash_password

client = TestClient(app)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _admin_token():
    return login_three_factor(client, "admin@proelev.ro", "Admin123")


def _bcrypt_seed_user(email, password, role_name, **kwargs):
    """Create a user directly via the ORM, bypassing the 3-factor flow."""
    db = SessionLocal()
    try:
        existing = db.query(User).filter_by(email=email).first()
        if existing:
            return existing
        role = db.query(Role).filter_by(name=role_name).first()
        u = User(
            email=email,
            password_hash=hash_password(password),
            name=kwargs.get("name", email.split("@")[0]),
            role_id=role.id,
            security_question="q?",
            security_answer_hash=hash_password("proelev"),
            class_id=kwargs.get("class_id"),
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean_invites():
    db = SessionLocal()
    try:
        db.query(InviteCode).delete()
        db.commit()
    finally:
        db.close()
    yield


# ─── invite code admin endpoints ─────────────────────────────────────────

class TestInviteAdmin:
    def test_admin_creates_invite_with_role_only(self):
        token = _admin_token()
        r = client.post("/admin/invites",
                        headers=_h(token),
                        json={"role": "parent"})
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "parent"
        assert len(body["code"]) == 16
        assert body["revoked"] is False

    def test_admin_creates_invite_with_preset_class_and_subject(self):
        token = _admin_token()
        db = SessionLocal()
        cls = db.query(SchoolClass).filter_by(name="4A").first()
        sub = db.query(Subject).filter_by(name="Matematică").first()
        db.close()
        r = client.post("/admin/invites",
                        headers=_h(token),
                        json={"role": "teacher", "class_id": cls.id, "subject_id": sub.id})
        assert r.status_code == 200
        body = r.json()
        assert body["class"]["name"]   == "4A"
        assert body["subject"]["name"] == "Matematică"

    def test_non_admin_cannot_create_invite(self):
        user_token = login_three_factor(client, "user@proelev.ro", "Parola123")
        r = client.post("/admin/invites",
                        headers=_h(user_token),
                        json={"role": "student"})
        assert r.status_code == 403

    def test_admin_revokes_unused_invite(self):
        token = _admin_token()
        body = client.post("/admin/invites",
                           headers=_h(token), json={"role": "student"}).json()
        rev = client.post(f"/admin/invites/{body['id']}/revoke", headers=_h(token))
        assert rev.status_code == 200
        # check ends up in /admin/invites with revoked=true if include_expired
        listed = client.get("/admin/invites?include_expired=true&include_used=true",
                            headers=_h(token)).json()
        match = [i for i in listed if i["id"] == body["id"]]
        assert match and match[0]["revoked"] is True


# ─── public invite check ─────────────────────────────────────────────────

class TestPublicInviteCheck:
    def test_check_valid_invite_returns_role(self):
        token = _admin_token()
        body = client.post("/admin/invites", headers=_h(token),
                           json={"role": "student"}).json()
        r = client.get(f"/auth/invite/check?code={body['code']}")
        assert r.status_code == 200
        assert r.json()["role"] == "student"

    def test_check_unknown_code_404s(self):
        r = client.get("/auth/invite/check?code=NOPENOPENOPENOPE")
        assert r.status_code == 404

    def test_check_revoked_code_400s(self):
        token = _admin_token()
        body = client.post("/admin/invites", headers=_h(token),
                           json={"role": "student"}).json()
        client.post(f"/admin/invites/{body['id']}/revoke", headers=_h(token))
        r = client.get(f"/auth/invite/check?code={body['code']}")
        assert r.status_code == 400


# ─── register with invite code ───────────────────────────────────────────

class TestRegisterWithInvite:
    def test_register_teacher_with_preset_assignment(self):
        token = _admin_token()
        db = SessionLocal()
        cls = db.query(SchoolClass).filter_by(name="4A").first()
        sub = db.query(Subject).filter_by(name="Matematică").first()
        db.close()
        inv = client.post("/admin/invites", headers=_h(token), json={
            "role": "teacher", "class_id": cls.id, "subject_id": sub.id,
        }).json()
        r = client.post("/auth/register", json={
            "name": "Prof Test", "email": "prof_test@proelev.ro", "password": "Profabc1",
            "security_question": "Care e?", "security_answer": "alpha",
            "invite_code": inv["code"],
        })
        assert r.status_code == 201
        body = r.json()
        assert body["user"]["role"] == "teacher"
        # teacher_assignment row was inserted
        db = SessionLocal()
        rows = db.execute(
            teacher_assignment.select().where(
                teacher_assignment.c.user_id == body["user"]["id"]
            )
        ).all()
        assert len(rows) == 1

    def test_register_student_with_preset_class(self):
        token = _admin_token()
        db = SessionLocal()
        cls = db.query(SchoolClass).filter_by(name="4A").first()
        db.close()
        inv = client.post("/admin/invites", headers=_h(token), json={
            "role": "student", "class_id": cls.id,
        }).json()
        r = client.post("/auth/register", json={
            "name": "Elev Test", "email": "elev_test@proelev.ro", "password": "Elevabc1",
            "security_question": "Care e?", "security_answer": "alpha",
            "invite_code": inv["code"],
        })
        assert r.status_code == 201
        body = r.json()
        assert body["user"]["role"] == "student"
        assert body["user"]["class"]["name"] == "4A"

    def test_register_parent_links_to_existing_child(self):
        # the seeded elev@proelev.ro is a real student account
        token = _admin_token()
        inv = client.post("/admin/invites", headers=_h(token),
                          json={"role": "parent"}).json()
        r = client.post("/auth/register", json={
            "name": "Parinte Test", "email": "parinte_test@proelev.ro", "password": "Parabc1",
            "security_question": "Care e?", "security_answer": "alpha",
            "invite_code": inv["code"],
            "children_emails": ["elev@proelev.ro"],
        })
        assert r.status_code == 201
        body = r.json()
        assert body["user"]["role"] == "parent"
        assert "children" in body["user"]
        assert any(c["email"] == "elev@proelev.ro" for c in body["user"]["children"])

    def test_register_consumes_the_invite(self):
        token = _admin_token()
        inv = client.post("/admin/invites", headers=_h(token),
                          json={"role": "parent"}).json()
        client.post("/auth/register", json={
            "name": "Parinte X", "email": "px@proelev.ro", "password": "Parabc1",
            "security_question": "Question?", "security_answer": "alpha",
            "invite_code": inv["code"],
            "children_emails": ["elev@proelev.ro"],
        })
        # second use must fail
        r = client.post("/auth/register", json={
            "name": "Parinte Y", "email": "py@proelev.ro", "password": "Parabc1",
            "security_question": "Question?", "security_answer": "alpha",
            "invite_code": inv["code"],
            "children_emails": ["elev@proelev.ro"],
        })
        assert r.status_code == 400

    def test_register_without_invite_is_legacy_user(self):
        r = client.post("/auth/register", json={
            "name": "Plain", "email": "plain@proelev.ro", "password": "Plain12",
            "security_question": "Care e?", "security_answer": "alpha",
        })
        assert r.status_code == 201
        assert r.json()["user"]["role"] == "user"


# ─── role-aware homework list ────────────────────────────────────────────

class TestRoleAwareList:
    def test_teacher_sees_only_assigned_homeworks(self):
        admin_token = _admin_token()
        teacher_token = login_three_factor(client, "prof@proelev.ro", "Profesor1")

        # admin posts one homework for Matematică 4A (teacher's assignment)
        r1 = client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Test Mate", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        assert r1.status_code == 201
        # admin posts another for Istorie 1A (NOT teacher's assignment)
        r2 = client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Test Istorie", "subject": "Istorie", "assignedClass": "1A",
            "dueDate": "2026-12-01", "description": "x",
        })
        assert r2.status_code == 201

        # teacher should see only the matematica/4A one
        listed = client.get("/homeworks?pageSize=100", headers=_h(teacher_token)).json()
        titles = [h["title"] for h in listed["items"]]
        assert "Test Mate" in titles
        assert "Test Istorie" not in titles

    def test_student_sees_only_own_class(self):
        admin_token = _admin_token()
        # admin posts homework for 4A (elev@ is in 4A)
        client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Pentru 4A", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        # admin posts homework for 1B (elev@ is NOT in 1B)
        client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Pentru 1B", "subject": "Istorie", "assignedClass": "1B",
            "dueDate": "2026-12-01", "description": "x",
        })

        elev_token = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        listed = client.get("/homeworks?pageSize=100", headers=_h(elev_token)).json()
        titles = [h["title"] for h in listed["items"]]
        assert "Pentru 4A" in titles
        assert "Pentru 1B" not in titles

    def test_parent_sees_only_children_classes(self):
        admin_token = _admin_token()
        client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Vizibil parinte", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Invizibil parinte", "subject": "Istorie", "assignedClass": "2B",
            "dueDate": "2026-12-01", "description": "x",
        })
        par_token = login_three_factor(client, "parinte@proelev.ro", "Parinte1")
        listed = client.get("/homeworks?pageSize=100", headers=_h(par_token)).json()
        titles = [h["title"] for h in listed["items"]]
        assert "Vizibil parinte"   in titles
        assert "Invizibil parinte" not in titles


# ─── role-aware homework write ──────────────────────────────────────────

class TestRoleAwareWrite:
    def test_teacher_can_post_for_own_class_subject(self):
        token = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        r = client.post("/homeworks", headers=_h(token), json={
            "title": "Tema noua", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        assert r.status_code == 201

    def test_teacher_cannot_post_for_other_subject(self):
        token = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        r = client.post("/homeworks", headers=_h(token), json={
            "title": "Nu pot", "subject": "Istorie", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        assert r.status_code == 403

    def test_student_cannot_post_homework(self):
        token = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        r = client.post("/homeworks", headers=_h(token), json={
            "title": "Test", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        assert r.status_code == 403


# ─── stats role enforcement ─────────────────────────────────────────────

class TestStatsRoles:
    def test_stats_403_for_student(self):
        admin_token = _admin_token()
        hw = client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Stat", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        elev_token = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        r = client.get(f"/homeworks/{hw['id']}/statistics", headers=_h(elev_token))
        assert r.status_code == 403

    def test_stats_403_for_parent(self):
        admin_token = _admin_token()
        hw = client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Stat2", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        par_token = login_three_factor(client, "parinte@proelev.ro", "Parinte1")
        r = client.get(f"/homeworks/{hw['id']}/statistics", headers=_h(par_token))
        assert r.status_code == 403

    def test_stats_200_for_admin(self):
        admin_token = _admin_token()
        hw = client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Stat3", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        r = client.get(f"/homeworks/{hw['id']}/statistics", headers=_h(admin_token))
        assert r.status_code == 200


# ─── student submission + teacher grading ───────────────────────────────

class TestSubmissionFlow:
    def test_student_submits_text_only(self):
        admin_token = _admin_token()
        hw = client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Sub1", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        elev_token = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        r = client.post(
            f"/homeworks/{hw['id']}/submit",
            headers=_h(elev_token),
            data={"text": "raspunsul meu"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["submissionText"] == "raspunsul meu"
        assert body["submittedAt"] is not None

    def test_teacher_grades_submission(self):
        # teacher creates the homework themselves so they own it
        prof_token = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        hw = client.post("/homeworks", headers=_h(prof_token), json={
            "title": "Sub2", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        elev_token = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        sub = client.post(f"/homeworks/{hw['id']}/submit", headers=_h(elev_token),
                          data={"text": "salut"}).json()
        r = client.put(
            f"/homeworks/{hw['id']}/students/{sub['id']}/grade",
            headers=_h(prof_token),
            json={"grade": 9, "feedback": "Bravo!"},
        )
        assert r.status_code == 200
        assert r.json()["grade"] == 9
        assert r.json()["feedback"] == "Bravo!"

    def test_student_cannot_grade(self):
        admin_token = _admin_token()
        hw = client.post("/homeworks", headers=_h(admin_token), json={
            "title": "Sub3", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        elev_token = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        sub = client.post(f"/homeworks/{hw['id']}/submit", headers=_h(elev_token),
                          data={"text": "x"}).json()
        r = client.put(
            f"/homeworks/{hw['id']}/students/{sub['id']}/grade",
            headers=_h(elev_token), json={"grade": 10},
        )
        assert r.status_code == 403

    def test_parent_sees_child_grade_and_feedback(self):
        # teacher creates and grades; parent should see their child's grade
        # and feedback on the student list for that homework
        prof_token = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        hw = client.post("/homeworks", headers=_h(prof_token), json={
            "title": "Sub4", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        elev_token = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        sub = client.post(f"/homeworks/{hw['id']}/submit", headers=_h(elev_token),
                          data={"text": "salut"}).json()
        client.put(
            f"/homeworks/{hw['id']}/students/{sub['id']}/grade",
            headers=_h(prof_token),
            json={"grade": 8, "feedback": "Foarte bine!"},
        )
        par_token = login_three_factor(client, "parinte@proelev.ro", "Parinte1")
        listed = client.get(
            f"/homeworks/{hw['id']}/students?pageSize=100",
            headers=_h(par_token),
        ).json()
        # exactly the parent's child appears, with grade + feedback visible
        assert len(listed["items"]) == 1
        row = listed["items"][0]
        assert row["grade"] == 8
        assert row["feedback"] == "Foarte bine!"
        assert row["submittedAt"] is not None


# ─── lookups ────────────────────────────────────────────────────────────

class TestLookups:
    def test_classes_returns_all(self):
        r = client.get("/lookups/classes")
        assert r.status_code == 200
        names = {c["name"] for c in r.json()}
        assert {"1A", "4A", "4B"}.issubset(names)

    def test_subjects_returns_matematica(self):
        r = client.get("/lookups/subjects")
        assert r.status_code == 200
        assert any(s["name"] == "Matematică" for s in r.json())
