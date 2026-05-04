"""
Gold, admin only endpoints to view the audit log and observation list
also lets the admin dismiss a flagged user

auth is enforced the same simple way as chat for now
the caller passes user_id as a query param, we look up the user and check
their role is admin, no tokens yet, real auth comes in the next assignment
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db
from models import User, ActionLog, Observation, ROLE_ADMIN

router = APIRouter()


# helper, raises 403 if the caller is not an admin
def _require_admin(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User inexistent")
    if not u.role or u.role.name != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Doar adminul")
    return u


@router.get("/logs")
def list_logs(
    user_id:  int = Query(...),
    page:     int = Query(default=1, ge=1),
    pageSize: int = Query(default=50, ge=1, le=500),
    only_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Recent action_log rows newest first, optional filter by user_id."""
    _require_admin(db, user_id)
    q = db.query(ActionLog)
    if only_user_id is not None:
        q = q.filter(ActionLog.user_id == only_user_id)
    total = q.count()
    rows = q.order_by(desc(ActionLog.id)).offset((page - 1) * pageSize).limit(pageSize).all()
    return {
        "page": page, "pageSize": pageSize, "total": total,
        "items": [{
            "id":          r.id,
            "user_id":     r.user_id,
            "user_name":   r.user.name if r.user else None,
            "role":        r.role.name if r.role else None,
            "action":      r.action,
            "target_type": r.target_type,
            "target_id":   r.target_id,
            "method":      r.method,
            "path":        r.path,
            "status":      r.status_code,
            "ip":          r.ip_address,
            "created_at":  r.created_at.isoformat(),
        } for r in rows],
    }


@router.get("/observations")
def list_observations(
    user_id: int = Query(...),
    include_dismissed: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """All flagged users, active first."""
    _require_admin(db, user_id)
    q = db.query(Observation)
    if not include_dismissed:
        q = q.filter(Observation.dismissed == 0)
    rows = q.order_by(desc(Observation.last_flagged_at)).all()
    return [{
        "id":               r.id,
        "user_id":          r.user_id,
        "user_name":        r.user.name if r.user else None,
        "user_email":       r.user.email if r.user else None,
        "user_role":        r.user.role.name if r.user and r.user.role else None,
        "score":            r.score,
        "reason":           r.reason,
        "first_flagged_at": r.first_flagged_at.isoformat(),
        "last_flagged_at":  r.last_flagged_at.isoformat(),
        "dismissed":        bool(r.dismissed),
    } for r in rows]


@router.post("/observations/{flagged_user_id}/dismiss")
def dismiss_observation(
    flagged_user_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
):
    _require_admin(db, user_id)
    obs = db.query(Observation).filter_by(user_id=flagged_user_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="Observatie inexistenta")
    obs.dismissed = 1
    obs.last_flagged_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
