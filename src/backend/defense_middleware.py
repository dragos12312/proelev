"""
Gold defense, one middleware that does three things:

1. Rate limits requests per IP, configurable per route group.
2. Rejects oversized request bodies before reading them.
3. Adds standard security headers to every response.

This sits BEFORE the audit middleware so refused requests show up in the
log as either 413 (too big) or 429 (rate limited).

Limits are kept in-memory because the assignment's data layer is in-memory
anyway. For a real deployment you would swap the buckets for Redis or
similar.
"""
import os
import time
import threading
from collections import defaultdict, deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


# ─── tunables, override via env vars at runtime ─────────────────────────────
GENERAL_LIMIT       = int(os.environ.get("RL_GENERAL_LIMIT",       "120"))  # req per window
GENERAL_WINDOW_SEC  = int(os.environ.get("RL_GENERAL_WINDOW_SEC",   "60"))  # rolling window
AUTH_LIMIT          = int(os.environ.get("RL_AUTH_LIMIT",            "20"))  # /auth/* tighter
AUTH_WINDOW_SEC     = int(os.environ.get("RL_AUTH_WINDOW_SEC",       "60"))
MAX_BODY_BYTES      = int(os.environ.get("MAX_BODY_BYTES",  str(1 * 1024 * 1024)))  # 1 MB

# ─── state, keyed by (bucket_name, ip) ──────────────────────────────────────
_buckets: dict[tuple[str, str], deque] = defaultdict(deque)
_lock = threading.Lock()


def _bucket_for(path: str) -> tuple[str, int, int]:
    """Return (bucket_name, limit, window_seconds) for a request path."""
    if path.startswith("/auth/"):
        return ("auth", AUTH_LIMIT, AUTH_WINDOW_SEC)
    return ("general", GENERAL_LIMIT, GENERAL_WINDOW_SEC)


def _client_ip(request: Request) -> str:
    """Best-effort client IP; respects X-Forwarded-For when behind a proxy."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _allow(bucket: str, ip: str, limit: int, window: float) -> tuple[bool, int]:
    """Sliding-window counter. Returns (allowed, retry_after_seconds)."""
    now = time.monotonic()
    with _lock:
        q = _buckets[(bucket, ip)]
        # drop entries older than the window
        while q and (now - q[0]) > window:
            q.popleft()
        if len(q) >= limit:
            retry_in = int(window - (now - q[0])) + 1
            return False, max(retry_in, 1)
        q.append(now)
        return True, 0


_SECURITY_HEADERS = {
    "X-Content-Type-Options":  "nosniff",
    "X-Frame-Options":         "DENY",
    "Referrer-Policy":         "strict-origin-when-cross-origin",
    # HSTS is only meaningful over https but harmless otherwise, the lab demo
    # runs over https with the self-signed cert from make_cert.py
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    # CSP is permissive on purpose, frontend is plain html+js, no inline eval
    "Content-Security-Policy": "default-src 'self'; img-src * data:; "
                               "connect-src *; style-src 'self' 'unsafe-inline'; "
                               "script-src 'self'; frame-ancestors 'none'",
}


def _stamp(resp: Response) -> Response:
    for k, v in _SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    return resp


class DefenseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. body size check, runs from the content-length header so we
        #    refuse before the body is read into memory
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return _stamp(JSONResponse(
                {"detail": "Request body too large"},
                status_code=413,
            ))

        # 2. rate limit, per IP, per bucket
        bucket, limit, window = _bucket_for(request.url.path)
        ip = _client_ip(request)
        allowed, retry_in = _allow(bucket, ip, limit, window)
        if not allowed:
            resp = JSONResponse(
                {"detail": f"Rate limit exceeded for bucket={bucket}, retry in {retry_in}s"},
                status_code=429,
            )
            resp.headers["Retry-After"] = str(retry_in)
            return _stamp(resp)

        # 3. defer to the rest of the stack
        response = await call_next(request)

        # 4. always stamp the security headers
        return _stamp(response)


def reset_for_tests() -> None:
    """Wipe all rate limit buckets, used between tests."""
    with _lock:
        _buckets.clear()
