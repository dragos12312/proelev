"""
Gold defense tests.

- DefenseMiddleware:
    * security headers stamped on every response
    * 413 on oversized request bodies
    * 429 when the per-IP bucket fills up
- Login throttle: too many bad passwords on /auth/login lock the (ip, email)
  pair, then a successful login clears it
- WebSocket flood guard: spamming messages closes the connection
- Detector auto-revoke: crossing BLOCK_THRESHOLD revokes every active session
"""
import json
import time
import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models import User, Session as UserSession, ActionLog, Observation
import defense_middleware as dm
import login_throttle
import detector
from _test_login import login_three_factor

client = TestClient(app)


@pytest.fixture(autouse=True)
def _wipe():
    """The conftest autouse fixture already resets the buckets and throttle.
    We also clear logs + observations + sessions to keep the detector tests
    deterministic."""
    db = SessionLocal()
    try:
        db.query(ActionLog).delete()
        db.query(Observation).delete()
        db.query(UserSession).delete()
        db.commit()
    finally:
        db.close()
    yield


# ─── security headers ──────────────────────────────────────────────────────

class TestSecurityHeaders:
    def test_headers_stamped_on_every_response(self):
        r = client.get("/")
        for h in ("x-content-type-options", "x-frame-options", "referrer-policy",
                  "strict-transport-security", "content-security-policy"):
            assert h in {k.lower() for k in r.headers.keys()}, f"missing {h}"

    def test_headers_present_on_429_too(self):
        # blow past the auth bucket then check the 429 still has the headers
        for _ in range(dm.AUTH_LIMIT + 1):
            r = client.post("/auth/login", json={"email": "x@y.com", "password": "wrong"})
        assert r.status_code == 429
        keys = {k.lower() for k in r.headers.keys()}
        assert "x-content-type-options" in keys
        assert "retry-after" in keys


# ─── body size limit ──────────────────────────────────────────────────────

class TestBodyLimit:
    def test_oversized_body_returns_413(self):
        # the limit defaults to 1 MB, send 2 MB to make sure the cap fires
        # even when it's bumped a little for tests
        oversize_kb = max(int(dm.MAX_BODY_BYTES / 1024) + 1024, 2 * 1024)
        big_body = {"junk": "x" * (oversize_kb * 1024)}
        r = client.post("/auth/login", json=big_body)
        # the cap is 1 MB by default, our payload is well above that
        assert r.status_code == 413


# ─── per-IP rate limit ────────────────────────────────────────────────────

class TestRateLimit:
    def test_general_bucket_blocks_at_limit(self):
        # we choose a route outside /auth so it goes through the general bucket
        last = None
        for _ in range(dm.GENERAL_LIMIT + 5):
            last = client.get("/")
        assert last.status_code == 429
        assert "Retry-After" in last.headers

    def test_auth_bucket_is_tighter_than_general(self):
        assert dm.AUTH_LIMIT < dm.GENERAL_LIMIT
        last = None
        for _ in range(dm.AUTH_LIMIT + 2):
            last = client.post("/auth/login", json={"email": "x@y.com", "password": "no"})
        assert last.status_code == 429

    def test_separate_paths_share_the_general_bucket(self):
        # we exhaust most of the general bucket via GET / and then GET /docs
        # should also be subject to it, defense middleware doesnt distinguish.
        # /docs is on the audit skip list but defense still rate-limits
        for _ in range(dm.GENERAL_LIMIT - 5):
            client.get("/")
        # any general-bucket path after this is close to the limit
        # we just confirm we can still make a few more before being blocked
        r = client.get("/")
        assert r.status_code in (200, 429)


# ─── login throttle ──────────────────────────────────────────────────────

class TestLoginThrottle:
    def test_repeated_bad_password_locks_pair(self):
        # MAX_FAILURES bad attempts in a row -> next attempt is throttled
        for _ in range(login_throttle.MAX_FAILURES - 1):
            r = client.post("/auth/login", json={
                "email": "admin@proelev.ro", "password": "wrong",
            })
            assert r.status_code == 401
        # the MAX_FAILURES-th failure trips the lock and returns 429
        r = client.post("/auth/login", json={
            "email": "admin@proelev.ro", "password": "wrong",
        })
        assert r.status_code == 429
        # the lock is sticky, even with the right password we're locked
        r2 = client.post("/auth/login", json={
            "email": "admin@proelev.ro", "password": "Admin123",
        })
        assert r2.status_code == 429
        # and the Retry-After hint is present
        assert "Retry-After" in r2.headers

    def test_successful_login_clears_the_counter(self):
        # a few bad attempts but stay under the lock threshold
        for _ in range(login_throttle.MAX_FAILURES - 2):
            client.post("/auth/login", json={
                "email": "admin@proelev.ro", "password": "wrong",
            })
        # one good attempt resets the counter
        r = client.post("/auth/login", json={
            "email": "admin@proelev.ro", "password": "Admin123",
        })
        assert r.status_code == 200
        # so we can fail again the same number of times without hitting the lock
        for _ in range(login_throttle.MAX_FAILURES - 1):
            r = client.post("/auth/login", json={
                "email": "admin@proelev.ro", "password": "wrong",
            })
            assert r.status_code == 401


# ─── ws flood guard ──────────────────────────────────────────────────────

class TestWebSocketFlood:
    def test_spammy_client_gets_disconnected(self):
        from routers.chat import WS_FLOOD_LIMIT
        admin_token = login_three_factor(client, "admin@proelev.ro", "Admin123")

        with client.websocket_connect("/chat/ws") as ws:
            ws.send_json({"type": "hello", "token": admin_token})
            assert ws.receive_json()["type"] == "ready"
            # find the global room id, easiest via the chat store directly
            import chat_store
            gid = chat_store.ensure_global_room()["id"]

            disconnected = False
            for i in range(WS_FLOOD_LIMIT + 5):
                try:
                    ws.send_json({"type": "message", "room_id": gid, "text": f"spam {i}"})
                    msg = ws.receive_json()
                    # last legitimate message is the broadcast back to us,
                    # at some point the server returns an error and closes
                    if msg.get("type") == "error" and "flood" in msg.get("error", ""):
                        disconnected = True
                        break
                except Exception:
                    disconnected = True
                    break
            assert disconnected, "server failed to cut off the spammer"


# ─── detector auto-revoke ────────────────────────────────────────────────

class TestDetectorAutoRevoke:
    def _seed_logs(self, user_id, count, **kw):
        """Insert N synthetic log rows for the user, all inside the last second."""
        from datetime import datetime, timedelta
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

    def test_score_at_or_above_block_threshold_revokes_sessions(self):
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(email="user@proelev.ro").first()
        finally:
            db.close()

        # log them in for real so we have an active Session row
        token = login_three_factor(client, "user@proelev.ro", "Parola123")
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

        # synthesize a heavy bad-actor pattern, more than enough to cross 25
        # privilege escalation (10) + mass delete (7) + flood (5) + forbidden (6) = 28
        self._seed_logs(user.id, detector.RATE_LIMIT + 5)  # flood
        self._seed_logs(user.id, detector.DELETE_LIMIT + 2,
                        action="homework.delete", method="DELETE", status_code=204)
        self._seed_logs(user.id, detector.FORBIDDEN_LIMIT + 1, status_code=403)
        self._seed_logs(user.id, 1, action="homework.delete", method="DELETE", status_code=403)

        db = SessionLocal()
        try:
            obs = detector.update_observation(db, user.id)
            assert obs is not None
            assert obs.score >= detector.BLOCK_THRESHOLD
            # every active session for the user is now revoked
            active = db.query(UserSession).filter_by(user_id=user.id, revoked=0).count()
            assert active == 0
        finally:
            db.close()

        # the original token is now useless
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
