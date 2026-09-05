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


_BATCH_SIZE = 10_000

# Same predicate as before -- rows older than the cutoff that are NOT
# referenced by any alert. Phase 6: executed in bounded batches instead of
# one statement, so purging a large backlog on a big vehicle_events table
# does not run one multi-minute transaction (long lock, one huge WAL
# record, autovacuum starvation). Net effect is identical: the same rows
# are deleted, alert-referenced rows are always kept.
_DELETE_BATCH_SQL = text(
    """
    DELETE FROM vehicle_events
    WHERE id IN (
        SELECT ve.id FROM vehicle_events ve
        WHERE ve.timestamp < :cutoff
          AND NOT EXISTS (SELECT 1 FROM alerts a WHERE a.vehicle_event_id = ve.id)
        ORDER BY ve.timestamp        -- walk the timestamp index, oldest first
        LIMIT :batch
    )
    """
)


def purge_old_vehicle_events(
    db: Session,
    *,
    retention_days: int,
    now: Optional[datetime] = None,
    batch_size: int = _BATCH_SIZE,
) -> int:
    """Delete `vehicle_events` older than `retention_days` that are not
    referenced by an alert. Returns the total number of rows deleted.

    Deletes in batches of `batch_size`, committing each batch, so a large
    first-run backlog doesn't hold one enormous transaction. Raises on a
    real DB error (the caller decides how to handle that); it does not
    swallow failures the way audit logging does, because a silently failing
    retention job is itself a compliance problem.
    """
    if retention_days is None or retention_days <= 0:
        return 0

    ref = now or datetime.now(timezone.utc)
    cutoff = ref - timedelta(days=retention_days)
    batch = max(1, int(batch_size))

    total = 0
    while True:
        result = db.execute(_DELETE_BATCH_SQL, {"cutoff": cutoff, "batch": batch})
        n = result.rowcount or 0
        db.commit()
        total += n
        if n < batch:
            break

    if total:
        logger.info(
            "retention: purged %d vehicle_events older than %s (%d-day policy)",
            total, cutoff.isoformat(), retention_days,
        )
    return total
