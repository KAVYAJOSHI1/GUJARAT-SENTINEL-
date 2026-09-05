"""
Watchlist Cross-Referencing Engine.
Given a persisted VehicleEvent, performs an exact normalized-plate lookup
against `watchlist`. On a hit, checks the 5-minute cooldown; if the
cooldown has expired it creates an `alerts` record and returns it so the
caller can broadcast it over WebSocket.

Pipeline (per DEVELOPER_README.md #9):
  ingest -> save event -> watchlist lookup
    match      -> cooldown check -> suppress | create alert + broadcast
    no match   -> return success (normal event logged)

Expiry (SENTINEL_System_Audit_Report.md §12/§15 "watchlist.expires_at never
enforced"): an entry with a past `expires_at` must never match, even while
`active` is still True (an operator may not have gotten around to manually
deactivating it yet) -- `active_watchlist_clause()` is the single shared
filter both this module and the vehicle-search API use, so the two can
never drift out of sync on what "currently on the watchlist" means.
"""
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlmodel import Session

from app.models.alert import Alert
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.services.cooldown import is_within_cooldown


def active_watchlist_clause(now: datetime | None = None):
    """SQLAlchemy WHERE clause matching only *currently valid* watchlist
    entries: active, and either no expiry or an expiry still in the future.
    An inactive or expired entry never matches, regardless of how it was
    deactivated (manual PATCH/DELETE or simply its `expires_at` elapsing)."""
    now = now or datetime.utcnow()
    return and_(
        Watchlist.active.is_(True),
        or_(Watchlist.expires_at.is_(None), Watchlist.expires_at > now),
    )


def find_watchlist_match(db: Session, plate_normalized: str) -> Watchlist | None:
    """Exact match against currently-valid watchlist entries (active,
    non-expired). O(log n) via the unique B-Tree index on the plate."""
    stmt = (
        select(Watchlist)
        .where(Watchlist.plate_number_normalized == plate_normalized)
        .where(active_watchlist_clause())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def process_event_against_watchlist(
    db: Session, event: VehicleEvent
) -> tuple[Watchlist | None, Alert | None, bool]:
    """
    Returns (matched_watchlist_entry, created_alert_or_None, suppressed_by_cooldown).
    Commits the new Alert row if one is created; caller handles the WS broadcast.
    """
    match = find_watchlist_match(db, event.plate_number_normalized)
    if match is None:
        return None, None, False

    if is_within_cooldown(db, event.plate_number_normalized, event.camera_id):
        return match, None, True

    alert = Alert(
        plate_number=event.plate_number,
        plate_number_normalized=event.plate_number_normalized,
        camera_id=event.camera_id,
        vehicle_event_id=event.id,
        watchlist_id=match.id,
        priority_level=match.priority_level,
        snapshot_url=event.snapshot_url,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return match, alert, False
