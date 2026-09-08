"""Unified Advanced Search + Global Quick Search schemas (FEATURE 1 / 14)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class VehicleSearchRow(BaseModel):
    """One vehicle_events row enriched with camera + relationship context."""

    event_id: str
    plate_number: str
    plate_number_normalized: str
    vehicle_type: Optional[str] = None
    vehicle_color: Optional[str] = None
    confidence_score: Optional[float] = None
    timestamp: datetime
    camera_id: Optional[str] = None
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    location_desc: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_mock_camera: bool = False
    has_snapshot: bool = False

    # relationship flags (derived, live)
    is_watchlisted: bool = False
    watchlist_category: Optional[str] = None
    alert_id: Optional[str] = None
    alert_status: Optional[str] = None
    incident_id: Optional[str] = None
    incident_number: Optional[str] = None
    case_id: Optional[str] = None
    case_number: Optional[str] = None


class VehicleSearchResponse(BaseModel):
    items: List[VehicleSearchRow]
    total: int
    limit: int
    offset: int
    sort: str
    took_ms: Optional[float] = None


class VehicleSearchQuery(BaseModel):
    """POST body for /search/vehicles -- also usable as the `params` of a
    saved search."""

    plate: Optional[str] = None                 # exact (normalised)
    plate_contains: Optional[str] = None        # partial (trigram)
    vehicle_type: Optional[str] = None
    vehicle_color: Optional[str] = None
    camera_code: Optional[str] = None
    location_contains: Optional[str] = None     # matches camera name / location_desc
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    time_from: Optional[str] = None             # "HH:MM" -- wall-clock band, applied per row
    time_to: Optional[str] = None
    # Phase 12: only events whose (camera, track) dwell time reaches this
    # many seconds -- backs the "detected for more than 5 minutes" query.
    min_duration_seconds: Optional[int] = Field(default=None, ge=1)
    unknown_only: bool = False
    watchlist_only: bool = False
    has_alert: Optional[bool] = None
    has_incident: Optional[bool] = None
    has_case: Optional[bool] = None
    min_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    source: Optional[str] = None                # "REAL" | "MOCK"
    sort: str = "latest"                        # latest|earliest|confidence|camera
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


# --- Global quick search -------------------------------------------------- #
class GlobalHit(BaseModel):
    kind: str          # VEHICLE | CAMERA | INCIDENT | CASE | ALERT | EVIDENCE
    id: str
    label: str
    sublabel: Optional[str] = None
    href: str          # frontend route


class GlobalSearchResponse(BaseModel):
    query: str
    groups: dict[str, List[GlobalHit]]
    total: int
