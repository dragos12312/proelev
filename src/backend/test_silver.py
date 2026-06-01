"""
Silver assignment tests
- role and permission tables persist correctly
- login response carries role + permission codes
- chat REST endpoints, list rooms, list users, dms, history
- chat websocket two clients exchange a message
"""
import pytest
from fastapi.testclient import TestClient

from database import SessionLocal
from models import Role, Permission, User, ROLE_ADMIN, ROLE_USER, PERMISSIONS, ROLE_PERMISSIONS
from main import app
import chat_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def _wipe_chat():
    """Each test gets a fresh chat store, but the sql users stay."""
    chat_store.reset()
    yield


# ─── role / permission DB layer ──────────────────────────────────────────────

class TestRolesPermissionsDb:
    def test_admin_and_user_roles_seeded(self):
        db = SessionLocal()
        try:
            names = {r.name for r in db.query(Role).all()}
            assert ROLE_ADMIN in names
            assert ROLE_USER  in names
        finally:
            db.close()

    def test_all_permissions_seeded(self):
        db = SessionLocal()
        try:
            codes = {p.code for p in db.query(Permission).all()}
            for c in PERMISSIONS:
                assert c in codes
        finally:
            db.close()

    def test_admin_role_has_every_permission(self):
        db = SessionLocal()
        try:
            admin = db.query(Role).filter_by(name=ROLE_ADMIN).first()
            codes = {p.code for p in admin.permissions}
            assert codes == set(PERMISSIONS)
        finally:
            db.close()

    def test_user_role_is_strict_subset(self):
        db = SessionLocal()
        try:
            user_role = db.query(Role).filter_by(name=ROLE_USER).first()
            codes = {p.code for p in user_role.permissions}
            assert codes == set(ROLE_PERMISSIONS[ROLE_USER])
            # user must not have any of the admin only permissions
            assert "homework_delete" not in codes
            assert "homework_create" not in codes
        finally:
            db.close()

    def test_demo_users_seeded_with_roles(self):
        db = SessionLocal()
        try:
            admin = db.query(User).filter_by(email="admin@proelev.ro").first()
            user  = db.query(User).filter_by(email="user@proelev.ro").first()
            assert admin and admin.role.name == ROLE_ADMIN
            assert user  and user.role.name  == ROLE_USER
        finally:
            db.close()

    def test_user_role_fk_blocks_invalid_role(self):
        """Cant insert a user pointing at a role id that doesnt exist."""
        from sqlalchemy.exc import IntegrityError
        db = SessionLocal()
        try:
            db.add(User(email="x@y.com", password_hash="x", name="x", role_id=9999))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
        finally:
            db.close()


# ─── login returns role + permissions ────────────────────────────────────────

def _full_login_response(email, password):
    """Walk all 3 factors, return the body of the final verify-question call
    so the caller can inspect both the user object and the access_token."""
    r1 = client.post("/auth/login", json={"email": email, "password": password})
    challenge_id = r1.json()["challenge_id"]
    inbox = client.get(f"/auth/inbox/last?to={email}")
    code = inbox.json()["code"]
    client.post("/auth/login/verify-email", json={"challenge_id": challenge_id, "code": code})
    r3 = client.post("/auth/login/verify-question", json={
        "challenge_id": challenge_id, "answer": "proelev",
    })
    return r3


class TestLoginResponse:
    def test_admin_login_returns_admin_role(self):
        r = _full_login_response("admin@proelev.ro", "Admin123")
        assert r.status_code == 200
        u = r.json()["user"]
        assert u["role"] == ROLE_ADMIN
        # admin gets every permission
        assert set(u["permissions"]) == set(PERMISSIONS)

    def test_normal_user_login_returns_restricted_permissions(self):
        r = _full_login_response("user@proelev.ro", "Parola123")
        assert r.status_code == 200
        u = r.json()["user"]
        assert u["role"] == ROLE_USER
        perms = set(u["permissions"])
        assert "homework_delete" not in perms
        assert "homework_create" not in perms
        assert "homework_read" in perms
        assert "chat_send"     in perms

    def test_login_does_not_leak_password(self):
        r = _full_login_response("admin@proelev.ro", "Admin123")
        assert "password"      not in r.json()["user"]
        assert "password_hash" not in r.json()["user"]


# ─── chat REST ───────────────────────────────────────────────────────────────

def _ids():
    """Return the ids of the seeded admin and user."""
    db = SessionLocal()
    try:
        a = db.query(User).filter_by(email="admin@proelev.ro").first().id
        u = db.query(User).filter_by(email="user@proelev.ro").first().id
        return a, u
    finally:
        db.close()


def _tokens():
    """Log in as admin and user via the 3 factor flow, return both access tokens."""
    from _test_login import login_three_factor
    return (
        login_three_factor(client, "admin@proelev.ro", "Admin123"),
        login_three_factor(client, "user@proelev.ro",  "Parola123"),
    )


def _h(token):
    return {"Authorization": f"Bearer {token}"}


class TestChatRest:
    def test_global_room_visible_to_everyone(self):
        _, user_token = _tokens()
        r = client.get("/chat/rooms", headers=_h(user_token))
        assert r.status_code == 200
        rooms = r.json()
        assert any(room["type"] == "global" for room in rooms)

    def test_list_users_excludes_self(self):
        admin_id, user_id = _ids()
        admin_token, _ = _tokens()
        r = client.get("/chat/users", headers=_h(admin_token))
        assert r.status_code == 200
        ids = [u["id"] for u in r.json()]
        assert admin_id not in ids
        assert user_id in ids

    def test_open_dm_creates_room(self):
        admin_id, user_id = _ids()
        admin_token, _ = _tokens()
        r = client.post(f"/chat/dm?other_id={user_id}", headers=_h(admin_token))
        assert r.status_code == 200
        room = r.json()
        assert room["type"] == "dm"
        assert sorted(room["participants"]) == sorted([admin_id, user_id])

    def test_open_dm_is_idempotent(self):
        admin_id, user_id = _ids()
        admin_token, user_token = _tokens()
        a = client.post(f"/chat/dm?other_id={user_id}",  headers=_h(admin_token)).json()
        b = client.post(f"/chat/dm?other_id={admin_id}", headers=_h(user_token)).json()
        assert a["id"] == b["id"]

    def test_open_dm_with_self_rejected(self):
        admin_id, _ = _ids()
        admin_token, _ = _tokens()
        r = client.post(f"/chat/dm?other_id={admin_id}", headers=_h(admin_token))
        assert r.status_code == 400

    def test_create_room_admin_only(self):
        admin_token, user_token = _tokens()
        # normal user gets 403
        r = client.post("/chat/rooms?name=X", headers=_h(user_token))
        assert r.status_code == 403
        # admin succeeds
        r = client.post("/chat/rooms?name=Profesori", headers=_h(admin_token))
        assert r.status_code == 200
        room = r.json()
        assert room["type"] == "room"
        assert room["name"] == "Profesori"

    def test_history_blocks_outsiders(self):
        admin_token, user_token = _tokens()
        r = client.post("/chat/rooms?name=Privat", headers=_h(admin_token))
        room_id = r.json()["id"]
        # the normal user is not a participant
        r2 = client.get(f"/chat/rooms/{room_id}/messages", headers=_h(user_token))
        assert r2.status_code == 403

    def test_unauthenticated_request_rejected(self):
        r = client.get("/chat/rooms")
        assert r.status_code == 401


# ─── chat websocket two client roundtrip ─────────────────────────────────────

class TestChatWebSocket:
    def test_two_clients_see_each_others_messages(self):
        admin_id, _ = _ids()
        admin_token, user_token = _tokens()
        with client.websocket_connect("/chat/ws") as ws_admin, \
             client.websocket_connect("/chat/ws") as ws_user:
            # identify with the bearer token, server auto subscribes to global
            ws_admin.send_json({"type": "hello", "token": admin_token})
            assert ws_admin.receive_json()["type"] == "ready"
            ws_user.send_json({"type": "hello", "token": user_token})
            assert ws_user.receive_json()["type"] == "ready"

            global_id = chat_store.ensure_global_room()["id"]

            ws_admin.send_json({"type": "message", "room_id": global_id, "text": "salut"})
            seen_admin = ws_admin.receive_json()
            seen_user  = ws_user.receive_json()
            assert seen_admin["type"] == "message"
            assert seen_admin["message"]["text"] == "salut"
            assert seen_user["message"]["text"]  == "salut"
            assert seen_user["message"]["author_id"] == admin_id

    def test_message_persisted_to_tinydb(self):
        admin_token, _ = _tokens()
        with client.websocket_connect("/chat/ws") as ws:
            ws.send_json({"type": "hello", "token": admin_token})
            assert ws.receive_json()["type"] == "ready"
            global_id = chat_store.ensure_global_room()["id"]
            ws.send_json({"type": "message", "room_id": global_id, "text": "persistent"})
            ws.receive_json()
        msgs = chat_store.list_messages(global_id)
        assert any(m["text"] == "persistent" for m in msgs)

    def test_subscribe_to_unauthorised_room_silently_ignored(self):
        admin_id, _ = _ids()
        _, user_token = _tokens()
        priv = chat_store.create_special_room("X", [admin_id])
        with client.websocket_connect("/chat/ws") as ws:
            ws.send_json({"type": "hello", "token": user_token})
            assert ws.receive_json()["type"] == "ready"
            ws.send_json({"type": "subscribe", "room_id": priv["id"]})
            ws.send_json({"type": "message", "room_id": priv["id"], "text": "shouldnt deliver"})
        assert chat_store.list_messages(priv["id"]) == []

    def test_ws_rejects_bad_token(self):
        with client.websocket_connect("/chat/ws") as ws:
            ws.send_json({"type": "hello", "token": "not-a-real-token"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
