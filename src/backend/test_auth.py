"""
Assignment 4, auth tests covering:
- bcrypt is used for storage and the plain password is never persisted
- login rejects bad credentials, returns a fresh token on success
- protected endpoints reject missing/bad/expired tokens with 401
- register creates a USER row and returns a usable token
- sliding refresh: each authenticated response carries a fresh token
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from models import User, Role, ROLE_USER, ROLE_ADMIN
from auth import SECRET_KEY, ALGORITHM, hash_password, verify_password
from _test_login import login_three_factor, login_three_factor_with_answer

client = TestClient(app)


# tiny helpers -----------------------------------------------------------

def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _login_only_password(email, password):
    """Just factor 1 of the 3-factor login, returns the http response."""
    return client.post("/auth/login", json={"email": email, "password": password})


def _full_login(email="admin@proelev.ro", password="Admin123"):
    """Walk all three factors with the demo answer, returns the access token."""
    return login_three_factor(client, email, password)


@pytest.fixture(autouse=True)
def _cleanup_extra_users():
    """Remove anyone registered during a test, keep the seeded admin + user."""
    yield
    db = SessionLocal()
    try:
        db.query(User).filter(
            ~User.email.in_(("admin@proelev.ro", "user@proelev.ro"))
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


# ─── password hashing ───────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_does_not_equal_plain(self):
        h = hash_password("hunter2")
        assert h != "hunter2"
        assert h.startswith("$2")  # bcrypt prefix

    def test_verify_round_trip(self):
        h = hash_password("hunter2")
        assert verify_password("hunter2", h)
        assert not verify_password("wrong", h)

    def test_verify_handles_garbage_hash(self):
        # malformed hash should not throw, just return False
        assert not verify_password("anything", "not-a-real-hash")

    def test_two_hashes_of_same_password_differ(self):
        # bcrypt salts each hash so identical passwords still produce different
        # hashes, important for resistance to rainbow tables
        a = hash_password("samepw")
        b = hash_password("samepw")
        assert a != b
        assert verify_password("samepw", a)
        assert verify_password("samepw", b)


# ─── login flow ─────────────────────────────────────────────────────────────

class TestLogin:
    def test_full_3factor_login_returns_token(self):
        token = _full_login("admin@proelev.ro", "Admin123")
        assert token and len(token) > 20
        # token works on a protected route
        r = client.get("/auth/me", headers=_h(token))
        assert r.status_code == 200
        assert r.json()["role"] == ROLE_ADMIN

    def test_factor1_wrong_password_blocks_flow(self):
        r = _login_only_password("admin@proelev.ro", "wrong")
        assert r.status_code == 401

    def test_factor1_unknown_email_blocks_flow(self):
        r = _login_only_password("nobody@x.com", "Admin123")
        assert r.status_code == 401

    def test_factor1_returns_challenge_not_token(self):
        body = _login_only_password("admin@proelev.ro", "Admin123").json()
        assert "challenge_id" in body
        assert "access_token" not in body

    def test_factor1_email_case_insensitive(self):
        r = _login_only_password("ADMIN@PROELEV.RO", "Admin123")
        assert r.status_code == 200


# ─── token verification on protected routes ────────────────────────────────

class TestProtectedRoutes:
    def test_admin_route_requires_token(self):
        assert client.get("/admin/observations").status_code == 401

    def test_admin_route_with_user_token_is_403(self):
        u = _full_login("user@proelev.ro", "Parola123")
        assert client.get("/admin/observations", headers=_h(u)).status_code == 403

    def test_admin_route_with_admin_token_is_200(self):
        a = _full_login("admin@proelev.ro", "Admin123")
        assert client.get("/admin/observations", headers=_h(a)).status_code == 200

    def test_bogus_token_is_401(self):
        assert client.get("/chat/rooms", headers=_h("not-a-token")).status_code == 401

    def test_token_with_wrong_signature_is_401(self):
        token = jwt.encode({"sub": "1", "role": "admin", "jti": "x"}, "wrong-secret", algorithm=ALGORITHM)
        assert client.get("/chat/rooms", headers=_h(token)).status_code == 401

    def test_expired_token_is_401(self):
        # mint a token that expired one minute ago, the jti points at nothing
        # so the session check would also reject it
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        payload = {
            "sub": "1", "role": ROLE_ADMIN, "jti": "expired-jti",
            "iat": int(past.timestamp()),
            "exp": int((past + timedelta(minutes=1)).timestamp()),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        assert client.get("/chat/rooms", headers=_h(token)).status_code == 401


# ─── register flow ─────────────────────────────────────────────────────────

REG_OK = {
    "name": "Tester", "email": "tester@proelev.ro", "password": "Pwd1234",
    "security_question": "Care e capitala Franței?",
    "security_answer":   "paris",
}


class TestRegister:
    def test_register_creates_user_and_returns_token(self):
        r = client.post("/auth/register", json=REG_OK)
        assert r.status_code == 201
        body = r.json()
        assert body["user"]["role"] == ROLE_USER
        me = client.get("/auth/me", headers=_h(body["access_token"]))
        assert me.status_code == 200
        assert me.json()["email"] == "tester@proelev.ro"

    def test_register_password_must_have_letter_and_digit(self):
        # missing digit
        assert client.post("/auth/register", json={**REG_OK, "email": "a@b.c", "password": "onlyletters"}).status_code == 422
        # missing letter
        assert client.post("/auth/register", json={**REG_OK, "email": "a@b.c", "password": "12345678"}).status_code == 422
        # too short
        assert client.post("/auth/register", json={**REG_OK, "email": "a@b.c", "password": "ab1"}).status_code == 422

    def test_register_email_must_look_like_email(self):
        r = client.post("/auth/register", json={**REG_OK, "email": "not-an-email"})
        assert r.status_code == 422

    def test_register_duplicate_email_is_409(self):
        r = client.post("/auth/register", json={**REG_OK, "email": "admin@proelev.ro"})
        assert r.status_code == 409

    def test_register_stores_hashed_password(self):
        client.post("/auth/register", json={**REG_OK, "email": "t2@proelev.ro"})
        db = SessionLocal()
        try:
            u = db.query(User).filter_by(email="t2@proelev.ro").first()
            assert u.password_hash != "Pwd1234"
            assert verify_password("Pwd1234", u.password_hash)
            # security question is stored, answer is bcrypt-hashed too
            assert u.security_question == "Care e capitala Franței?"
            assert u.security_answer_hash and u.security_answer_hash.startswith("$2")
        finally:
            db.close()

    def test_register_requires_security_question(self):
        # missing security_question field
        bad = {k: v for k, v in REG_OK.items() if k != "security_question"}
        bad["email"] = "x@y.com"
        assert client.post("/auth/register", json=bad).status_code == 422


# ─── sliding refresh ───────────────────────────────────────────────────────

class TestRefreshHeader:
    def test_authenticated_response_carries_refresh_token(self):
        a = _full_login("admin@proelev.ro", "Admin123")
        r = client.get("/auth/me", headers=_h(a))
        assert r.status_code == 200
        assert "x-refresh-token" in {k.lower() for k in r.headers.keys()}

    def test_refresh_token_is_valid_and_reusable(self):
        a = _full_login("admin@proelev.ro", "Admin123")
        r1 = client.get("/auth/me", headers=_h(a))
        fresh = r1.headers["X-Refresh-Token"]
        r2 = client.get("/auth/me", headers=_h(fresh))
        assert r2.status_code == 200

    def test_no_refresh_for_unauthenticated_response(self):
        r = client.get("/auth/me")  # 401
        assert "x-refresh-token" not in {k.lower() for k in r.headers.keys()}
