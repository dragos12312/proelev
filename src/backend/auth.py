"""
Auth module for assignment 4. Bronze added bcrypt + signed JWTs; silver
extends this with:

- per-session jti claim and a server-side Session table, so logout actually
  invalidates a token
- a permissions array baked into the JWT for fine-grained authorization
- a require_perm dependency for routes that need a specific capability

The bronze sliding-window refresh still works the same way through
refresh_middleware.py.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session as DbSession

from database import get_db
from models import User, Session as UserSession, ROLE_ADMIN


# config
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "dev-only-secret-replace-in-prod-with-something-at-least-32-bytes-please",
)
ALGORITHM  = "HS256"
ACCESS_TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", "30"))


# password hashing
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


# token helpers
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _sign(payload: dict) -> str:
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def issue_session_token(db: DbSession, user: User) -> str:
    """Create a Session row and sign a JWT that references it via jti."""
    jti = secrets.token_urlsafe(32)
    now = _now_utc()
    db.add(UserSession(
        user_id=user.id, jti=jti,
        created_at=now.replace(tzinfo=None),
        last_active_at=now.replace(tzinfo=None),
        revoked=0,
    ))
    db.commit()

    perms = sorted(p.code for p in user.role.permissions) if user.role else []
    payload = {
        "sub":  str(user.id),
        "role": user.role.name if user.role else "user",
        "perms": perms,
        "jti":  jti,
        "iat":  int(now.timestamp()),
        "exp":  int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),
    }
    return _sign(payload)


def refresh_token_for_payload(payload: dict) -> str:
    """Re-issue a token with the same identity but fresh exp. Used by the
    sliding-refresh middleware so we don't hit the DB on every request."""
    now = _now_utc()
    refreshed = dict(payload)
    refreshed["iat"] = int(now.timestamp())
    refreshed["exp"] = int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp())
    return _sign(refreshed)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesiune expirată, te rugăm să te autentifici din nou",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )


# FastAPI dependencies
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: DbSession = Depends(get_db),
) -> User:
    """Resolve the bearer token to a User row.
    Also checks that the session jti hasn't been revoked, and bumps last_active_at."""
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Lipsește token-ul de autentificare",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(creds.credentials)
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Token invalid")

    # session check, silver. older tokens without jti are rejected
    jti = payload.get("jti")
    if not jti:
        raise HTTPException(status_code=401, detail="Token fără sesiune validă")
    sess = db.query(UserSession).filter_by(jti=jti).first()
    if not sess or sess.revoked or sess.user_id != user_id:
        raise HTTPException(status_code=401, detail="Sesiune revocată")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Utilizator inexistent")

    # bump the heartbeat so admins can see who is currently active
    sess.last_active_at = _now_utc().replace(tzinfo=None)
    db.commit()
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.role or user.role.name != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Doar adminul")
    return user


def require_perm(code: str):
    """Dependency factory: only allow callers whose role grants `code`.
    Reads the perms array from the JWT instead of the role relationship so
    we don't hit the DB for the perm list."""
    def _check(
        creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
        user: User = Depends(get_current_user),
    ) -> User:
        # token always exists by the time get_current_user resolved
        payload = decode_token(creds.credentials)
        perms = payload.get("perms") or []
        if code not in perms:
            raise HTTPException(status_code=403, detail=f"Permisiune lipsă: {code}")
        return user
    return _check


def revoke_session(db: DbSession, jti: str) -> None:
    sess = db.query(UserSession).filter_by(jti=jti).first()
    if sess:
        sess.revoked = 1
        db.commit()


def try_get_user_id(request: Request, db: DbSession) -> Optional[int]:
    """Best-effort, used by the audit middleware which runs for unauthenticated
    requests too. Reads the bearer token without raising on missing/expired.
    Also returns None when the session has been revoked."""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(None, 1)[1].strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        jti = payload.get("jti")
        if jti:
            sess = db.query(UserSession).filter_by(jti=jti).first()
            if not sess or sess.revoked:
                return None
        return user_id
    except Exception:
        return None
