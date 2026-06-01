"""
Brute-force defense for /auth/login.

Tracks failed factor-1 attempts per (ip, email) tuple. After N consecutive
failures inside the window, further attempts from that pair are blocked
with 429 for a cooldown period.

A successful login resets the counter for that pair. Memory-only state.
"""
import os
import time
import threading
from collections import defaultdict


MAX_FAILURES   = int(os.environ.get("LOGIN_THROTTLE_MAX",      "5"))   # consecutive failures
WINDOW_SEC     = int(os.environ.get("LOGIN_THROTTLE_WINDOW",  "120"))  # in this window
LOCK_DURATION  = int(os.environ.get("LOGIN_THROTTLE_LOCK",    "300"))  # blocked for this long after


# (ip, email) -> {"failures": [t1, t2, ...], "locked_until": float}
_state: dict[tuple[str, str], dict] = defaultdict(lambda: {"failures": [], "locked_until": 0.0})
_lock = threading.Lock()


def _key(ip: str, email: str) -> tuple[str, str]:
    return (ip or "0.0.0.0", (email or "").strip().lower())


def is_locked(ip: str, email: str) -> tuple[bool, int]:
    """Return (locked, retry_in_seconds). Removes the lock if it expired."""
    now = time.monotonic()
    with _lock:
        entry = _state[_key(ip, email)]
        if entry["locked_until"] > now:
            return True, int(entry["locked_until"] - now) + 1
        return False, 0


def record_failure(ip: str, email: str) -> tuple[bool, int]:
    """Note one failed attempt. Returns (locked_after_this, retry_in_seconds)."""
    now = time.monotonic()
    with _lock:
        entry = _state[_key(ip, email)]
        # drop failures older than the window
        entry["failures"] = [t for t in entry["failures"] if (now - t) <= WINDOW_SEC]
        entry["failures"].append(now)
        if len(entry["failures"]) >= MAX_FAILURES:
            entry["locked_until"] = now + LOCK_DURATION
            entry["failures"] = []  # start fresh after lock expires
            return True, LOCK_DURATION
        return False, 0


def record_success(ip: str, email: str) -> None:
    """Clear the throttle for this pair on a successful login."""
    with _lock:
        k = _key(ip, email)
        if k in _state:
            del _state[k]


def reset_for_tests() -> None:
    with _lock:
        _state.clear()
