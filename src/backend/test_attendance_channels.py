"""Smoke tests for the attendance + subject channel endpoints."""
import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models import Attendance, SubjectChannelPost, Notification, InviteCode, Homework, Student
from _test_login import login_three_factor

client = TestClient(app)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _clean():
    db = SessionLocal()
    try:
        db.query(Attendance).delete()
        db.query(SubjectChannelPost).delete()
        db.query(Notification).delete()
        db.query(InviteCode).delete()
        db.commit()
    finally:
        db.close()
    yield


class TestAttendance:
    def test_teacher_lists_their_classes(self):
        tok = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        r = client.get("/attendance/teacher/classes", headers=_h(tok))
        assert r.status_code == 200
        names = [c["name"] for c in r.json()]
        assert "4A" in names

    def test_teacher_marks_and_student_reads(self):
        tok = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        classes = client.get("/attendance/teacher/classes", headers=_h(tok)).json()
        cls_id = classes[0]["id"]
        roster = client.get(f"/attendance/roster/{cls_id}", headers=_h(tok)).json()
        student_id = roster[0]["userId"]

        r = client.post("/attendance/bulk", headers=_h(tok), json={
            "classId": cls_id, "date": "2026-06-08",
            "marks": [{"studentUserId": student_id, "status": "absent", "note": "medical"}],
        })
        assert r.status_code == 200, r.text
        assert r.json()["affected"] == 1

        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        me = client.get("/attendance/me", headers=_h(elev)).json()
        assert me["viewKind"] == "student"
        assert any(row["status"] == "absent" and row["note"] == "medical" for row in me["rows"])

    def test_student_cannot_mark(self):
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        r = client.post("/attendance/bulk", headers=_h(elev), json={
            "classId": 1, "date": "2026-06-08", "marks": [],
        })
        assert r.status_code == 403

    def test_absent_mark_fires_notification(self):
        tok = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        classes = client.get("/attendance/teacher/classes", headers=_h(tok)).json()
        cls_id = classes[0]["id"]
        roster = client.get(f"/attendance/roster/{cls_id}", headers=_h(tok)).json()
        student_id = roster[0]["userId"]

        client.post("/attendance/bulk", headers=_h(tok), json={
            "classId": cls_id, "date": "2026-06-09",
            "marks": [{"studentUserId": student_id, "status": "absent"}],
        })
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        notifs = client.get("/notifications?unread_only=true", headers=_h(elev)).json()
        assert any(n["kind"] == "attendance_marked" for n in notifs)


class TestChannels:
    def test_teacher_sees_their_channel(self):
        tok = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        r = client.get("/channels/mine", headers=_h(tok))
        assert r.status_code == 200
        chs = r.json()
        assert any(c["className"] == "4A" and c["subjectName"] == "Matematică" for c in chs)

    def test_teacher_posts_and_student_reads(self):
        tok = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        chs = client.get("/channels/mine", headers=_h(tok)).json()
        ch  = chs[0]
        r = client.post(
            f"/channels/{ch['classId']}/{ch['subjectId']}/post",
            headers=_h(tok),
            data={"text": "Salut clasă, lecția de azi este despre fracții"},
        )
        assert r.status_code == 200, r.text

        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        feed = client.get(f"/channels/{ch['classId']}/{ch['subjectId']}", headers=_h(elev)).json()
        assert any(p["kind"] == "post" and "fracții" in (p["text"] or "") for p in feed["posts"])

    def test_student_cannot_upload_files(self):
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        chs = client.get("/channels/mine", headers=_h(elev)).json()
        if not chs:
            pytest.skip("no channels visible to student")
        ch = chs[0]
        r = client.post(
            f"/channels/{ch['classId']}/{ch['subjectId']}/file",
            headers=_h(elev),
            files={"file": ("x.txt", b"hi", "text/plain")},
        )
        assert r.status_code == 403

    def test_teacher_uploads_and_student_downloads(self):
        tok = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        chs = client.get("/channels/mine", headers=_h(tok)).json()
        ch = chs[0]
        up = client.post(
            f"/channels/{ch['classId']}/{ch['subjectId']}/file",
            headers=_h(tok),
            files={"file": ("notite.txt", b"continut notite", "text/plain")},
        )
        assert up.status_code == 200, up.text
        post_id = up.json()["id"]

        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        r = client.get(f"/channels/post/{post_id}/file", headers=_h(elev))
        assert r.status_code == 200
        assert r.content == b"continut notite"

    def test_post_notifies_other_members(self):
        tok = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        chs = client.get("/channels/mine", headers=_h(tok)).json()
        ch = chs[0]
        client.post(
            f"/channels/{ch['classId']}/{ch['subjectId']}/post",
            headers=_h(tok), data={"text": "Anunț nou pentru toți"},
        )
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        notifs = client.get("/notifications?unread_only=true", headers=_h(elev)).json()
        assert any(n["kind"] == "channel_post" for n in notifs)
