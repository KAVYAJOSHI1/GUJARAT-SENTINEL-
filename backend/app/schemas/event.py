"""
Canonical AI-detection event contract  (POST /api/v1/events/ai-detection).

ONE schema. It matches the payload ``ai/pipeline.py`` actually emits
(nested ``vehicle`` / ``license_plate`` / ``evidence`` blocks) and also
accepts the older flat form (top-level ``plate_number`` / ``vehicle_type`` /
``confidence_score``) so nothing that already speaks to this endpoint breaks.

Fields the pipeline is expected to supply:
  event_id, camera_id (external code or UUID), timestamp, track_id,
  vehicle.type/class, vehicle.bbox, license_plate.plate_number/text,
  license_plate.confidence, evidence.frame_snapshot_path (or snapshot_base64).
"""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class VehicleBlock(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    type: Optional[str] = None
    vehicle_class: Optional[str] = Field(default=None, alias="class")
    confidence: Optional[float] = None
    bbox: Optional[List[float]] = None
    track_id: Optional[int] = None


class LicensePlateBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plate_detected: Optional[bool] = None
    plate_number: Optional[str] = None
    text: Optional[str] = None
    confidence: Optional[float] = None
    raw_text: Optional[str] = None


class EvidenceBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    frame_snapshot_path: Optional[str] = None
    frame_path: Optional[str] = None
    plate_crop_path: Optional[str] = None
    snapshot_url: Optional[str] = None


class AIDetectionEventIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: Optional[str] = None
    camera_id: str                       # external code ("cam04") OR cameras.id UUID
    camera_name: Optional[str] = None
    timestamp: datetime
    pts: Optional[float] = None
    track_id: Optional[int] = None

    vehicle: Optional[VehicleBlock] = None
    license_plate: Optional[LicensePlateBlock] = None
    evidence: Optional[EvidenceBlock] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Optional inline snapshot -> uploaded to object storage.
    snapshot_base64: Optional[str] = None
    snapshot_content_type: str = "image/jpeg"

    # --- flat-form fallbacks (older callers) ---
    plate_number: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_color: Optional[str] = None
    confidence_score: Optional[float] = None

    # ---- resolved accessors -------------------------------------------------
    def resolved_plate(self) -> str:
        for cand in (
            self.plate_number,
            self.license_plate.plate_number if self.license_plate else None,
            self.license_plate.text if self.license_plate else None,
        ):
            if cand and str(cand).strip():
                return str(cand).strip()
        return "UNKNOWN"

    def resolved_track_id(self) -> Optional[int]:
        if self.track_id is not None:
            return self.track_id
        if self.vehicle and self.vehicle.track_id is not None:
            return self.vehicle.track_id
        return None

    def resolved_vehicle_type(self) -> Optional[str]:
        if self.vehicle and (self.vehicle.type or self.vehicle.vehicle_class):
            return self.vehicle.type or self.vehicle.vehicle_class
        return self.vehicle_type

    def resolved_confidence(self) -> Optional[float]:
        if self.confidence_score is not None:
            return self.confidence_score
        if self.license_plate and self.license_plate.confidence is not None:
            return self.license_plate.confidence
        if self.vehicle and self.vehicle.confidence is not None:
            return self.vehicle.confidence
        return None

    def resolved_snapshot_ref(self) -> Optional[str]:
        if not self.evidence:
            return None
        return (
            self.evidence.snapshot_url
            or self.evidence.frame_snapshot_path
            or self.evidence.frame_path
        )

    def bbox(self) -> Optional[List[float]]:
        return self.vehicle.bbox if self.vehicle else None


class AIDetectionEventOut(BaseModel):
    id: str
    event_id: Optional[str] = None
    camera_id: str
    camera_code: Optional[str] = None
    track_id: Optional[int] = None
    plate_number: str
    plate_number_normalized: str
    timestamp: datetime
    snapshot_url: Optional[str] = None
    watchlist_match: bool
    alert_id: Optional[str] = None
    alert_suppressed_by_cooldown: bool = False

    model_config = ConfigDict(from_attributes=True)
