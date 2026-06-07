# fastapi entry point, wires all the routers and the websocket together
# data layer is sqlalchemy on top of sqlite, see database.py and models.py
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from routers import homeworks, students, auth, generator, comments, chat, admin, heavy_stats, invites, lookups
import notifications
from graphql_schema import schema as gql_schema
from database import SessionLocal
from seed import seed_lookups
from audit_middleware import AuditMiddleware
from refresh_middleware import RefreshTokenMiddleware
from defense_middleware import DefenseMiddleware
import ai_detector


# startup hook seeds the lookup tables and the default admin if the db is empty
# also launches the assignment 5 ai detector thread which scores user behavior
# in the background every 30 seconds
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        seed_lookups(db)
    finally:
        db.close()
    ai_detector.start_scheduler()
    try:
        yield
    finally:
        ai_detector.stop_scheduler()


app = FastAPI(
    title="ProElev API",
    description="Backend API for ProElev education management platform",
    version="2.0.0",
    lifespan=lifespan,
)

# open cors so the vite dev server can talk to the api from a different port
# also lets the cross machine demo work, the client can be on another box
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# gold, audit middleware that logs every request and runs the detector
# added AFTER cors so the cors preflights still respond first
app.add_middleware(AuditMiddleware)

# assignment 4 gold, defense middleware sits INSIDE audit so refused requests
# (429, 413) still show up in the action_log and admin can see the attack
app.add_middleware(DefenseMiddleware)

# assignment 4, sliding token refresh, runs after audit so every successful
# request bumps the inactivity timer on the caller's session token
app.add_middleware(RefreshTokenMiddleware)

app.include_router(auth.router,       prefix="/auth",       tags=["Auth"])
app.include_router(homeworks.router,  prefix="/homeworks",  tags=["Homeworks"])
app.include_router(students.router,   prefix="/homeworks",  tags=["Students"])
app.include_router(comments.router,   prefix="/homeworks",  tags=["Comments"])
app.include_router(generator.router,  prefix="/generator",  tags=["Generator"])
app.include_router(chat.router,       prefix="/chat",       tags=["Chat"])
app.include_router(admin.router,      prefix="/admin",      tags=["Admin"])
app.include_router(heavy_stats.router, prefix="/stats",      tags=["HeavyStats"])
app.include_router(invites.admin_router,  prefix="/admin",   tags=["Admin"])
app.include_router(invites.public_router, prefix="/auth",    tags=["Auth"])
app.include_router(lookups.router,        prefix="/lookups", tags=["Lookups"])
app.include_router(notifications.router,  prefix="/notifications", tags=["Notifications"])

# graphql lives under /graphql, same store as the rest endpoints
graphql_app = GraphQLRouter(gql_schema)
app.include_router(graphql_app, prefix="/graphql", tags=["GraphQL"])

# list of every connected ws client, we push events to all of them
_ws_clients: list[WebSocket] = []


# sends a json payload to every connected client, drops the ones that have died
async def broadcast(data: dict):
    message = json.dumps(data)
    disconnected = []
    for client in _ws_clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.append(client)
    for c in disconnected:
        _ws_clients.remove(c)


# the only ws endpoint, the frontend opens it on login and listens for events
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.remove(websocket)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ProElev API is running"}


# ─── temporary deploy-debug endpoints ───────────────────────────────────────
# safe to delete once the public deploy is verified, no auth on purpose so we
# can hit them from a phone without going through the 3 factor login

from models import User as _User  # local alias so the import lives near use
from auth import verify_password as _verify


@app.get("/debug/users", tags=["Debug"])
def debug_users():
    """Lists every user row in the db. Used to confirm the seeder ran."""
    db = SessionLocal()
    try:
        return {
            "count": db.query(_User).count(),
            "users": [
                {
                    "id": u.id,
                    "email": u.email,
                    "name": u.name,
                    "role": u.role.name if u.role else None,
                    "has_password_hash": bool(u.password_hash),
                    "password_hash_starts": (u.password_hash or "")[:7],
                }
                for u in db.query(_User).all()
            ],
        }
    finally:
        db.close()


@app.post("/debug/reseed", tags=["Debug"])
def debug_reseed():
    """Force-run seed_lookups against the current db.
    Returns what's in the user table afterwards."""
    db = SessionLocal()
    try:
        seed_lookups(db)
        return debug_users()
    finally:
        db.close()


@app.get("/debug/verify", tags=["Debug"])
def debug_verify(email: str, password: str):
    """Take an email + password as query params and report whether the
    bcrypt hash on disk matches. Lets us tell apart 'user not found' from
    'password mismatch' without leaking the actual hash."""
    db = SessionLocal()
    try:
        u = db.query(_User).filter_by(email=email.strip().lower()).first()
        if not u:
            return {"found": False}
        return {
            "found":             True,
            "password_matches":  _verify(password, u.password_hash),
            "hash_prefix":       (u.password_hash or "")[:7],
        }
    finally:
        db.close()
