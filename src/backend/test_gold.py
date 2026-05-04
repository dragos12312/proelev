"""
Gold assignment tests
- audit middleware writes one action_log row per request
- log row carries user_id, role_id, action code, status code
- detector triggers on each rule and writes the observation row
- admin endpoints reject non admins and serve flagged users to admins
"""
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient

from database import SessionLocal
from models import User, ActionLog, Observation, ROLE_USER, ROLE_ADMIN
from main import app
import detector

client = TestClient(app)


def _ids():
    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(email="admin@proelev.ro").first()
        user  = db.query(User).filter_by(email="user@proelev.ro").first()
        return admin.id, user.id
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _wipe_logs():
    """Each test starts with a clean log + observation table."""
    db = SessionLocal()
    try:
        db.query(ActionLog).delete()
        db.query(Observation).delete()
        db.commit()
    finally:
        db.close()
    yield


def _log_count(user_id=None) -> int:
    db = SessionLocal()
    try:
        q = db.query(ActionLog)
        if user_id is not None:
            q = q.filter(ActionLog.user_id == user_id)
        return q.count()
    finally:
        db.close()


# ─── audit middleware writes rows ────────────────────────────────────────────

class TestAuditLogging:
    def test_anonymous_request_logged_with_null_user(self):
        client.post("/auth/login", json={"email": "admin@proelev.ro", "password": "Admin123"})
        assert _log_count() >= 1
        db = SessionLocal()
        try:
            row = db.query(ActionLog).order_by(ActionLog.id.desc()).first()
            assert row.user_id is None
            assert row.action == "auth.login"
            assert row.method == "POST"
            assert row.status_code == 200
        finally:
            db.close()

    def test_authenticated_request_carries_user_and_role(self):
        admin_id, _ = _ids()
        client.get("/homeworks", headers={"X-User-Id": str(admin_id)})
        db = SessionLocal()
        try:
            row = db.query(ActionLog).order_by(ActionLog.id.desc()).first()
            assert row.user_id == admin_id
            assert row.role is not None
            assert row.role.name == ROLE_ADMIN
            assert row.action == "homework.list"
        finally:
            db.close()

    def test_failed_request_still_logged(self):
        # 404 should still appear in the log
        client.get("/homeworks/999999")
        db = SessionLocal()
        try:
            row = db.query(ActionLog).order_by(ActionLog.id.desc()).first()
            assert row.status_code == 404
            assert row.action == "homework.read"
        finally:
            db.close()

    def test_skipped_paths_not_logged(self):
        # the docs endpoint is in the skip list, no log row should appear
        before = _log_count()
        client.get("/docs")
        assert _log_count() == before


# ─── detector rules ──────────────────────────────────────────────────────────

def _seed_logs(user_id, count, **kw):
    """Insert N synthetic log rows for a user, all inside the last second."""
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
                # tiny offset so rows have distinct timestamps but all stay within the window
                created_at=now - timedelta(microseconds=i * 1000),
            ))
        db.commit()
    finally:
        db.close()


class TestDetectorRules:
    def test_request_flood_triggers(self):
        _, user_id = _ids()
        _seed_logs(user_id, detector.RATE_LIMIT + 5)
        db = SessionLocal()
        try:
            score, reasons = detector.evaluate(db, user_id)
        finally:
            db.close()
        assert score >= detector.RATE_POINTS
        assert any("flood" in r for r in reasons)

    def test_mass_delete_triggers(self):
        _, user_id = _ids()
        _seed_logs(user_id, detector.DELETE_LIMIT + 1, method="DELETE", status_code=204, action="homework.delete")
        db = SessionLocal()
        try:
            score, reasons = detector.evaluate(db, user_id)
        finally:
            db.close()
        assert any("mass delete" in r for r in reasons)

    def test_forbidden_spam_triggers(self):
        _, user_id = _ids()
        _seed_logs(user_id, detector.FORBIDDEN_LIMIT + 1, status_code=403)
        db = SessionLocal()
        try:
            score, reasons = detector.evaluate(db, user_id)
        finally:
            db.close()
        assert any("forbidden" in r for r in reasons)

    def test_validation_spam_triggers(self):
        _, user_id = _ids()
        _seed_logs(user_id, detector.VALIDATION_LIMIT + 1, status_code=422)
        db = SessionLocal()
        try:
            score, reasons = detector.evaluate(db, user_id)
        finally:
            db.close()
        assert any("validation" in r for r in reasons)

    def test_privilege_escalation_triggers_for_normal_user(self):
        _, user_id = _ids()
        _seed_logs(user_id, 1, action="homework.delete", method="DELETE", status_code=403)
        db = SessionLocal()
        try:
            score, reasons = detector.evaluate(db, user_id)
        finally:
            db.close()
        assert score >= detector.PRIVILEGE_ESCAPE_POINTS
        assert any("privilege" in r for r in reasons)

    def test_admin_doing_admin_action_does_not_trigger_escalation(self):
        admin_id, _ = _ids()
        _seed_logs(admin_id, 1, action="homework.delete", method="DELETE", status_code=204)
        db = SessionLocal()
        try:
            score, reasons = detector.evaluate(db, admin_id)
        finally:
            db.close()
        assert not any("privilege" in r for r in reasons)

    def test_no_recent_logs_yields_zero(self):
        _, user_id = _ids()
        db = SessionLocal()
        try:
            score, reasons = detector.evaluate(db, user_id)
        finally:
            db.close()
        assert score == 0 and reasons == []


# ─── observation table is updated when score crosses threshold ───────────────

class TestObservationUpdates:
    def test_threshold_crossed_creates_row(self):
        _, user_id = _ids()
        _seed_logs(user_id, 1, action="homework.delete", method="DELETE", status_code=403)
        db = SessionLocal()
        try:
            obs = detector.update_observation(db, user_id)
            assert obs is not None
            assert obs.score >= detector.OBSERVATION_THRESHOLD
            assert obs.dismissed == 0
        finally:
            db.close()

    def test_below_threshold_no_row(self):
        _, user_id = _ids()
        # only a few normal reads, well under any rule
        _seed_logs(user_id, 3)
        db = SessionLocal()
        try:
            obs = detector.update_observation(db, user_id)
            assert obs is None
            assert db.query(Observation).filter_by(user_id=user_id).count() == 0
        finally:
            db.close()

    def test_repeated_flag_keeps_first_flagged_at(self):
        _, user_id = _ids()
        _seed_logs(user_id, 1, action="homework.delete", method="DELETE", status_code=403)
        db = SessionLocal()
        try:
            first = detector.update_observation(db, user_id)
            ts1 = first.first_flagged_at
            # flag again with more bad activity
            _seed_logs(user_id, detector.DELETE_LIMIT + 1, method="DELETE", status_code=204, action="homework.delete")
            second = detector.update_observation(db, user_id)
            assert second.first_flagged_at == ts1
            assert second.last_flagged_at >= ts1
        finally:
            db.close()


# ─── admin endpoints ─────────────────────────────────────────────────────────

class TestAdminEndpoints:
    def test_logs_endpoint_requires_admin(self):
        admin_id, user_id = _ids()
        # normal user gets 403
        r = client.get(f"/admin/logs?user_id={user_id}")
        assert r.status_code == 403
        # admin gets 200 with a paginated payload
        r = client.get(f"/admin/logs?user_id={admin_id}")
        assert r.status_code == 200
        assert "items" in r.json() and "total" in r.json()

    def test_observations_endpoint_requires_admin(self):
        admin_id, user_id = _ids()
        assert client.get(f"/admin/observations?user_id={user_id}").status_code == 403
        assert client.get(f"/admin/observations?user_id={admin_id}").status_code == 200

    def test_dismiss_endpoint_marks_observation(self):
        admin_id, user_id = _ids()
        # seed an observation directly
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            db.add(Observation(
                user_id=user_id, reason="test", score=10,
                first_flagged_at=now, last_flagged_at=now, dismissed=0,
            ))
            db.commit()
        finally:
            db.close()
        r = client.post(f"/admin/observations/{user_id}/dismiss?user_id={admin_id}")
        assert r.status_code == 200
        # row is now dismissed and disappears from default list
        active = client.get(f"/admin/observations?user_id={admin_id}").json()
        assert all(o["user_id"] != user_id for o in active)
        # but shows up with include_dismissed=true
        all_rows = client.get(f"/admin/observations?user_id={admin_id}&include_dismissed=true").json()
        assert any(o["user_id"] == user_id and o["dismissed"] for o in all_rows)


# ─── end to end, real http traffic builds up the score ───────────────────────

class TestEndToEnd:
    def test_normal_user_trying_admin_routes_gets_observed(self):
        admin_id, user_id = _ids()
        # the user pokes at admin only routes a few times
        for _ in range(2):
            client.delete("/homeworks/999", headers={"X-User-Id": str(user_id)})
        # now check the observation list
        rows = client.get(f"/admin/observations?user_id={admin_id}").json()
        assert any(o["user_id"] == user_id for o in rows)
        flagged = next(o for o in rows if o["user_id"] == user_id)
        assert flagged["score"] >= detector.OBSERVATION_THRESHOLD
        assert "privilege" in flagged["reason"]
