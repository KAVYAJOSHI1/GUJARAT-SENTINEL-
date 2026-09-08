"""Schemas for the Vehicle Visual Re-ID API (Phase 14 §1)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ReIDSearchRequest(BaseModel):
    event_id: Optional[str] = Field(default=None, description="sighting to match against")
    plate: Optional[str] = Field(default=None, description="use this plate's most recent sighting")
    limit: int = Field(default=20, ge=1, le=100)
    time_window_hours: Optional[int] = Field(default=None, ge=1, le=24 * 30)
    exclude_same_plate: bool = False
    exclude_same_camera: bool = False
    min_similarity: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SimilarVehicle(BaseModel):
    event_id: str
    plate_number_normalized: str
    camera_id: str
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    track_id: Optional[int] = None
    timestamp: datetime
    vehicle_type: Optional[str] = None
    vehicle_color: Optional[str] = None
    similarity: float
    similarity_pct: float
    band: str                       # STRONG | MODERATE | WEAK | NONE
    confidence_level: str           # HIGH | MEDIUM | LOW | INSUFFICIENT (capped at MEDIUM)
    same_plate: bool
    verdict: str                    # "VISUAL MATCH" | "PLATE MATCH"


class ReIDSearchResponse(BaseModel):
    query_event_id: Optional[str] = None
    query_plate: Optional[str] = None
    query_vehicle_type: Optional[str] = None
    query_vehicle_color: Optional[str] = None
    model_name: str
    scanned: int
    returned: int
    candidates: List[SimilarVehicle] = []
    disclaimer: str


class ReIDCompareRequest(BaseModel):
    event_id_a: str
    event_id_b: str


class ReIDCompareResponse(BaseModel):
    event_id_a: str
    event_id_b: str
    similarity: float
    similarity_pct: float
    band: str
    confidence_level: str
    same_plate: bool
    model_name: str
    note: str


class EmbeddingInfo(BaseModel):
    vehicle_event_id: str
    plate_number_normalized: str
    camera_code: Optional[str] = None
    timestamp: datetime
    vehicle_type: Optional[str] = None
    vehicle_color: Optional[str] = None
    dim: int
    model_name: str
    source: str


class ReIDBackfillResponse(BaseModel):
    scanned: int
    indexed: int
