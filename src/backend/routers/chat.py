"""
Chat router, both REST and websocket endpoints
REST is used to list rooms and load history, websocket is used for live messages
the data layer is tinydb in chat_store
"""
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from database import get_db
from models import User
import chat_store

router = APIRouter()


# ─── REST ─────────────────────────────────────────────────────────────────────

# returns every room the caller can see, the global room is always first
# the user id comes through as a query param since we dont have proper auth tokens yet
@router.get("/rooms")
def my_rooms(user_id: int = Query(...), db: Session = Depends(get_db)):
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User inexistent")
    return chat_store.list_rooms_for_user(user_id)


@router.get("/users")
def list_other_users(user_id: int = Query(...), db: Session = Depends(get_db)):
    """List of users you can dm, everyone except yourself."""
    rows = db.query(User).filter(User.id != user_id).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role.name if u.role else None} for u in rows]


@router.post("/dm")
def open_dm(user_id: int = Query(...), other_id: int = Query(...), db: Session = Depends(get_db)):
    """Open or create the dm between caller and other_id."""
    me   = db.get(User, user_id)
    them = db.get(User, other_id)
    if not me or not them:
        raise HTTPException(status_code=404, detail="User inexistent")
    try:
        return chat_store.get_or_create_dm(me.id, them.id, me.name, them.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rooms")
def create_room(name: str, user_id: int = Query(...), participants: str = "", db: Session = Depends(get_db)):
    """
    Special room creation, admin only.
    participants is a comma separated list of user ids that should be allowed in.
    """
    me = db.get(User, user_id)
    if not me:
        raise HTTPException(status_code=404, detail="User inexistent")
    if not me.role or me.role.name != "admin":
        raise HTTPException(status_code=403, detail="Doar adminul poate crea camere")
    ids = [int(x) for x in participants.split(",") if x.strip()] if participants else []
    if me.id not in ids:
        ids.append(me.id)
    return chat_store.create_special_room(name.strip(), ids)


@router.get("/rooms/{room_id}/messages")
def history(room_id: int, user_id: int = Query(...), db: Session = Depends(get_db)):
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User inexistent")
    if not chat_store.can_user_see_room(user_id, room_id):
        raise HTTPException(status_code=403, detail="Nu ai acces la aceasta camera")
    return chat_store.list_messages(room_id)


# ─── WebSocket ────────────────────────────────────────────────────────────────

# every connected ws client paired with the user id and the rooms they subscribed to
_clients: list[dict] = []


async def _broadcast_to_room(room_id: int, payload: dict) -> None:
    """Send payload to every client currently subscribed to room_id."""
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
    state = {"ws": websocket, "user_id": None, "user_name": None, "rooms": set()}
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
                # client identifies itself with its user id and name
                state["user_id"]   = int(msg.get("user_id", 0))
                state["user_name"] = str(msg.get("user_name", ""))
                # auto subscribe to the global room
                global_room = chat_store.ensure_global_room()
                state["rooms"].add(global_room["id"])
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
                try:
                    stored = chat_store.add_message(room_id, state["user_id"], state["user_name"], text)
                except ValueError:
                    continue
                await _broadcast_to_room(room_id, {"type": "message", "room_id": room_id, "message": stored})

    except WebSocketDisconnect:
        pass
    finally:
        if state in _clients:
            _clients.remove(state)
