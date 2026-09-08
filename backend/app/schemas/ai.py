"""Phase 12 — AI intelligence layer request/response schemas."""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.models.base import AnomalyKind, AnomalyStatus, ConfidenceLevel


# --------------------------------------------------------------------------- #
#  Copilot                                                                    #
# --------------------------------------------------------------------------- #
class CopilotRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class ParsedQuery(BaseModel):
    """The deterministic interpretation of a natural-language question --
    always shown to the officer so the AI stays explainable."""

    intent: str
    plate: Optional[str] = None
    camera_codes: List[str] = []
    vehicle_type: Optional[str] = None
    vehicle_color: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    time_from: Optional[str] = None       # "HH:MM"
    time_to: Optional[str] = None
    relative_window: Optional[str] = None  # human phrase, e.g. "last 6 hours"
    watchlist_only: bool = False
    unknown_only: bool = False
    min_duration_seconds: Optional[int] = None
    notes: List[str] = []                 # what the parser could / couldn't resolve


class TimelineItem(BaseModel):
    timestamp: datetime
    label: str
    camera_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    ref_kind: Optional[str] = None
    ref_id: Optional[str] = None


class MapPoint(BaseModel):
    latitude: float
    longitude: float
    label: str
    camera_code: Optional[str] = None
    timestamp: Optional[datetime] = None


class RelatedRef(BaseModel):
    kind: str            # ALERT | INCIDENT | CASE | EVIDENCE | CAMERA
    id: str
    label: str
    href: str


class CopilotResponse(BaseModel):
    query: str
    provider: str                       # "deterministic" | "openai"
    intent: str
    parsed: ParsedQuery
    tool_calls: List[dict] = []          # {tool, params} — what was actually run
    answer: str                         # human-readable, grounded in results
    result_count: int
    results: List[dict] = []            # raw structured rows (from existing APIs)
    timeline: List[TimelineItem] = []
    map_points: List[MapPoint] = []
    related: List[RelatedRef] = []
    confidence_score: float
    confidence_level: ConfidenceLevel
    match_method: Optional[str] = None
    limitations: List[str] = []
    generated_at: datetime


# --------------------------------------------------------------------------- #
#  NL search                                                                  #
# --------------------------------------------------------------------------- #
class AISearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class AISearchResponse(BaseModel):
    query: str
    parsed: ParsedQuery
    filters: dict                       # the exact VehicleSearchQuery sent to /search/vehicles
    search: Any                         # VehicleSearchResponse
    limitations: List[str] = []


# --------------------------------------------------------------------------- #
#  AI summary (incident / case)                                               #
# --------------------------------------------------------------------------- #
class SummarySection(BaseModel):
    label: str
    value: str
    is_fact: bool = True                # True = straight from data; False = inference


class AISummaryResponse(BaseModel):
    subject_kind: str                   # "incident" | "case"
    subject_id: str
    subject_ref: str                    # INC-.. / CASE-..
    provider: str
    headline: str                       # the prose summary
    sections: List[SummarySection] = []
    investigation_gaps: List[str] = []
    confidence_level: ConfidenceLevel
    disclaimer: str = "AI-GENERATED SUMMARY — based on recorded Sentinel data."
    generated_at: datetime


# --------------------------------------------------------------------------- #
#  Anomaly events                                                             #
# --------------------------------------------------------------------------- #
class AnomalyEventRead(BaseModel):
    id: str
    kind: AnomalyKind
    camera_id: str
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    location_desc: Optional[str] = None
    plate_number_normalized: Optional[str] = None
    track_id: Optional[int] = None
    first_seen: datetime
    last_seen: datetime
    duration_seconds: int
    detection_count: int
    displacement_meters: Optional[float] = None
    confidence_score: float
    confidence_level: ConfidenceLevel
    reasoning: Optional[str] = None
    evidence_event_id: Optional[str] = None
    alert_id: Optional[str] = None
    status: AnomalyStatus
    reviewed_by_username: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AnomalyPage(BaseModel):
    items: List[AnomalyEventRead]
    total: int
    limit: int
    offset: int


class AnomalyScanRequest(BaseModel):
    lookback_hours: Optional[int] = Field(default=None, ge=1, le=24 * 30)
    camera_code: Optional[str] = None


class AnomalyScanResult(BaseModel):
    scanned_tracks: int
    created: int
    already_flagged: int
    anomalies: List[AnomalyEventRead] = []


class AnomalyReviewRequest(BaseModel):
    status: AnomalyStatus


class AIStatus(BaseModel):
    provider: str
    llm_available: bool
    deterministic_always_on: bool = True
    anomaly_scan_enabled: bool
    anomaly_thresholds: dict
    max_results: int
