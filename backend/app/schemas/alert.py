"""Alert (contract #3) and watchlist request/response schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

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
    watchlist_id: Optional[str] = None       # None for source=ANOMALY (Phase 12)
    source: str = "WATCHLIST"
    anomaly_event_id: Optional[str] = None
    priority_level: PriorityLevel
    status: AlertStatus
    snapshot_url: Optional[str] = None
    created_at: datetime

    # Phase 11 escalation workflow (all None on a fresh NEW alert)
    assigned_to_user_id: Optional[str] = None
    assigned_to_username: Optional[str] = None
    acknowledged_by_user_id: Optional[str] = None
    acknowledged_by_username: Optional[str] = None
    escalated_by_user_id: Optional[str] = None
    escalated_by_username: Optional[str] = None
    escalated_at: Optional[datetime] = None
    escalation_reason: Optional[str] = None
    resolved_by_user_id: Optional[str] = None
    resolved_by_username: Optional[str] = None
    resolved_at: Optional[datetime] = None
    incident_id: Optional[str] = None
    incident_number: Optional[str] = None

    class Config:
        from_attributes = True


class AlertAcknowledge(BaseModel):
    status: AlertStatus = AlertStatus.ACKNOWLEDGED


class AlertAssign(BaseModel):
    user_id: Optional[str] = None


class AlertEscalate(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AlertResolve(BaseModel):
    note: Optional[str] = None


# --- watchlist ---------------------------------------------------------- #
class WatchlistCreate(BaseModel):
    plate_number: str
    offense_category: str
    priority_level: PriorityLevel = PriorityLevel.MEDIUM
    reason: Optional[str] = None
    description: Optional[str] = None
    effective_from: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class WatchlistUpdate(BaseModel):
    plate_number: Optional[str] = None
    offense_category: Optional[str] = None
    priority_level: Optional[PriorityLevel] = None
    reason: Optional[str] = None
    description: Optional[str] = None
    effective_from: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    active: Optional[bool] = None


class WatchlistRead(BaseModel):
    id: str
    plate_number: str
    plate_number_normalized: Optional[str] = None
    offense_category: str
    priority_level: PriorityLevel
    reason: Optional[str] = None
    description: Optional[str] = None
    active: bool
    effective_from: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_expired: bool = False
    is_pending: bool = False           # effective_from still in the future
    is_currently_effective: bool = True
    added_by_user_id: Optional[str] = None
    added_by_username: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    updated_by_username: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WatchlistPage(BaseModel):
    items: List[WatchlistRead]
    total: int
    limit: int
    offset: int


class WatchlistImportRow(BaseModel):
    line: int
    plate: Optional[str] = None
    outcome: str        # created | updated | skipped | invalid
    reason: Optional[str] = None


class WatchlistImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    invalid: int
    rows: List[WatchlistImportRow]
