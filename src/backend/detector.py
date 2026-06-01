"""
Gold, malicious behavior detector
runs after every logged action for the user that just acted
each rule scans a 60 second rolling window of that users action_log rows
returns a list of matched reasons and a total score, when the score crosses
the threshold the user is added or updated in the observation table

rule list, kept simple and tunable from the constants at the top
- request flood, more than N requests in the window
- mass delete, more than N deletes in the window
- forbidden spam, more than N 403 responses in a row
- validation spam, more than N 422 responses
- privilege escalation, ANY non admin trying an admin only action
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from models import ActionLog, Observation, User, Session as UserSession, ROLE_ADMIN


# tunables, change these and the tests still pass since the tests trigger them on purpose
WINDOW_SECONDS         = 60
RATE_LIMIT             = 60   # > this many requests in WINDOW means flooding
RATE_POINTS            = 5
DELETE_LIMIT           = 5    # > this many deletes in WINDOW means mass delete
DELETE_POINTS          = 7
FORBIDDEN_LIMIT        = 3    # > this many 403s in WINDOW means probing
FORBIDDEN_POINTS       = 6
VALIDATION_LIMIT       = 10   # > this many 422s in WINDOW means fuzzing
VALIDATION_POINTS      = 4
PRIVILEGE_ESCAPE_POINTS = 10  # any single attempt by a non admin gets the full hit

# total score >= this puts the user on the observation list
OBSERVATION_THRESHOLD  = 10

# gold defense, when the score climbs this high we kill every session for the
# user so the attack stops cold. they can still log in again but the immediate
# burst is cut off.
BLOCK_THRESHOLD        = 25


def _recent_logs(db: Session, user_id: int) -> list[ActionLog]:
    """Rows for the user whose most recent hit lands inside the rolling window.
    We use last_seen_at because rows can be coalesced, a row with last_seen_at
    inside the window represents activity that ended inside the window.
    Rows that have never been bumped fall back to created_at."""
    cutoff = datetime.utcnow() - timedelta(seconds=WINDOW_SECONDS)
    return (
        db.query(ActionLog)
        .filter(
            ActionLog.user_id == user_id,
            (ActionLog.last_seen_at >= cutoff) | (ActionLog.created_at >= cutoff),
        )
        .all()
    )


def _count(rows) -> int:
    """Sum the .count field across rows, treating None as 1 for old data."""
    return sum((r.count or 1) for r in rows)


def _is_admin_only_path(action: str) -> bool:
    """The actions a normal user should never trigger successfully."""
    return action in {
        "homework.create", "homework.update", "homework.delete",
        "student.create",  "student.update",  "student.delete",
        "comment.update",  "comment.delete",
        "chat.room.create",
        "admin.logs.read", "admin.observation.read", "admin.observation.dismiss",
    }


def evaluate(db: Session, user_id: int) -> tuple[int, list[str]]:
    """
    Scan recent activity for one user, return (score, reasons).
    Caller decides whether to write the result to the observation table.
    """
    if not user_id:
        return 0, []

    logs = _recent_logs(db, user_id)
    if not logs:
        return 0, []

    score   = 0
    reasons: list[str] = []

    # request flood, sum across coalesced rows so 1 row x count=1000 still counts
    total_hits = _count(logs)
    if total_hits > RATE_LIMIT:
        score += RATE_POINTS
        reasons.append(f"request flood: {total_hits} requests in {WINDOW_SECONDS}s")

    # mass delete
    deletes = [l for l in logs if l.method == "DELETE" and 200 <= l.status_code < 300]
    n_del = _count(deletes)
    if n_del > DELETE_LIMIT:
        score += DELETE_POINTS
        reasons.append(f"mass delete: {n_del} successful deletes in {WINDOW_SECONDS}s")

    # repeated forbidden hits, common when probing for admin endpoints
    forbidden = [l for l in logs if l.status_code == 403]
    n_403 = _count(forbidden)
    if n_403 > FORBIDDEN_LIMIT:
        score += FORBIDDEN_POINTS
        reasons.append(f"forbidden spam: {n_403} 403s in {WINDOW_SECONDS}s")

    # 422 spam, common when fuzzing inputs
    validation = [l for l in logs if l.status_code == 422]
    n_422 = _count(validation)
    if n_422 > VALIDATION_LIMIT:
        score += VALIDATION_POINTS
        reasons.append(f"validation spam: {n_422} 422s in {WINDOW_SECONDS}s")

    # privilege escalation, even one attempt is loud
    user = db.get(User, user_id)
    role_name = user.role.name if user and user.role else None
    if role_name and role_name != ROLE_ADMIN:
        attempts = [l for l in logs if _is_admin_only_path(l.action)]
        if attempts:
            score += PRIVILEGE_ESCAPE_POINTS
            sample = attempts[-1].action
            reasons.append(f"privilege escalation: tried {sample} as {role_name}")

    return score, reasons


def update_observation(db: Session, user_id: int) -> Optional[Observation]:
    """
    Run evaluate for the user, write or update the observation row if the score
    crosses the threshold. Returns the row if one was written, None otherwise.
    """
    score, reasons = evaluate(db, user_id)
    if score < OBSERVATION_THRESHOLD:
        return None

    now = datetime.utcnow()
    reason_text = "; ".join(reasons)

    obs = db.query(Observation).filter_by(user_id=user_id).first()
    if obs:
        # update with the latest score and reason but keep first_flagged_at
        obs.score           = max(obs.score, score)
        obs.reason          = reason_text
        obs.last_flagged_at = now
        obs.dismissed       = 0  # any new hit re-opens a previously dismissed row
    else:
        obs = Observation(
            user_id=user_id, reason=reason_text, score=score,
            first_flagged_at=now, last_flagged_at=now, dismissed=0,
        )
        db.add(obs)

    # gold defense, if the score crossed the block line, revoke every session
    # for this user so any in-flight token stops working immediately
    if obs.score >= BLOCK_THRESHOLD:
        db.query(UserSession).filter_by(user_id=user_id, revoked=0).update(
            {"revoked": 1}, synchronize_session=False,
        )
    db.commit()
    return obs
