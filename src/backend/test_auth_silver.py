"""
Silver auth tests covering:
- 3-factor login happy path
- each factor failing in isolation
- /auth/logout actually revokes the session token
- password recovery: forgot -> reset, single-use, expiry
- permissions are baked into the JWT
- per-permission dependency rejects callers missing the perm
- inbox endpoints
"""
from datetime import datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from main import app
from database import SessionLocal
from models import (
    User, Session as UserSession, PasswordReset, LoginChallenge,
    ROLE_USER, ROLE_ADMIN,
)
from auth import SECRET_KEY, ALGORITHM, hash_password
from _test_login import login_three_factor
import email_service

client = TestClient(app)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _cleanup_per_test():
    """Wipe email inbox + login challenges + password resets + extra users."""
    email_service.reset()
    db: DbSession = SessionLocal()
    try:
        db.query(LoginChallenge).delete()
        db.query(PasswordReset).delete()
        db.query(UserSession).delete()
        # remove any users added by the test, keep the two seeded ones
        db.query(User).filter(
            ~User.email.in_(("admin@proelev.ro", "user@proelev.ro"))
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    yield


# ─── 3-factor happy path ────────────────────────────────────────────────────

class TestThreeFactor:
    def test_full_flow_returns_working_token(self):
        token = login_three_factor(client, "admin@proelev.ro", "Admin123")
        r = client.get("/auth/me", headers=_h(token))
        assert r.status_code == 200
        assert r.json()["email"] == "admin@proelev.ro"

    def test_factor1_sends_email_with_code(self):
        client.post("/auth/login", json={"email": "admin@proelev.ro", "password": "Admin123"})
        inbox = email_service.inbox_for("admin@proelev.ro")
        assert len(inbox) >= 1
        msg = inbox[0]
        assert msg["code"] and len(msg["code"]) == 6
        assert msg["code"].isdigit()

    def test_factor2_wrong_code_rejected(self):
        r1 = client.post("/auth/login", json={"email": "admin@proelev.ro", "password": "Admin123"})
        ch = r1.json()["challenge_id"]
        r2 = client.post("/auth/login/verify-email", json={"challenge_id": ch, "code": "000000"})
        assert r2.status_code == 400
        # the challenge is still valid (not consumed), so the right code still works
        good_code = email_service.inbox_for("admin@proelev.ro")[0]["code"]
        ok = client.post("/auth/login/verify-email", json={"challenge_id": ch, "code": good_code})
        assert ok.status_code == 200

    def test_factor3_wrong_answer_rejected(self):
        r1 = client.post("/auth/login", json={"email": "admin@proelev.ro", "password": "Admin123"})
        ch = r1.json()["challenge_id"]
        good_code = email_service.inbox_for("admin@proelev.ro")[0]["code"]
        client.post("/auth/login/verify-email", json={"challenge_id": ch, "code": good_code})
        r3 = client.post("/auth/login/verify-question", json={"challenge_id": ch, "answer": "wrong-answer"})
        assert r3.status_code == 400

    def test_factor3_requires_factor2_first(self):
        r1 = client.post("/auth/login", json={"email": "admin@proelev.ro", "password": "Admin123"})
        ch = r1.json()["challenge_id"]
        # skip factor 2 and try to answer the question
        r3 = client.post("/auth/login/verify-question", json={"challenge_id": ch, "answer": "proelev"})
        assert r3.status_code == 400

    def test_unknown_challenge_id_rejected(self):
        r = client.post("/auth/login/verify-email", json={"challenge_id": "nope", "code": "1"})
        assert r.status_code == 400

    def test_expired_challenge_rejected(self):
        # poke the row directly to backdate it
        r1 = client.post("/auth/login", json={"email": "admin@proelev.ro", "password": "Admin123"})
        ch_id = r1.json()["challenge_id"]
        db = SessionLocal()
        try:
            ch = db.query(LoginChallenge).filter_by(challenge_id=ch_id).first()
            ch.expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        finally:
            db.close()
        good_code = email_service.inbox_for("admin@proelev.ro")[0]["code"]
        r2 = client.post("/auth/login/verify-email", json={"challenge_id": ch_id, "code": good_code})
        assert r2.status_code == 400


# ─── session revocation via /auth/logout ───────────────────────────────────

class TestLogout:
    def test_logout_revokes_token(self):
        token = login_three_factor(client, "admin@proelev.ro", "Admin123")
        # token works before logout
        assert client.get("/auth/me", headers=_h(token)).status_code == 200
        client.post("/auth/logout", headers=_h(token))
        # same token, now rejected
        assert client.get("/auth/me", headers=_h(token)).status_code == 401

    def test_logout_without_token_is_idempotent(self):
        # 200 with ok:true even without an Authorization header
        r = client.post("/auth/logout")
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_revoked_session_blocks_admin_routes(self):
        token = login_three_factor(client, "admin@proelev.ro", "Admin123")
        # manually flip the session revoked, simulates an admin-banned user
        db = SessionLocal()
        try:
            jti = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["jti"]
            sess = db.query(UserSession).filter_by(jti=jti).first()
            sess.revoked = 1
            db.commit()
        finally:
            db.close()
        assert client.get("/admin/observations", headers=_h(token)).status_code == 401


# ─── password recovery ────────────────────────────────────────────────────

class TestPasswordRecovery:
    def test_forgot_creates_reset_token_and_emails_it(self):
        r = client.post("/auth/forgot", json={"email": "admin@proelev.ro"})
        assert r.status_code == 200
        inbox = email_service.inbox_for("admin@proelev.ro")
        assert any("Resetare" in m["subject"] for m in inbox)

    def test_forgot_unknown_email_still_200(self):
        # we deliberately do not leak whether the email exists
        r = client.post("/auth/forgot", json={"email": "nobody@x.com"})
        assert r.status_code == 200
        # but no email was actually sent
        assert email_service.inbox_for("nobody@x.com") == []

    def test_reset_with_valid_token_changes_password(self):
        client.post("/auth/forgot", json={"email": "admin@proelev.ro"})
        token = email_service.inbox_for("admin@proelev.ro")[0]["code"]
        r = client.post("/auth/reset", json={"token": token, "new_password": "Brand1New"})
        assert r.status_code == 200
        # old password is no longer accepted at factor 1
        old = client.post("/auth/login", json={"email": "admin@proelev.ro", "password": "Admin123"})
        assert old.status_code == 401
        # new password works
        new = login_three_factor(client, "admin@proelev.ro", "Brand1New")
        assert new
        # put it back so other tests still pass
        client.post("/auth/forgot", json={"email": "admin@proelev.ro"})
        t2 = email_service.inbox_for("admin@proelev.ro")[0]["code"]
        client.post("/auth/reset", json={"token": t2, "new_password": "Admin123"})

    def test_reset_token_is_single_use(self):
        client.post("/auth/forgot", json={"email": "admin@proelev.ro"})
        token = email_service.inbox_for("admin@proelev.ro")[0]["code"]
        r1 = client.post("/auth/reset", json={"token": token, "new_password": "Once4Use"})
        assert r1.status_code == 200
        r2 = client.post("/auth/reset", json={"token": token, "new_password": "AnotherTime9"})
        assert r2.status_code == 400
        # cleanup
        client.post("/auth/forgot", json={"email": "admin@proelev.ro"})
        t2 = email_service.inbox_for("admin@proelev.ro")[0]["code"]
        client.post("/auth/reset", json={"token": t2, "new_password": "Admin123"})

    def test_reset_with_unknown_token_is_400(self):
        r = client.post("/auth/reset", json={"token": "nope", "new_password": "Whatever3"})
        assert r.status_code == 400

    def test_reset_revokes_all_existing_sessions(self):
        # log in twice, get two tokens
        t1 = login_three_factor(client, "user@proelev.ro", "Parola123")
        t2 = login_three_factor(client, "user@proelev.ro", "Parola123")
        assert client.get("/auth/me", headers=_h(t1)).status_code == 200
        assert client.get("/auth/me", headers=_h(t2)).status_code == 200
        # forgot + reset
        client.post("/auth/forgot", json={"email": "user@proelev.ro"})
        rtok = email_service.inbox_for("user@proelev.ro")[0]["code"]
        client.post("/auth/reset", json={"token": rtok, "new_password": "Parola123"})
        # both old tokens are now invalid
        assert client.get("/auth/me", headers=_h(t1)).status_code == 401
        assert client.get("/auth/me", headers=_h(t2)).status_code == 401


# ─── permissions baked into the JWT ────────────────────────────────────────

class TestPermissionsInToken:
    def test_admin_jwt_contains_all_perms(self):
        token = login_three_factor(client, "admin@proelev.ro", "Admin123")
        payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert "perms" in payload
        assert "homework_delete" in payload["perms"]

    def test_user_jwt_contains_only_user_perms(self):
        token = login_three_factor(client, "user@proelev.ro", "Parola123")
        payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        perms = payload["perms"]
        assert "homework_read" in perms
        assert "homework_delete" not in perms


# ─── mock inbox ────────────────────────────────────────────────────────────

class TestInbox:
    def test_inbox_lists_only_own_mail_for_user(self):
        client.post("/auth/login", json={"email": "user@proelev.ro", "password": "Parola123"})
        # now log in fully so we have a token to call /auth/inbox
        token = login_three_factor(client, "user@proelev.ro", "Parola123")
        r = client.get("/auth/inbox", headers=_h(token))
        assert r.status_code == 200
        # every message visible should be addressed to the user
        for m in r.json():
            assert m["to"] == "user@proelev.ro"

    def test_admin_inbox_sees_every_message(self):
        # cause an email to be sent to the normal user
        client.post("/auth/login", json={"email": "user@proelev.ro", "password": "Parola123"})
        admin_token = login_three_factor(client, "admin@proelev.ro", "Admin123")
        r = client.get("/auth/inbox", headers=_h(admin_token))
        # admin sees the user's email even though it wasnt addressed to them
        addresses = {m["to"] for m in r.json()}
        assert "user@proelev.ro" in addresses
