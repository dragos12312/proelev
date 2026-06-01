"""
Heavy-stats + AI detector tests for assignment 5 gold.

Coverage:
- /stats/by-tag returns the same payload across all three modes
- cache mode actually caches between two consecutive calls
- the AI detector fits a model and writes observations when given a
  population with one heavily-noisy user
- the AI detector returns gracefully when there isn't enough data
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models import (
    Tag, Student, Homework, Subject, SchoolClass, ActionLog, Observation, User,
    student_tag,
)
from _test_login import login_three_factor
import ai_detector
import routers.heavy_stats as heavy_stats


client = TestClient(app)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _cleanup():
    """Wipe everything we touched."""
    db = SessionLocal()
    try:
        db.execute(student_tag.delete())
        db.query(Tag).delete()
        db.query(ActionLog).delete()
        db.query(Observation).delete()
        db.commit()
    finally:
        db.close()
    heavy_stats.cache_reset()
    yield


def _seed_small_m2m():
    """Drop a tiny dataset into the M2M so the three modes have something to compute."""
    db = SessionLocal()
    try:
        # need at least one homework so students attach somewhere
        subj = db.query(Subject).first()
        cls  = db.query(SchoolClass).first()
        hw = db.query(Homework).first()
        if not hw:
            hw = Homework(
                title="probe", subject_id=subj.id, class_id=cls.id,
                due_date=datetime.utcnow().date(), description="x", file_name=None,
            )
            db.add(hw)
            db.flush()
        # 3 tags
        tags = [Tag(name=f"t{i}") for i in range(3)]
        db.add_all(tags)
        db.flush()
        # 6 students with various grades
        students = []
        for i in range(6):
            s = Student(homework_id=hw.id, name=f"u{i}",
                        date_time="2026-01-01 10:00",
                        grade=(i + 1) * 2 if i < 5 else None)
            db.add(s)
            students.append(s)
        db.flush()
        # each student gets 1-2 tags
        links = [
            {"student_id": students[0].id, "tag_id": tags[0].id},
            {"student_id": students[1].id, "tag_id": tags[0].id},
            {"student_id": students[2].id, "tag_id": tags[1].id},
            {"student_id": students[3].id, "tag_id": tags[1].id},
            {"student_id": students[4].id, "tag_id": tags[2].id},
            {"student_id": students[5].id, "tag_id": tags[2].id},
            {"student_id": students[0].id, "tag_id": tags[1].id},  # overlap
        ]
        db.execute(student_tag.insert(), links)
        db.commit()
    finally:
        db.close()


# ─── /stats/by-tag ─────────────────────────────────────────────────────────

class TestByTag:
    def test_requires_auth(self):
        # no bearer header -> 401
        assert client.get("/stats/by-tag").status_code == 401

    def test_naive_and_indexed_return_same_data(self):
        _seed_small_m2m()
        t = login_three_factor(client, "admin@proelev.ro", "Admin123")
        a = client.get("/stats/by-tag?mode=naive",   headers=_h(t)).json()
        b = client.get("/stats/by-tag?mode=indexed", headers=_h(t)).json()
        # both return three tag rows with matching aggregates
        assert a["mode"] == "naive" and b["mode"] == "indexed"
        a_set = {(r["tag"], r["num_students"], r["num_graded"]) for r in a["results"]}
        b_set = {(r["tag"], r["num_students"], r["num_graded"]) for r in b["results"]}
        assert a_set == b_set

    def test_cached_mode_hits_after_first_call(self):
        _seed_small_m2m()
        t = login_three_factor(client, "admin@proelev.ro", "Admin123")
        r1 = client.get("/stats/by-tag?mode=cached", headers=_h(t)).json()
        r2 = client.get("/stats/by-tag?mode=cached", headers=_h(t)).json()
        assert r1["from_cache"] is False
        assert r2["from_cache"] is True

    def test_unknown_mode_returns_422(self):
        t = login_three_factor(client, "admin@proelev.ro", "Admin123")
        r = client.get("/stats/by-tag?mode=banana", headers=_h(t))
        assert r.status_code == 422


# ─── perf demo ─────────────────────────────────────────────────────────────

class TestPerfDemo:
    def test_perf_demo_returns_four_timings(self):
        _seed_small_m2m()
        t = login_three_factor(client, "admin@proelev.ro", "Admin123")
        r = client.get("/stats/perf-demo", headers=_h(t)).json()
        assert set(r["ms"].keys()) == {"naive", "indexed", "cache_miss", "cache_hit"}
        # cache_hit should be at least as fast as cache_miss
        assert r["ms"]["cache_hit"] <= r["ms"]["cache_miss"] + 5  # tolerate jitter


# ─── AI detector ──────────────────────────────────────────────────────────

class TestAiDetector:
    def _seed_action_logs(self, user_id, count, **kw):
        db = SessionLocal()
        try:
            u = db.get(User, user_id)
            now = datetime.utcnow()
            for i in range(count):
                db.add(ActionLog(
                    user_id=user_id, role_id=u.role_id,
                    action=kw.get("action", "homework.list"),
                    method=kw.get("method", "GET"),
                    path=kw.get("path", "/homeworks"),
                    status_code=kw.get("status_code", 200),
                    created_at=now - timedelta(microseconds=i * 1000),
                    last_seen_at=now - timedelta(microseconds=i * 1000),
                    count=1,
                ))
            db.commit()
        finally:
            db.close()

    def test_run_once_with_no_data_returns_not_fitted(self):
        r = ai_detector.run_once()
        assert r["fitted"] is False

    def test_run_once_fits_and_flags_outlier(self):
        # only admin + normal user are seeded, drop a third User row directly
        # so the IsolationForest has a proper population of three
        from models import Role
        from auth import hash_password
        db = SessionLocal()
        try:
            existing = db.query(User).filter_by(email="t3@proelev.ro").first()
            if not existing:
                role = db.query(Role).filter_by(name="user").first()
                db.add(User(
                    email="t3@proelev.ro", name="t3",
                    password_hash=hash_password("Pwd1234"),
                    role_id=role.id,
                    security_question="q?", security_answer_hash=hash_password("a"),
                ))
                db.commit()
            users = db.query(User).order_by(User.id).all()[:3]
        finally:
            db.close()
        assert len(users) >= 3
        normal_a, normal_b, noisy = users[0].id, users[1].id, users[2].id
        # ~10 normal-looking GETs each for the "normal" users
        self._seed_action_logs(normal_a, 10)
        self._seed_action_logs(normal_b, 10)
        # the noisy user fires 200 requests, lots of 403s and 422s
        self._seed_action_logs(noisy, 80, status_code=403, action="admin.logs.read", path="/admin/logs")
        self._seed_action_logs(noisy, 60, status_code=422, action="auth.login",     path="/auth/login")
        self._seed_action_logs(noisy, 60, status_code=204, method="DELETE",         path="/homeworks/1")

        r = ai_detector.run_once()
        assert r["fitted"] is True
        assert r["users"] >= 3
        flagged_ids = {f["user_id"] for f in r["flagged"]}
        assert noisy in flagged_ids, f"expected user {noisy} flagged, got {flagged_ids}"

        # the observation row was written too
        db = SessionLocal()
        try:
            obs = db.query(Observation).filter_by(user_id=noisy).first()
            assert obs is not None
            assert "ai:" in obs.reason
        finally:
            db.close()
