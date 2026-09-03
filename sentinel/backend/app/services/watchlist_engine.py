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
"""
from sqlalchemy import select
from sqlmodel import Session

from app.models.alert import Alert
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.services.cooldown import is_within_cooldown


def find_watchlist_match(db: Session, plate_normalized: str) -> Watchlist | None:
    """Exact match against active watchlist entries. O(log n) via unique B-Tree index."""
    stmt = (
        select(Watchlist)
        .where(Watchlist.plate_number_normalized == plate_normalized)
        .where(Watchlist.active.is_(True))
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
