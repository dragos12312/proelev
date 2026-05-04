"""
TinyDB-backed chat store, the NoSQL half of silver
two collections, rooms and messages
each room has a type, global, dm or room
- global is a single shared room every logged in user joins automatically
- dm rooms have exactly two participants and are created on demand
- room is a generic special room for topic chats, only admin can create them

stored on disk so chat history survives a server restart
the file path is configurable via CHAT_DB_PATH so tests use a temp file
"""
import os
import threading
from datetime import datetime
from tinydb import TinyDB, Query


CHAT_DB_PATH = os.environ.get("CHAT_DB_PATH", "./chat.json")
GLOBAL_ROOM_NAME = "Global"

# tinydb is not thread safe, fastapi runs requests on different threads
# so a simple lock around every read and write keeps things sane
_lock = threading.Lock()
_db = TinyDB(CHAT_DB_PATH)
_rooms = _db.table("rooms")
_messages = _db.table("messages")


def _next_id(table) -> int:
    """Atomic auto increment, tinydb gives us back a doc id but we want our own."""
    docs = table.all()
    return (max(d.get("id", 0) for d in docs) + 1) if docs else 1


def reset() -> None:
    """Wipe everything, used by tests."""
    with _lock:
        _db.drop_tables()
        # re-grab the new tables since drop_tables wipes our handles
        global _rooms, _messages
        _rooms = _db.table("rooms")
        _messages = _db.table("messages")


def reload(path: str) -> None:
    """Re-open the db at a different path, used by tests via CHAT_DB_PATH."""
    global _db, _rooms, _messages
    with _lock:
        _db.close()
        _db = TinyDB(path)
        _rooms = _db.table("rooms")
        _messages = _db.table("messages")


def ensure_global_room() -> dict:
    """Make sure the single global room exists, return it."""
    with _lock:
        Room = Query()
        existing = _rooms.get(Room.type == "global")
        if existing:
            return existing
        room = {
            "id":           _next_id(_rooms),
            "type":         "global",
            "name":         GLOBAL_ROOM_NAME,
            "participants": [],
        }
        _rooms.insert(room)
        return room


def list_rooms_for_user(user_id: int) -> list[dict]:
    """All rooms visible to this user, the global one plus any dm/room they are in."""
    ensure_global_room()
    with _lock:
        Room = Query()
        # global room is visible to everyone
        out = [r for r in _rooms.search(Room.type == "global")]
        # dms and special rooms only if the user is in the participants list
        out += _rooms.search((Room.type != "global") & (Room.participants.any([user_id])))
        # newest non global first, global pinned at the top
        out.sort(key=lambda r: (r["type"] != "global", -r["id"]))
        return out


def get_or_create_dm(user_a: int, user_b: int, name_a: str, name_b: str) -> dict:
    """Find the dm room between these two users or create it."""
    if user_a == user_b:
        raise ValueError("cant dm yourself")
    pair = sorted([user_a, user_b])
    with _lock:
        Room = Query()
        existing = _rooms.search(
            (Room.type == "dm") & (Room.participants == pair)
        )
        if existing:
            return existing[0]
        room = {
            "id":           _next_id(_rooms),
            "type":         "dm",
            "name":         f"{name_a} ↔ {name_b}",
            "participants": pair,
        }
        _rooms.insert(room)
        return room


def create_special_room(name: str, participant_ids: list[int]) -> dict:
    """Topic room with a fixed list of allowed users, admin only on the api side."""
    with _lock:
        room = {
            "id":           _next_id(_rooms),
            "type":         "room",
            "name":         name,
            "participants": list(set(participant_ids)),
        }
        _rooms.insert(room)
        return room


def get_room(room_id: int) -> dict | None:
    with _lock:
        Room = Query()
        return _rooms.get(Room.id == room_id)


def can_user_see_room(user_id: int, room_id: int) -> bool:
    room = get_room(room_id)
    if not room:
        return False
    if room["type"] == "global":
        return True
    return user_id in room.get("participants", [])


def list_messages(room_id: int, limit: int = 100) -> list[dict]:
    """Return the last N messages for a room, oldest first."""
    with _lock:
        Msg = Query()
        msgs = _messages.search(Msg.room_id == room_id)
        msgs.sort(key=lambda m: m["id"])
        return msgs[-limit:]


def add_message(room_id: int, author_id: int, author_name: str, text: str) -> dict:
    """Persist a message, return the stored row."""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty message")
    with _lock:
        msg = {
            "id":          _next_id(_messages),
            "room_id":     room_id,
            "author_id":   author_id,
            "author_name": author_name,
            "text":        text[:2000],
            "created_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        _messages.insert(msg)
        return msg
