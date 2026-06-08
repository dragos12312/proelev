"""Smoke tests for the CATALOG, ORAR, and homework-attachment endpoints."""
import io
import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models import Homework, Notification, InviteCode
from _test_login import login_three_factor

client = TestClient(app)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _clean():
    db = SessionLocal()
    try:
        db.query(Notification).delete()
        db.query(InviteCode).delete()
        # leave homeworks so the per-role tests have data to aggregate
        db.commit()
    finally:
        db.close()
    yield


class TestGradebook:
    def test_student_sees_only_own_grades(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        hw = client.post("/homeworks", headers=_h(prof), json={
            "title": "Cat1", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        sub = client.post(f"/homeworks/{hw['id']}/submit", headers=_h(elev),
                          data={"text": "merge"}).json()
        client.put(f"/homeworks/{hw['id']}/students/{sub['id']}/grade",
                   headers=_h(prof), json={"grade": 9, "feedback": "Bun!"})

        r = client.get("/gradebook", headers=_h(elev))
        assert r.status_code == 200
        body = r.json()
        assert body["viewKind"] == "student"
        rows = body["data"]["rows"]
        assert any(row["grade"] == 9 and row["title"] == "Cat1" for row in rows)

    def test_parent_sees_children_grades(self):
        par = login_three_factor(client, "parinte@proelev.ro", "Parinte1")
        r = client.get("/gradebook", headers=_h(par))
        assert r.status_code == 200
        body = r.json()
        assert body["viewKind"] == "parent"
        assert isinstance(body["children"], list)

    def test_teacher_sees_assigned_class_subject(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        r = client.get("/gradebook", headers=_h(prof))
        assert r.status_code == 200
        body = r.json()
        assert body["viewKind"] == "teacher"
        # teacher is assigned to Matematică 4A in the seed
        assert any(b["subject"]["name"] == "Matematică" and b["class"]["name"] == "4A"
                   for b in body["blocks"])


class TestTimetable:
    def test_student_gets_own_class(self):
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        r = client.get("/timetable", headers=_h(elev))
        assert r.status_code == 200
        body = r.json()
        assert body["class"]["name"] == "4A"
        assert len(body["days"]) == 5
        assert len(body["periods"]) == 5

    def test_admin_can_switch_class(self):
        admin = login_three_factor(client, "admin@proelev.ro", "Admin123")
        r = client.get("/timetable?class=2B", headers=_h(admin))
        assert r.status_code == 200
        assert r.json()["class"]["name"] == "2B"


class TestHomeworkAttachment:
    def test_teacher_uploads_and_student_downloads(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        hw = client.post("/homeworks", headers=_h(prof), json={
            "title": "Attach1", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()

        # teacher uploads
        r = client.post(
            f"/homeworks/{hw['id']}/attachment",
            headers=_h(prof),
            files={"file": ("tema.txt", b"contents here", "text/plain")},
        )
        assert r.status_code == 200, r.text

        # student in that class can download it
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        r = client.get(f"/homeworks/{hw['id']}/attachment", headers=_h(elev))
        assert r.status_code == 200
        assert r.content == b"contents here"

    def test_non_owner_teacher_cannot_upload(self):
        # admin creates the homework so prof@proelev.ro is NOT the owner
        admin = login_three_factor(client, "admin@proelev.ro", "Admin123")
        hw = client.post("/homeworks", headers=_h(admin), json={
            "title": "Attach2", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        r = client.post(
            f"/homeworks/{hw['id']}/attachment",
            headers=_h(prof),
            files={"file": ("x.txt", b"x", "text/plain")},
        )
        assert r.status_code == 403
