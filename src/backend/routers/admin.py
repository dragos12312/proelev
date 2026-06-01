"""
Gold admin endpoints, locked behind the admin role.
The caller no longer passes user_id, the bearer token does the talking.
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db
from models import User, ActionLog, Observation
from auth import get_current_admin
import ai_detector

router = APIRouter()


@router.get("/logs")
def list_logs(
    page:     int = Query(default=1, ge=1),
    pageSize: int = Query(default=50, ge=1, le=500),
    only_user_id: int | None = Query(default=None),
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Recent action_log rows newest first, optional filter by user_id."""
    q = db.query(ActionLog)
    if only_user_id is not None:
        q = q.filter(ActionLog.user_id == only_user_id)
    total = q.count()
    # most recently active row first, falls back to created_at when last_seen_at is null
    rows = (
        q.order_by(desc(ActionLog.last_seen_at), desc(ActionLog.created_at), desc(ActionLog.id))
        .offset((page - 1) * pageSize).limit(pageSize).all()
    )

    # backend stores naive utc datetimes, append Z so the client knows it is utc
    # and can format in the local timezone
    def _iso_utc(dt):
        return dt.isoformat() + "Z" if dt else None

    return {
        "page": page, "pageSize": pageSize, "total": total,
        "items": [{
            "id":           r.id,
            "user_id":      r.user_id,
            "user_name":    r.user.name if r.user else None,
            "role":         r.role.name if r.role else None,
            "action":       r.action,
            "target_type":  r.target_type,
            "target_id":    r.target_id,
            "method":       r.method,
            "path":         r.path,
            "status":       r.status_code,
            "ip":           r.ip_address,
            "created_at":   _iso_utc(r.created_at),
            "last_seen_at": _iso_utc(r.last_seen_at) or _iso_utc(r.created_at),
            "count":        r.count or 1,
        } for r in rows],
    }


@router.get("/observations")
def list_observations(
    include_dismissed: bool = Query(default=False),
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """All flagged users, active first."""
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
        "first_flagged_at": r.first_flagged_at.isoformat() + "Z",
        "last_flagged_at":  r.last_flagged_at.isoformat() + "Z",
        "dismissed":        bool(r.dismissed),
    } for r in rows]


@router.post("/ai/run")
def ai_run_now(
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Trigger one detection cycle synchronously. Used by the admin panel's
    'run now' button so the lab teacher doesn't have to wait the 30s gap."""
    return ai_detector.run_once(db)


@router.post("/observations/{flagged_user_id}/dismiss")
def dismiss_observation(
    flagged_user_id: int,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    obs = db.query(Observation).filter_by(user_id=flagged_user_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="Observatie inexistenta")
    obs.dismissed = 1
    obs.last_flagged_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
