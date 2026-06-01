"""
Sliding session refresh.
Runs after every request. If the caller had a valid bearer token whose
session is still active, we mint a fresh one with the inactivity timer
reset to the full window and stash it in the X-Refresh-Token response
header. The frontend swaps it in.

Expired, invalid, or revoked tokens are NOT refreshed.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

import jwt as _jwt
from auth import SECRET_KEY, ALGORITHM, refresh_token_for_payload
from database import SessionLocal
from models import Session as UserSession


class RefreshTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return response
        token = auth_header.split(None, 1)[1].strip()

        try:
            payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except Exception:
            return response  # expired or invalid, nothing to refresh

        # silver, only refresh tokens whose session row is still active
        jti = payload.get("jti")
        if jti:
            db = SessionLocal()
            try:
                sess = db.query(UserSession).filter_by(jti=jti).first()
                if not sess or sess.revoked:
                    return response
            finally:
                db.close()

        response.headers["X-Refresh-Token"] = refresh_token_for_payload(payload)
        # tell browsers in the cors preflight that this header is readable
        response.headers["Access-Control-Expose-Headers"] = "X-Refresh-Token"
        return response
