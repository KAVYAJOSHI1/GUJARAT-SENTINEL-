"""
vehicle_events data-retention purge.

SENTINEL_System_Audit_Report.md §12 raised that `vehicle_events` grows
unbounded and that "mass ANPR retention of every vehicle movement is a real
policy/privacy question". This implements a configurable time-boxed purge.

Guarantees:
  * Only `vehicle_events` rows are ever deleted.
  * A `vehicle_events` row referenced by any `alerts` row is NEVER deleted,
    regardless of age -- the alert, its watchlist entry, and the audit log
    are the permanent record and must keep their evidence pointer intact.
  * `watchlist`, `alerts`, `audit_logs`, `users`, `cameras` are never
    touched.
  * `VEHICLE_EVENT_RETENTION_DAYS <= 0` disables purging (returns 0).

The periodic sweep runs from the FastAPI lifespan task (app/main.py); this
module is also called directly by POST /api/v1/admin/retention/purge and by
the tests.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlmodel import Session

logger = logging.getLogger("sentinel.retention")


def purge_old_vehicle_events(
    db: Session,
    *,
    retention_days: int,
    now: Optional[datetime] = None,
) -> int:
    """Delete `vehicle_events` older than `retention_days` that are not
    referenced by an alert. Returns the number of rows deleted.

    Commits its own transaction. Raises on a real DB error (the caller --
    lifespan task or admin endpoint -- decides how to handle that); it does
    not swallow failures the way audit logging does, because a silently
    failing retention job is itself a compliance problem.
    """
    if retention_days is None or retention_days <= 0:
        return 0

    ref = now or datetime.now(timezone.utc)
    cutoff = ref - timedelta(days=retention_days)

    result = db.execute(
        text(
            """
            DELETE FROM vehicle_events ve
            WHERE ve.timestamp < :cutoff
              AND NOT EXISTS (
                  SELECT 1 FROM alerts a WHERE a.vehicle_event_id = ve.id
              )
            """
        ),
        {"cutoff": cutoff},
    )
    deleted = result.rowcount or 0
    db.commit()
    if deleted:
        logger.info(
            "retention: purged %d vehicle_events older than %s (%d-day policy)",
            deleted, cutoff.isoformat(), retention_days,
        )
    return deleted
