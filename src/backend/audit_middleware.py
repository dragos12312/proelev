"""
Gold, audit middleware
runs after every http request and writes a row to action_log
also calls the detector for the active user so the observation list updates live

the user id comes from the X-User-Id request header which the frontend sets
after a successful login, requests without the header are logged with user_id null
which covers /auth/login and any anonymous probing
"""
import json
import re
from datetime import datetime
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from database import SessionLocal
from models import ActionLog, User
import detector


# paths we never log because they would dwarf the real signal
# the docs prefix and friends are matched with startswith, "/" is matched exactly
# since startswith("/") would skip every request
_SKIP_PREFIXES = ("/docs", "/openapi.json", "/redoc", "/favicon.ico")
_SKIP_EXACT    = ("/",)


# url -> short action code, used by the detector for the "admin only path" rule
# patterns are tried top to bottom, first match wins
_ROUTE_RULES = [
    # (method regex, path regex, action code, target type)
    (r"^GET$",       r"^/homeworks/?$",                                 "homework.list",         "homework"),
    (r"^POST$",      r"^/homeworks/?$",                                 "homework.create",       "homework"),
    (r"^GET$",       r"^/homeworks/(\d+)$",                             "homework.read",         "homework"),
    (r"^PUT$",       r"^/homeworks/(\d+)$",                             "homework.update",       "homework"),
    (r"^DELETE$",    r"^/homeworks/(\d+)$",                             "homework.delete",       "homework"),
    (r"^GET$",       r"^/homeworks/(\d+)/students.*",                   "student.list",          "student"),
    (r"^POST$",      r"^/homeworks/(\d+)/students.*",                   "student.create",        "student"),
    (r"^PUT$",       r"^/homeworks/(\d+)/students/(\d+)$",              "student.update",        "student"),
    (r"^DELETE$",    r"^/homeworks/(\d+)/students/(\d+)$",              "student.delete",        "student"),
    (r"^GET$",       r"^/homeworks/(\d+)/comments(/statistics)?.*",     "comment.list",          "comment"),
    (r"^POST$",      r"^/homeworks/(\d+)/comments/?$",                  "comment.create",        "comment"),
    (r"^PUT$",       r"^/homeworks/(\d+)/comments/(\d+)$",              "comment.update",        "comment"),
    (r"^DELETE$",    r"^/homeworks/(\d+)/comments/(\d+)$",              "comment.delete",        "comment"),
    (r"^GET$",       r"^/homeworks/(\d+)/statistics$",                  "homework.stats",        "homework"),
    (r"^POST$",      r"^/auth/login$",                                  "auth.login",            None),
    (r"^GET$",       r"^/chat/rooms/?$",                                "chat.rooms.list",       "chat"),
    (r"^POST$",      r"^/chat/rooms/?$",                                "chat.room.create",      "chat"),
    (r"^GET$",       r"^/chat/users/?$",                                "chat.users.list",       "chat"),
    (r"^POST$",      r"^/chat/dm/?$",                                   "chat.dm.open",          "chat"),
    (r"^GET$",       r"^/chat/rooms/(\d+)/messages$",                   "chat.history",          "chat"),
    (r"^GET$",       r"^/admin/logs/?$",                                "admin.logs.read",       "admin"),
    (r"^GET$",       r"^/admin/observations/?$",                        "admin.observation.read","admin"),
    (r"^POST$",      r"^/admin/observations/(\d+)/dismiss$",            "admin.observation.dismiss","admin"),
    (r"^POST$",      r"^/generator/(start|stop)$",                      "generator.toggle",      "generator"),
    (r"^GET$",       r"^/generator/status$",                            "generator.status",      "generator"),
]
_COMPILED = [(re.compile(m), re.compile(p), a, t) for m, p, a, t in _ROUTE_RULES]


def classify(method: str, path: str) -> tuple[str, Optional[str], Optional[int]]:
    """Map a (method, path) pair to (action_code, target_type, target_id)."""
    for m_rx, p_rx, action, target in _COMPILED:
        if m_rx.match(method) and (mp := p_rx.match(path)):
            target_id = None
            for grp in mp.groups():
                if grp and grp.isdigit():
                    target_id = int(grp)
                    break
            return action, target, target_id
    # unknown route, still log it but with a generic action code
    return f"http.{method.lower()}", None, None


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # skip noise so logs only carry interesting events
        path = request.url.path
        if path in _SKIP_EXACT or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return response
        # websockets dont go through this middleware so no need to filter them

        # who did the action, header is set by the frontend after login
        raw = request.headers.get("X-User-Id")
        user_id: Optional[int] = None
        try:
            user_id = int(raw) if raw else None
        except ValueError:
            user_id = None

        action, target_type, target_id = classify(request.method, path)
        ip = request.client.host if request.client else None

        db = SessionLocal()
        try:
            role_id = None
            if user_id:
                u = db.get(User, user_id)
                role_id = u.role_id if u else None

            db.add(ActionLog(
                user_id     = user_id,
                role_id     = role_id,
                action      = action,
                target_type = target_type,
                target_id   = target_id,
                method      = request.method,
                path        = path,
                status_code = response.status_code,
                ip_address  = ip,
                details     = json.dumps({"qs": request.url.query}) if request.url.query else None,
                created_at  = datetime.utcnow(),
            ))
            db.commit()

            # run the detector for the user that just acted
            # if anything fires it writes to the observation table
            if user_id:
                try:
                    detector.update_observation(db, user_id)
                except Exception:
                    # never let the detector break the user request
                    db.rollback()
        finally:
            db.close()

        return response
