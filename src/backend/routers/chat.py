"""
Chat router, REST + websocket. REST uses the bearer dependency, the websocket
accepts the same token as the first message of the protocol since browsers
cant attach custom headers to a WS handshake.
"""
import json
import os
import time
from collections import deque
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

# gold defense, chat flood guard, drop clients that spam messages
WS_FLOOD_LIMIT  = int(os.environ.get("WS_FLOOD_LIMIT",  "30"))   # messages
WS_FLOOD_WINDOW = int(os.environ.get("WS_FLOOD_WINDOW", "10"))   # seconds

from database import get_db, SessionLocal
from models import User, ROLE_ADMIN
from auth import get_current_user, decode_token
import chat_store

router = APIRouter()


# ─── REST ─────────────────────────────────────────────────────────────────────

@router.get("/rooms")
def my_rooms(me: User = Depends(get_current_user)):
    return chat_store.list_rooms_for_user(me.id)


@router.get("/users")
def list_other_users(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(User).filter(User.id != me.id).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role.name if u.role else None} for u in rows]


@router.post("/dm")
def open_dm(other_id: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    them = db.get(User, other_id)
    if not them:
        raise HTTPException(status_code=404, detail="User inexistent")
    try:
        return chat_store.get_or_create_dm(me.id, them.id, me.name, them.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rooms")
def create_room(
    name: str,
    participants: str = "",
    me: User = Depends(get_current_user),
):
    """Admin only special-room creation."""
    if not me.role or me.role.name != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Doar adminul poate crea camere")
    ids = [int(x) for x in participants.split(",") if x.strip()] if participants else []
    if me.id not in ids:
        ids.append(me.id)
    return chat_store.create_special_room(name.strip(), ids)


@router.get("/rooms/{room_id}/messages")
def history(room_id: int, me: User = Depends(get_current_user)):
    if not chat_store.can_user_see_room(me.id, room_id):
        raise HTTPException(status_code=403, detail="Nu ai acces la aceasta camera")
    return chat_store.list_messages(room_id)


# ─── WebSocket ────────────────────────────────────────────────────────────────

_clients: list[dict] = []


async def _broadcast_to_room(room_id: int, payload: dict) -> None:
    msg = json.dumps(payload)
    dead = []
    for c in _clients:
        if room_id in c["rooms"]:
            try:
                await c["ws"].send_text(msg)
            except Exception:
                dead.append(c)
    for c in dead:
        _clients.remove(c)


@router.websocket("/ws")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    state = {
        "ws": websocket, "user_id": None, "user_name": None,
        "rooms": set(),
        # gold, rolling window of recent message timestamps for flood detection
        "msg_times": deque(),
    }
    _clients.append(state)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await websocket.send_text(json.dumps({"type": "error", "error": "bad json"}))
                continue

            mtype = msg.get("type")
            if mtype == "hello":
                # the client identifies itself with the bearer token, we decode it
                # rather than trust raw user_id from the wire. previously we did
                # the latter for silver before tokens existed
                token = msg.get("token", "")
                try:
                    payload = decode_token(token) if token else None
                except Exception:
                    payload = None
                if not payload:
                    await websocket.send_text(json.dumps({"type": "error", "error": "auth"}))
                    continue

                # confirm the user actually exists, also grab the display name
                db = SessionLocal()
                try:
                    u = db.get(User, int(payload["sub"]))
                finally:
                    db.close()
                if not u:
                    await websocket.send_text(json.dumps({"type": "error", "error": "auth"}))
                    continue

                state["user_id"]   = u.id
                state["user_name"] = u.name
                # auto subscribe to every room the user can see
                for room in chat_store.list_rooms_for_user(u.id):
                    state["rooms"].add(room["id"])
                await websocket.send_text(json.dumps({"type": "ready"}))

            elif mtype == "subscribe":
                room_id = int(msg.get("room_id", 0))
                if state["user_id"] is None:
                    continue
                if chat_store.can_user_see_room(state["user_id"], room_id):
                    state["rooms"].add(room_id)
                    await websocket.send_text(json.dumps({"type": "subscribed", "room_id": room_id}))

            elif mtype == "message":
                room_id = int(msg.get("room_id", 0))
                text    = str(msg.get("text", ""))
                if state["user_id"] is None:
                    continue
                if not chat_store.can_user_see_room(state["user_id"], room_id):
                    continue

                # gold defense, slide the window, drop old timestamps
                now = time.monotonic()
                times = state["msg_times"]
                while times and (now - times[0]) > WS_FLOOD_WINDOW:
                    times.popleft()
                if len(times) >= WS_FLOOD_LIMIT:
                    # too many messages too fast, kill the connection
                    await websocket.send_text(json.dumps(
                        {"type": "error", "error": "flood, connection closed"}
                    ))
                    await websocket.close(code=1008)
                    break
                times.append(now)

                try:
                    stored = chat_store.add_message(room_id, state["user_id"], state["user_name"], text)
                except ValueError:
                    continue
                await _broadcast_to_room(room_id, {"type": "message", "room_id": room_id, "message": stored})

                # notify offline recipients. global room gets skipped so we
                # don't spam everyone; dms + group rooms notify everyone in
                # `participants` except the sender themselves
                try:
                    room = chat_store.get_room(room_id)
                    if room and room.get("type") != "global":
                        recipients = [p for p in room.get("participants", []) if p != state["user_id"]]
                        if recipients:
                            from notifications import notify_chat_message
                            notify_chat_message(
                                recipients,
                                author_name=state["user_name"] or "Cineva",
                                text=text,
                                room_id=room_id,
                            )
                except Exception as _e:
                    import logging; logging.getLogger(__name__).warning("notify_chat_message failed: %s", _e)

    except WebSocketDisconnect:
        pass
    finally:
        if state in _clients:
            _clients.remove(state)
