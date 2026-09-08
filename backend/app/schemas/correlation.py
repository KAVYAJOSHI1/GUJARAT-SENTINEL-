"""Schemas for cross-camera correlation + camera transition intelligence
(Phase 14 §2, §3)."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CorrelationRequest(BaseModel):
    event_id_a: Optional[str] = None
    event_id_b: Optional[str] = None
    plate: Optional[str] = Field(default=None, description="analyse every hop for this plate")
    limit: int = Field(default=50, ge=1, le=100)


class ExpectedTravel(BaseModel):
    source: str                       # historical | distance-model | unknown
    sample_count: int
    typical_min_seconds: Optional[int] = None
    typical_max_seconds: Optional[int] = None
    median_seconds: Optional[int] = None
    hard_max_seconds: Optional[int] = None
    distance_meters: Optional[float] = None


class CorrelationBreakdown(BaseModel):
    event_id_a: str
    event_id_b: str
    from_camera_id: str
    from_camera_code: Optional[str] = None
    to_camera_id: str
    to_camera_code: Optional[str] = None
    time_diff_seconds: int
    scores: Dict[str, float]
    explanations: Dict[str, str]
    weights: Dict[str, float]
    overall_score: float
    confidence_level: str
    verdict: str                      # CONFIRMED | INFERRED
    match_method: str
    transition_classification: str    # PLAUSIBLE | FAST | SLOW | IMPOSSIBLE | UNKNOWN
    expected_travel: ExpectedTravel
    disclaimer: str


class CorrelationJourneyResponse(BaseModel):
    plate: str
    sightings: int
    hops_analyzed: int
    confirmed: int
    inferred: int
    hops: List[CorrelationBreakdown] = []


class CameraTransitionStatRead(BaseModel):
    from_camera_id: str
    from_camera_code: Optional[str] = None
    to_camera_id: str
    to_camera_code: Optional[str] = None
    sample_count: int
    min_seconds: Optional[int] = None
    median_seconds: Optional[int] = None
    p90_seconds: Optional[int] = None
    max_seconds: Optional[int] = None
    mean_seconds: Optional[int] = None
    distance_meters: Optional[float] = None
    last_computed_at: datetime

    class Config:
        from_attributes = True


class RelatedCamera(BaseModel):
    camera_id: str
    camera_code: Optional[str] = None
    observed_hops: int
    share: float
    median_seconds: Optional[int] = None


class CameraTransitionNeighbours(BaseModel):
    camera_id: str
    camera_code: Optional[str] = None
    likely_next: List[RelatedCamera] = []
    likely_previous: List[RelatedCamera] = []


class TransitionRecomputeResponse(BaseModel):
    pairs_upserted: int
    events_scanned: int
