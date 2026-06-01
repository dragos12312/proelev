"""
Assignment 5 gold, AI-based anomaly detection on top of the action_log.

Replaces nothing, runs alongside the hand-rolled detector.py rule engine.
Every N seconds (default 30) we:

  1. pull every user with at least MIN_HISTORY action_log rows
  2. build a feature vector per user from their recent activity
  3. fit a sklearn IsolationForest on the whole population
  4. score every user, anything below the contamination threshold gets
     written into the existing observation table with reason "ai:..."

That way the admin panel renders AI-flagged users right alongside
rule-based ones, no new UI plumbing needed.

The model is re-fit every cycle because the data is tiny and the dataset
shifts as users come and go. For a production deployment you'd persist
the fitted model and only re-fit weekly.
"""
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session as DbSession

from database import SessionLocal
from models import ActionLog, Observation, User


CYCLE_SEC          = int(os.environ.get("AI_CYCLE_SEC",      "30"))
WINDOW_SEC         = int(os.environ.get("AI_WINDOW_SEC",    "120"))
MIN_HISTORY        = int(os.environ.get("AI_MIN_HISTORY",     "5"))
CONTAMINATION      = float(os.environ.get("AI_CONTAMINATION", "0.15"))
MIN_USERS_TO_FIT   = int(os.environ.get("AI_MIN_USERS",       "3"))
WRITE_BACK         = os.environ.get("AI_WRITE_BACK", "1") == "1"


# ─── features ─────────────────────────────────────────────────────────────
# we compute six numeric features per user, chosen so an attacker who
# spams the api, scans admin endpoints, or fuzzes inputs sits in a
# different region of feature space than a normal user
_FEATURES = (
    "n_requests",
    "n_distinct_paths",
    "ratio_4xx",
    "ratio_403",
    "ratio_422",
    "ratio_delete",
)


def _user_features(db: DbSession, user_id: int) -> Optional[np.ndarray]:
    """Return a (6,) feature vector or None if there isn't enough history."""
    cutoff = datetime.utcnow() - timedelta(seconds=WINDOW_SEC)
    rows = (
        db.query(ActionLog)
        .filter(
            ActionLog.user_id == user_id,
            ((ActionLog.last_seen_at >= cutoff) | (ActionLog.created_at >= cutoff)),
        )
        .all()
    )
    if len(rows) < MIN_HISTORY:
        return None

    total = sum((r.count or 1) for r in rows)
    n_4xx = sum((r.count or 1) for r in rows if 400 <= r.status_code < 500)
    n_403 = sum((r.count or 1) for r in rows if r.status_code == 403)
    n_422 = sum((r.count or 1) for r in rows if r.status_code == 422)
    n_del = sum((r.count or 1) for r in rows if r.method == "DELETE")
    n_paths = len({r.path for r in rows})

    return np.array([
        total,
        n_paths,
        n_4xx / max(total, 1),
        n_403 / max(total, 1),
        n_422 / max(total, 1),
        n_del / max(total, 1),
    ], dtype=float)


def _build_dataset(db: DbSession) -> tuple[list[int], np.ndarray]:
    """Return (user_ids, feature_matrix) for everyone with enough history."""
    user_ids = []
    rows = []
    for (uid,) in db.query(ActionLog.user_id).filter(ActionLog.user_id.isnot(None)).distinct().all():
        v = _user_features(db, uid)
        if v is None:
            continue
        user_ids.append(uid)
        rows.append(v)
    if not rows:
        return [], np.zeros((0, len(_FEATURES)))
    return user_ids, np.vstack(rows)


def run_once(db: Optional[DbSession] = None) -> dict:
    """One detection cycle. Returns a summary dict for logging/tests."""
    owns_db = db is None
    db = db or SessionLocal()
    try:
        user_ids, X = _build_dataset(db)
        if X.shape[0] < MIN_USERS_TO_FIT:
            return {"fitted": False, "reason": "not enough users", "users": X.shape[0]}

        model = IsolationForest(
            n_estimators=80,
            contamination=CONTAMINATION,
            random_state=42,
        )
        model.fit(X)
        # decision_function: higher = more normal, lower = more anomalous
        scores = model.decision_function(X)
        preds  = model.predict(X)  # -1 means anomalous

        flagged = []
        for uid, score, pred, feats in zip(user_ids, scores, preds, X):
            if pred != -1:
                continue
            flagged.append({"user_id": uid, "score": float(score), "features": feats.tolist()})

            if WRITE_BACK:
                # write or update the observation row, mirrors rule-based detector
                _upsert_observation(db, uid, score, feats)

        if WRITE_BACK:
            db.commit()

        return {
            "fitted": True,
            "users":  X.shape[0],
            "flagged": flagged,
        }
    finally:
        if owns_db:
            db.close()


def _upsert_observation(db: DbSession, user_id: int, score: float, feats: np.ndarray) -> None:
    reason = (
        f"ai: anomaly score={score:.2f}, "
        f"requests={int(feats[0])}, "
        f"paths={int(feats[1])}, "
        f"4xx={feats[2]:.0%}, "
        f"403={feats[3]:.0%}, "
        f"422={feats[4]:.0%}, "
        f"delete={feats[5]:.0%}"
    )
    # ai score is negative for anomalous, map to a positive integer for the table
    # so the admin panel can sort by score consistently
    bumped_score = max(1, int(round(-score * 100)))

    obs = db.query(Observation).filter_by(user_id=user_id).first()
    now = datetime.utcnow()
    if obs:
        obs.score           = max(obs.score, bumped_score)
        obs.reason          = (obs.reason + "; " + reason) if "ai:" not in (obs.reason or "") else reason
        obs.last_flagged_at = now
        obs.dismissed       = 0
    else:
        db.add(Observation(
            user_id=user_id, reason=reason, score=bumped_score,
            first_flagged_at=now, last_flagged_at=now, dismissed=0,
        ))


# ─── background scheduler ─────────────────────────────────────────────────
_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def _loop():
    while not _stop_event.is_set():
        try:
            run_once()
        except Exception as e:
            # never crash the scheduler thread
            print(f"[ai_detector] cycle error: {e}")
        _stop_event.wait(CYCLE_SEC)


def start_scheduler() -> None:
    """Launch a daemon thread that runs the AI cycle every CYCLE_SEC."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="ai_detector")
    _thread.start()


def stop_scheduler() -> None:
    _stop_event.set()
