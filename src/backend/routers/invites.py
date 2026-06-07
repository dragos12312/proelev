"""
Assignment 6, invite codes that gate teacher/student/parent self-registration.

Admin generates a code (POST /admin/invites), shares it with the new user, who
pastes it in the register form. The code locks down which role the new account
will have, and can optionally preset a class (for students) or subject (for
teachers). Codes expire after a configurable TTL (default 7 days) and are
single-use.

Public:
  GET  /auth/invite/check?code=XXX    returns role + preset class/subject so
                                     the register form can show "Vei fi
                                     înregistrat ca PROFESOR pentru
                                     Matematică 4A"

Admin only:
  POST /admin/invites                 generate a new code
  GET  /admin/invites                 list active codes (not used, not expired,
                                                         not revoked)
  POST /admin/invites/{id}/revoke     kill a code before it gets used
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_admin
from models import (
    InviteCode, SchoolClass, Subject, User,
    INVITE_CODE_TTL_DAYS,
    ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT,
)


router = APIRouter()


# admin endpoints live under /admin in main.py, public check under /auth
admin_router = APIRouter()
public_router = APIRouter()


_VALID_ROLES = {ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT}


# ─── schemas ────────────────────────────────────────────────────────────────

class InviteCreate(BaseModel):
    role: str
    class_id:   Optional[int] = None
    subject_id: Optional[int] = None
    ttl_days:   Optional[int] = None  # override default 7


def _invite_to_dict(inv: InviteCode) -> dict:
    return {
        "id":         inv.id,
        "code":       inv.code,
        "role":       inv.role_name,
        "class":      {"id": inv.preset_class.id,   "name": inv.preset_class.name}   if inv.preset_class   else None,
        "subject":    {"id": inv.preset_subject.id, "name": inv.preset_subject.name} if inv.preset_subject else None,
        "created_at": inv.created_at.isoformat() + "Z",
        "expires_at": inv.expires_at.isoformat() + "Z",
        "used_at":    inv.used_at.isoformat() + "Z" if inv.used_at else None,
        "used_by":    {"id": inv.used_by.id, "email": inv.used_by.email} if inv.used_by else None,
        "revoked":    bool(inv.revoked),
    }


# ─── admin: generate + list + revoke ──────────────────────────────────────

@admin_router.post("/invites")
def create_invite(
    body: InviteCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Rol invalid, alege din: {sorted(_VALID_ROLES)}")

    # validate the preset references exist
    if body.class_id is not None and not db.get(SchoolClass, body.class_id):
        raise HTTPException(status_code=400, detail="Clasa nu există")
    if body.subject_id is not None and not db.get(Subject, body.subject_id):
        raise HTTPException(status_code=400, detail="Materia nu există")

    # role-aware presets: teacher cant preset class without subject (or vice
    # versa) since their assignment is (class, subject). student presets class
    # only. parent doesn't preset anything.
    if body.role == ROLE_PARENT and (body.class_id or body.subject_id):
        raise HTTPException(status_code=400, detail="Codul pentru părinte nu acceptă clasă sau materie")
    if body.role == ROLE_STUDENT and body.subject_id:
        raise HTTPException(status_code=400, detail="Codul de elev nu acceptă materie")

    # 16 hex chars = ~64 bits, plenty against accidental guesses, short enough
    # for an admin to copy-paste comfortably
    code = secrets.token_hex(8).upper()
    while db.query(InviteCode).filter_by(code=code).first():
        code = secrets.token_hex(8).upper()

    now = datetime.utcnow()
    ttl_days = body.ttl_days if (body.ttl_days and body.ttl_days > 0) else INVITE_CODE_TTL_DAYS
    expires = now + timedelta(days=min(ttl_days, INVITE_CODE_TTL_DAYS))

    inv = InviteCode(
        code=code,
        role_name=body.role,
        class_id=body.class_id,
        subject_id=body.subject_id,
        created_by_user_id=admin.id,
        created_at=now,
        expires_at=expires,
        revoked=0,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return _invite_to_dict(inv)


@admin_router.get("/invites")
def list_invites(
    include_expired: bool = Query(default=False),
    include_used:    bool = Query(default=False),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    q = db.query(InviteCode).order_by(InviteCode.created_at.desc())
    rows = q.all()
    out = []
    for r in rows:
        is_expired = r.expires_at < now
        is_used    = bool(r.used_by_user_id)
        if not include_expired and is_expired and not is_used:
            continue
        if not include_used and is_used:
            continue
        out.append(_invite_to_dict(r))
    return out


@admin_router.post("/invites/{invite_id}/revoke")
def revoke_invite(
    invite_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    inv = db.get(InviteCode, invite_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Cod inexistent")
    if inv.used_by_user_id:
        raise HTTPException(status_code=400, detail="Codul a fost deja folosit")
    inv.revoked = 1
    db.commit()
    return {"ok": True}


# ─── public: check a code before submitting the full register form ──────

@public_router.get("/invite/check")
def check_invite(code: str, db: Session = Depends(get_db)):
    inv = db.query(InviteCode).filter_by(code=code.strip().upper()).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Cod invalid")
    if inv.revoked:
        raise HTTPException(status_code=400, detail="Codul a fost revocat")
    if inv.used_by_user_id:
        raise HTTPException(status_code=400, detail="Codul a fost deja folosit")
    if inv.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Codul a expirat")
    return {
        "role":    inv.role_name,
        "class":   {"id": inv.preset_class.id,   "name": inv.preset_class.name}   if inv.preset_class   else None,
        "subject": {"id": inv.preset_subject.id, "name": inv.preset_subject.name} if inv.preset_subject else None,
        "expires_at": inv.expires_at.isoformat() + "Z",
    }


# helper that the register route uses to validate + consume an invite
def consume_invite(db: Session, code: str, user: User) -> InviteCode:
    """Look up the code, validate it, mark it used. Raises HTTPException if
    anything is off. Caller is responsible for db.commit()."""
    inv = db.query(InviteCode).filter_by(code=code.strip().upper()).first()
    if not inv:
        raise HTTPException(status_code=400, detail="Cod invalid")
    if inv.revoked:
        raise HTTPException(status_code=400, detail="Codul a fost revocat")
    if inv.used_by_user_id:
        raise HTTPException(status_code=400, detail="Codul a fost deja folosit")
    if inv.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Codul a expirat")
    inv.used_by_user_id = user.id
    inv.used_at = datetime.utcnow()
    return inv
