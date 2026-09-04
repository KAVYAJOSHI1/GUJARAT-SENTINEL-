"""Alert (contract #3) and watchlist request/response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.base import AlertStatus, PriorityLevel


class AlertRead(BaseModel):
    id: str
    plate_number: str
    plate_number_normalized: Optional[str] = None
    camera_id: str
    # Enrichment joined from cameras (not stored on Alert itself) so the
    # incident/alert UI can show "cam04 — Paldi Circle" instead of a bare
    # backend UUID. None when the camera has since been removed.
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    location_desc: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    vehicle_event_id: str
    watchlist_id: str
    priority_level: PriorityLevel
    status: AlertStatus
    snapshot_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AlertAcknowledge(BaseModel):
    status: AlertStatus = AlertStatus.ACKNOWLEDGED


class WatchlistCreate(BaseModel):
    plate_number: str
    offense_category: str
    priority_level: PriorityLevel = PriorityLevel.MEDIUM
    reason: Optional[str] = None
    expires_at: Optional[datetime] = None


class WatchlistRead(BaseModel):
    id: str
    plate_number: str
    offense_category: str
    priority_level: PriorityLevel
    reason: Optional[str]
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True
