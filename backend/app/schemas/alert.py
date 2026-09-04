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
