"""
Background ingest scheduler.

start_in_background() launches a daemon thread that:
1. Runs ingest immediately if taxi.duckdb is missing or stale (>24h).
2. Sleeps and re-runs ingest once every INTERVAL_HOURS thereafter.
"""

from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

INTERVAL_HOURS = 24
DB_PATH = "taxi.duckdb"
MARKER = Path(f"{DB_PATH}.last_ingest")


def _seconds_since_last_ingest() -> float:
    if not MARKER.exists():
        return float("inf")
    return time.time() - MARKER.stat().st_mtime


def needs_ingest() -> bool:
    if not Path(DB_PATH).exists():
        return True
    return _seconds_since_last_ingest() > INTERVAL_HOURS * 3600


def _touch_marker() -> None:
    MARKER.touch()


def run_once() -> None:
    """Synchronous one-shot ingest."""
    from ingest import ingest, make_default_months

    months = make_default_months()
    print(f"[scheduler] {datetime.now():%Y-%m-%d %H:%M:%S} ingest start months={months}")
    ingest(DB_PATH, months)
    _touch_marker()
    print(f"[scheduler] {datetime.now():%Y-%m-%d %H:%M:%S} ingest done")


def _loop() -> None:
    while True:
        try:
            if needs_ingest():
                run_once()
        except Exception:
            traceback.print_exc()

        # Sleep in small chunks so we can wake up quickly if the process exits
        remaining = INTERVAL_HOURS * 3600
        while remaining > 0:
            time.sleep(min(60, remaining))
            remaining -= 60


_started = False
_lock = threading.Lock()


def start_in_background() -> None:
    """Idempotent: safe to call multiple times."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    t = threading.Thread(target=_loop, daemon=True, name="ingest-scheduler")
    t.start()
    print("[scheduler] background thread started")
