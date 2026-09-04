"""Schemas for POST /api/v1/events/ai-detection (contract #2 — AI Event Object)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AIDetectionEventIn(BaseModel):
    """Payload posted by Kavya's ANPR/YOLO pipeline."""

    camera_id: str
    plate_number: str
    timestamp: datetime
    vehicle_type: Optional[str] = None
    vehicle_color: Optional[str] = None
    confidence_score: Optional[float] = Field(default=None, ge=0, le=1)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Base64-encoded snapshot JPEG/PNG; optional — event still persists without it.
    snapshot_base64: Optional[str] = None
    snapshot_content_type: str = "image/jpeg"


class AIDetectionEventOut(BaseModel):
    id: str
    camera_id: str
    plate_number: str
    plate_number_normalized: str
    timestamp: datetime
    snapshot_url: Optional[str]
    watchlist_match: bool
    alert_id: Optional[str] = None

    class Config:
        from_attributes = True
