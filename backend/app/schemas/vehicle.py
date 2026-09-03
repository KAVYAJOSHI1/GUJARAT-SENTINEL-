"""GET /api/v1/vehicles/search response schema (contract #4 — Vehicle History)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class VehicleSighting(BaseModel):
    event_id: str
    camera_id: str
    camera_name: Optional[str] = None
    timestamp: datetime
    latitude: Optional[float]
    longitude: Optional[float]
    snapshot_url: Optional[str]
    confidence_score: Optional[float]

    class Config:
        from_attributes = True


class VehicleHistoryResponse(BaseModel):
    plate_number: str
    total_sightings: int
    is_watchlisted: bool
    sightings: list[VehicleSighting]
