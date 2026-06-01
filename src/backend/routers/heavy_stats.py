"""
Assignment 5 gold, heavy computational stat over a M2M relationship.

Three modes for /stats/by-tag, selectable via the `mode` query param:

  mode=naive   default. iterates tags, for each one fetches its students via
               the ORM relationship, then iterates again to compute the
               average. classic N+1 problem, also re-evaluates from scratch
               on every call. easy to DDOS with JMeter.

  mode=indexed single SQL aggregate using the indices added in migration
               7cfc4d9b5eab on student_tag.tag_id and student.grade. orders
               of magnitude faster than naive.

  mode=cached  same as indexed but the result is held in an in-process TTL
               cache. subsequent calls inside the TTL return instantly and
               do zero DB work.

Every response also reports its own wall-clock so the admin perf-demo page
can chart the speed-up.
"""
import time
import threading
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import Tag, Student, student_tag, User
from auth import get_current_user


router = APIRouter()


# ── tiny TTL cache for the cached mode ──────────────────────────────────────
_CACHE_TTL_SEC = 60
_cache: dict = {"expires_at": 0.0, "payload": None}
_cache_lock = threading.Lock()


def _cache_get():
    with _cache_lock:
        if _cache["payload"] is not None and time.monotonic() < _cache["expires_at"]:
            return _cache["payload"]
        return None


def _cache_put(payload):
    with _cache_lock:
        _cache["payload"]    = payload
        _cache["expires_at"] = time.monotonic() + _CACHE_TTL_SEC


def cache_reset():
    with _cache_lock:
        _cache["payload"]    = None
        _cache["expires_at"] = 0.0


# ── naive mode, slow on purpose ─────────────────────────────────────────────
def _naive_compute(db: Session) -> list[dict]:
    """N+1 ORM walk so the lab teacher can see what bad code looks like."""
    out = []
    for tag in db.query(Tag).all():
        # Tag.students is a relationship traversal, lazy loads on every access
        students = tag.students
        grades = [s.grade for s in students if s.grade is not None]
        avg = round(sum(grades) / len(grades), 2) if grades else None
        out.append({
            "tag":             tag.name,
            "num_students":    len(students),
            "num_graded":      len(grades),
            "average_grade":   avg,
        })
    return out


# ── indexed mode, single grouped aggregate ──────────────────────────────────
def _indexed_compute(db: Session) -> list[dict]:
    """One query, hits the indices on student_tag.tag_id and student.grade.

    SELECT
        tag.name,
        COUNT(student_tag.student_id),
        COUNT(student.grade),
        AVG(student.grade)
    FROM tag
    LEFT JOIN student_tag ON student_tag.tag_id = tag.id
    LEFT JOIN student     ON student.id        = student_tag.student_id
    GROUP BY tag.id, tag.name
    """
    stmt = (
        select(
            Tag.name.label("tag"),
            func.count(student_tag.c.student_id).label("num_students"),
            func.count(Student.grade).label("num_graded"),
            func.avg(Student.grade).label("avg_grade"),
        )
        .select_from(Tag)
        .join(student_tag, student_tag.c.tag_id == Tag.id, isouter=True)
        .join(Student,     Student.id == student_tag.c.student_id, isouter=True)
        .group_by(Tag.id, Tag.name)
        .order_by(Tag.name)
    )
    return [
        {
            "tag":           row.tag,
            "num_students":  int(row.num_students or 0),
            "num_graded":    int(row.num_graded   or 0),
            "average_grade": round(float(row.avg_grade), 2) if row.avg_grade is not None else None,
        }
        for row in db.execute(stmt).all()
    ]


# ── endpoint ─────────────────────────────────────────────────────────────────
@router.get("/by-tag")
def by_tag(
    mode: str = Query(default="naive", pattern="^(naive|indexed|cached)$"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),  # auth required so JMeter has to log in first
):
    start = time.perf_counter()

    if mode == "cached":
        cached = _cache_get()
        if cached is not None:
            ms = (time.perf_counter() - start) * 1000
            return {
                "mode":        "cached",
                "from_cache":  True,
                "elapsed_ms":  round(ms, 2),
                "results":     cached,
            }
        # cache miss, compute via the fast path and store
        results = _indexed_compute(db)
        _cache_put(results)
    elif mode == "indexed":
        results = _indexed_compute(db)
    else:
        results = _naive_compute(db)

    ms = (time.perf_counter() - start) * 1000
    return {
        "mode":        mode,
        "from_cache":  False,
        "elapsed_ms":  round(ms, 2),
        "results":     results,
    }


# ── side-by-side perf demo, runs all three modes and reports timings ───────
@router.get("/perf-demo")
def perf_demo(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Runs all three modes back-to-back and returns per-mode wall-clock.
    The admin perf-demo page calls this and charts the result."""

    # warm cache so the second cached call actually hits it
    cache_reset()
    _ = _naive_compute(db)  # discard, we just want the timing
    t0 = time.perf_counter(); _naive_compute(db);   t_naive  = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter(); _indexed_compute(db); t_indexed = (time.perf_counter() - t0) * 1000

    # first cached call is the miss
    cache_reset()
    t0 = time.perf_counter(); _ = _indexed_compute(db); _cache_put(_); t_cache_miss = (time.perf_counter() - t0) * 1000
    # second cached call hits
    t0 = time.perf_counter(); _ = _cache_get();        t_cache_hit  = (time.perf_counter() - t0) * 1000

    return {
        "rows": {
            "tags":         db.query(Tag).count(),
            "students":     db.query(Student).count(),
            "tag_links":    db.execute(select(func.count()).select_from(student_tag)).scalar(),
        },
        "ms": {
            "naive":      round(t_naive,      2),
            "indexed":    round(t_indexed,    2),
            "cache_miss": round(t_cache_miss, 2),
            "cache_hit":  round(t_cache_hit,  2),
        },
    }
