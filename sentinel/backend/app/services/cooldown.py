"""
Alert cooldown deduplicator.
Suppresses duplicate alert generation for the same normalized plate on the
same camera within ALERT_COOLDOWN_SECONDS (default 300s / 5 minutes).
Backed by the composite (plate_number_normalized, camera_id, created_at)
index on `alerts` for sub-15ms lookups.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlmodel import Session

from app.config import settings
from app.models.alert import Alert


def is_within_cooldown(db: Session, plate_normalized: str, camera_id: str) -> bool:
    """True if an alert for this plate+camera was already raised within the cooldown window."""
    cutoff = datetime.utcnow() - timedelta(seconds=settings.ALERT_COOLDOWN_SECONDS)
    stmt = (
        select(Alert.id)
        .where(Alert.plate_number_normalized == plate_normalized)
        .where(Alert.camera_id == camera_id)
        .where(Alert.created_at >= cutoff)
        .limit(1)
    )
    return db.execute(stmt).first() is not None
