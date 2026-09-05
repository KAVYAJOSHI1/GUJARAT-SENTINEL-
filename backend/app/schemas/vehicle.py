"""GET /api/v1/vehicles/search response schema (contract #4 — Vehicle History).

This describes a **camera-sighting journey** (a plate observed at a sequence
of fixed cameras), NOT GPS/route tracking. `sightings` is always in
chronological ascending order.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class VehicleSighting(BaseModel):
    event_id: str
    camera_id: str
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    location_desc: Optional[str] = None
    timestamp: datetime
    latitude: Optional[float]
    longitude: Optional[float]
    has_location: bool = False
    snapshot_url: Optional[str]
    confidence_score: Optional[float]
    track_id: Optional[int] = None
    vehicle_type: Optional[str] = None
    plate_number: Optional[str] = None

    class Config:
        from_attributes = True


class VehicleJourneySummary(BaseModel):
    """Derived, entirely from the real sighting rows -- never fabricated.
    A single sighting yields `first_seen == last_seen` and
    `span_seconds == 0`; zero sightings yields all-None / 0."""
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    span_seconds: Optional[int] = None
    distinct_cameras: int = 0
    geolocated_sightings: int = 0
    vehicle_types: List[str] = []
    is_single_sighting: bool = False
    has_journey: bool = False  # >= 2 distinct geolocated sightings -> a plottable trail


class VehicleHistoryResponse(BaseModel):
    plate_number: str
    total_sightings: int
    is_watchlisted: bool
    sightings: list[VehicleSighting]
    journey: VehicleJourneySummary = VehicleJourneySummary()
