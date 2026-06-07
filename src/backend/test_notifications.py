"""
Notification system tests.

We exercise the three creation hooks (homework, submission, grade), confirm
the listing endpoint returns newest-first, mark-read flips the flag, and
unread_count reflects what's actually on the row.
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models import Notification, InviteCode
from _test_login import login_three_factor

client = TestClient(app)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _clean_notifications_and_invites():
    db = SessionLocal()
    try:
        db.query(Notification).delete()
        db.query(InviteCode).delete()
        db.commit()
    finally:
        db.close()
    yield


class TestNotificationsHomework:
    def test_homework_create_notifies_student_and_parent(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        client.post("/homeworks", headers=_h(prof), json={
            "title": "Notif test", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })

        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        notifs = client.get("/notifications", headers=_h(elev)).json()
        kinds = [n["kind"] for n in notifs]
        assert "homework_new" in kinds
        assert any("Notif test" in n["body"] for n in notifs)

        par = login_three_factor(client, "parinte@proelev.ro", "Parinte1")
        par_notifs = client.get("/notifications", headers=_h(par)).json()
        assert any(n["kind"] == "homework_new" for n in par_notifs)

    def test_unread_count_reflects_actual_state(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        client.post("/homeworks", headers=_h(prof), json={
            "title": "Count1", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        before = client.get("/notifications/unread_count", headers=_h(elev)).json()
        assert before["count"] >= 1


class TestNotificationsSubmission:
    def test_submission_notifies_teacher(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        hw = client.post("/homeworks", headers=_h(prof), json={
            "title": "Sub-N", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        # snapshot teacher's existing unread, then submit
        before = client.get("/notifications/unread_count", headers=_h(prof)).json()["count"]

        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        client.post(f"/homeworks/{hw['id']}/submit", headers=_h(elev), data={"text": "salut"})

        after_list = client.get("/notifications?unread_only=true", headers=_h(prof)).json()
        assert any(n["kind"] == "submission_new" for n in after_list)
        after = client.get("/notifications/unread_count", headers=_h(prof)).json()["count"]
        assert after == before + 1


class TestNotificationsGrade:
    def test_grade_notifies_student_and_parent(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        hw = client.post("/homeworks", headers=_h(prof), json={
            "title": "Gr-N", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        }).json()
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        sub = client.post(f"/homeworks/{hw['id']}/submit", headers=_h(elev),
                          data={"text": "x"}).json()

        # mark all read so the new grade-given notification is the freshest
        client.post("/notifications/read_all", headers=_h(elev))
        par = login_three_factor(client, "parinte@proelev.ro", "Parinte1")
        client.post("/notifications/read_all", headers=_h(par))

        client.put(
            f"/homeworks/{hw['id']}/students/{sub['id']}/grade",
            headers=_h(prof), json={"grade": 9, "feedback": "Bravo!"},
        )

        elev_notifs = client.get("/notifications?unread_only=true", headers=_h(elev)).json()
        assert any(n["kind"] == "grade_given" and "9" in n["title"] for n in elev_notifs)

        par_notifs = client.get("/notifications?unread_only=true", headers=_h(par)).json()
        assert any(n["kind"] == "grade_given" for n in par_notifs)


class TestNotificationsApi:
    def test_list_is_newest_first(self):
        # generate two homeworks back to back, student sees the second one first
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        client.post("/homeworks", headers=_h(prof), json={
            "title": "Older",  "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        client.post("/homeworks", headers=_h(prof), json={
            "title": "Newer",  "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        rows = client.get("/notifications", headers=_h(elev)).json()
        titles = [r["body"] for r in rows if r["kind"] == "homework_new"]
        # most recent first => Newer comes before Older
        assert titles.index("Newer (4A), termen 2026-12-01") < titles.index("Older (4A), termen 2026-12-01")

    def test_mark_read_flips_flag(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        client.post("/homeworks", headers=_h(prof), json={
            "title": "Mark-read", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        rows = client.get("/notifications", headers=_h(elev)).json()
        target = next(r for r in rows if r["kind"] == "homework_new")
        assert target["read"] is False

        r = client.post(f"/notifications/{target['id']}/read", headers=_h(elev))
        assert r.status_code == 200
        rows2 = client.get("/notifications", headers=_h(elev)).json()
        target2 = next(r for r in rows2 if r["id"] == target["id"])
        assert target2["read"] is True

    def test_read_all_clears_unread(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        client.post("/homeworks", headers=_h(prof), json={
            "title": "Clear", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        assert client.get("/notifications/unread_count", headers=_h(elev)).json()["count"] >= 1
        client.post("/notifications/read_all", headers=_h(elev))
        assert client.get("/notifications/unread_count", headers=_h(elev)).json()["count"] == 0

    def test_other_users_cannot_mark_my_notification(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        client.post("/homeworks", headers=_h(prof), json={
            "title": "Cross", "subject": "Matematică", "assignedClass": "4A",
            "dueDate": "2026-12-01", "description": "x",
        })
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        nid = client.get("/notifications", headers=_h(elev)).json()[0]["id"]
        # admin shouldn't be able to mark a notification that belongs to elev
        admin = login_three_factor(client, "admin@proelev.ro", "Admin123")
        r = client.post(f"/notifications/{nid}/read", headers=_h(admin))
        assert r.status_code == 404
