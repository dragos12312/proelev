"""Tests for the formal-test (announce + grade + improvement splash) flow."""
import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models import (
    Test, TestGrade, TestImprovement, Notification, InviteCode,
)
from _test_login import login_three_factor

client = TestClient(app)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _clean():
    db = SessionLocal()
    try:
        # cascade: test_grade + test_improvement clear when test rows go
        db.query(TestImprovement).delete()
        db.query(TestGrade).delete()
        db.query(Test).delete()
        db.query(Notification).delete()
        db.query(InviteCode).delete()
        db.commit()
    finally:
        db.close()
    yield


class TestAnnounce:
    def test_teacher_announces_and_student_sees_it(self):
        tok = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        # the teacher's assignments lookup gives us the right ids
        pairs = client.get("/tests/lookups/my_assignments", headers=_h(tok)).json()
        p = next(p for p in pairs if p["className"] == "4A" and p["subjectName"] == "Matematică")
        r = client.post("/tests", headers=_h(tok), json={
            "classId": p["classId"], "subjectId": p["subjectId"],
            "title": "Test final fracții", "description": "10 exerciții",
            "scheduledDate": "2026-06-01",   # backdate allowed
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["title"] == "Test final fracții"
        # every real student in 4A should have a blank TestGrade row already
        assert len(body["grades"]) >= 1

        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        listed = client.get("/tests", headers=_h(elev)).json()
        assert any(t["title"] == "Test final fracții" for t in listed)

    def test_backdated_test_is_allowed(self):
        tok = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        pairs = client.get("/tests/lookups/my_assignments", headers=_h(tok)).json()
        p = pairs[0]
        r = client.post("/tests", headers=_h(tok), json={
            "classId": p["classId"], "subjectId": p["subjectId"],
            "title": "Test din trecut", "scheduledDate": "2020-01-15",
        })
        assert r.status_code == 200

    def test_student_cannot_announce(self):
        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        r = client.post("/tests", headers=_h(elev), json={
            "classId": 1, "subjectId": 1,
            "title": "Hax", "scheduledDate": "2026-06-01",
        })
        assert r.status_code == 403


class TestGrading:
    def test_teacher_grades_and_student_sees_only_own(self):
        tok = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        pairs = client.get("/tests/lookups/my_assignments", headers=_h(tok)).json()
        p = next(p for p in pairs if p["className"] == "4A" and p["subjectName"] == "Matematică")
        t = client.post("/tests", headers=_h(tok), json={
            "classId": p["classId"], "subjectId": p["subjectId"],
            "title": "T1", "scheduledDate": "2026-06-01",
        }).json()
        # the elev's row sits inside t.grades
        elev_row = next(g for g in t["grades"] if g["studentName"] and "Elev" in g["studentName"])
        r = client.post(
            f"/tests/{t['id']}/grade", headers=_h(tok),
            json={"studentUserId": elev_row["studentUserId"], "grade": 7},
        )
        assert r.status_code == 200, r.text

        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        detail = client.get(f"/tests/{t['id']}", headers=_h(elev)).json()
        # student only sees their own grade row
        assert len(detail["grades"]) == 1
        assert detail["grades"][0]["grade"] == 7


class TestImprovementSplash:
    def _setup_two_tests(self, prof_token):
        pairs = client.get("/tests/lookups/my_assignments", headers=_h(prof_token)).json()
        p = next(p for p in pairs if p["className"] == "4A" and p["subjectName"] == "Matematică")
        t_old = client.post("/tests", headers=_h(prof_token), json={
            "classId": p["classId"], "subjectId": p["subjectId"],
            "title": "Test vechi", "scheduledDate": "2026-05-01",
        }).json()
        t_new = client.post("/tests", headers=_h(prof_token), json={
            "classId": p["classId"], "subjectId": p["subjectId"],
            "title": "Test nou", "scheduledDate": "2026-06-01",
        }).json()
        return t_old, t_new

    def _elev_id_in(self, test_body):
        return next(g["studentUserId"] for g in test_body["grades"]
                    if g["studentName"] and "Elev" in g["studentName"])

    def test_three_point_jump_fires_improvement(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        t_old, t_new = self._setup_two_tests(prof)
        sid = self._elev_id_in(t_new)
        client.post(f"/tests/{t_old['id']}/grade", headers=_h(prof),
                    json={"studentUserId": sid, "grade": 5})
        client.post(f"/tests/{t_new['id']}/grade", headers=_h(prof),
                    json={"studentUserId": sid, "grade": 9})

        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        pending = client.get("/tests/improvements/pending", headers=_h(elev)).json()
        assert len(pending) == 1
        assert pending[0]["oldGrade"] == 5
        assert pending[0]["newGrade"] == 9
        assert pending[0]["delta"]    == 4

    def test_two_point_jump_does_not_fire(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        t_old, t_new = self._setup_two_tests(prof)
        sid = self._elev_id_in(t_new)
        client.post(f"/tests/{t_old['id']}/grade", headers=_h(prof),
                    json={"studentUserId": sid, "grade": 6})
        client.post(f"/tests/{t_new['id']}/grade", headers=_h(prof),
                    json={"studentUserId": sid, "grade": 8})

        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        pending = client.get("/tests/improvements/pending", headers=_h(elev)).json()
        assert pending == []

    def test_ack_clears_splash(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        t_old, t_new = self._setup_two_tests(prof)
        sid = self._elev_id_in(t_new)
        client.post(f"/tests/{t_old['id']}/grade", headers=_h(prof),
                    json={"studentUserId": sid, "grade": 4})
        client.post(f"/tests/{t_new['id']}/grade", headers=_h(prof),
                    json={"studentUserId": sid, "grade": 10})

        elev = login_three_factor(client, "elev@proelev.ro", "Elev1234")
        pending = client.get("/tests/improvements/pending", headers=_h(elev)).json()
        assert len(pending) == 1
        client.post(f"/tests/improvements/{pending[0]['id']}/ack", headers=_h(elev))
        again = client.get("/tests/improvements/pending", headers=_h(elev)).json()
        assert again == []

    def test_parent_also_sees_improvement(self):
        prof = login_three_factor(client, "prof@proelev.ro", "Profesor1")
        t_old, t_new = self._setup_two_tests(prof)
        sid = self._elev_id_in(t_new)
        client.post(f"/tests/{t_old['id']}/grade", headers=_h(prof),
                    json={"studentUserId": sid, "grade": 4})
        client.post(f"/tests/{t_new['id']}/grade", headers=_h(prof),
                    json={"studentUserId": sid, "grade": 8})

        par = login_three_factor(client, "parinte@proelev.ro", "Parinte1")
        pending = client.get("/tests/improvements/pending", headers=_h(par)).json()
        assert len(pending) == 1
        assert pending[0]["oldGrade"] == 4
        assert pending[0]["newGrade"] == 8
