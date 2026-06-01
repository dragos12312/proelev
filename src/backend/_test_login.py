"""
Shared helper for tests that need to complete the silver 3-factor login.

Usage:
    from _test_login import login_three_factor
    token = login_three_factor(client, "admin@proelev.ro", "Admin123")
"""
from fastapi.testclient import TestClient


def login_three_factor(client: TestClient, email: str, password: str) -> str:
    """Walk all three factors using the mock inbox. Returns the access token."""
    r1 = client.post("/auth/login", json={"email": email, "password": password})
    assert r1.status_code == 200, r1.text
    challenge_id = r1.json()["challenge_id"]

    # the mock inbox holds the code, fetch the latest message for this email
    inbox = client.get(f"/auth/inbox/last?to={email}")
    code = inbox.json()["code"]

    r2 = client.post("/auth/login/verify-email", json={
        "challenge_id": challenge_id, "code": code,
    })
    assert r2.status_code == 200, r2.text

    # demo users seeded by seed_lookups all have the same answer "proelev"
    # tests that create their own users supply their own helper
    r3 = client.post("/auth/login/verify-question", json={
        "challenge_id": challenge_id, "answer": "proelev",
    })
    assert r3.status_code == 200, r3.text
    return r3.json()["access_token"]


def login_three_factor_with_answer(
    client: TestClient, email: str, password: str, answer: str
) -> str:
    """Same as login_three_factor but with a custom security answer, used for
    self-registered users where the answer differs from the demo default."""
    r1 = client.post("/auth/login", json={"email": email, "password": password})
    assert r1.status_code == 200, r1.text
    challenge_id = r1.json()["challenge_id"]
    inbox = client.get(f"/auth/inbox/last?to={email}")
    code = inbox.json()["code"]
    r2 = client.post("/auth/login/verify-email", json={
        "challenge_id": challenge_id, "code": code,
    })
    assert r2.status_code == 200, r2.text
    r3 = client.post("/auth/login/verify-question", json={
        "challenge_id": challenge_id, "answer": answer,
    })
    assert r3.status_code == 200, r3.text
    return r3.json()["access_token"]
