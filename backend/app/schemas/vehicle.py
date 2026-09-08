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
    vehicle_color: Optional[str] = None
    plate_number: Optional[str] = None
    # Phase 15B: explicit ANPR outcome for this sighting.
    anpr_status: str = "OK"
    anpr_failure_reason: Optional[str] = None
    anpr_quality_score: Optional[float] = None
    # Phase 13: REAL government camera vs a local MOCK/demo feed. Derived
    # from the camera code prefix (never labels a real feed as mock).
    is_mock: bool = False
    # Phase 16: honest provenance -- DEMO (seeded data) > MOCK (local stream)
    # > REAL (government feed). Never labels seeded/demo data as REAL.
    feed_source: str = "REAL"
    # A directly OBSERVED sighting is always a CONFIRMED fact.
    kind: str = "CONFIRMED"

    class Config:
        from_attributes = True


class JourneyTransition(BaseModel):
    """An INFERRED camera-to-camera movement between two consecutive
    sightings. The sightings are facts; the movement between them was not
    observed -- so `kind` is always INFERRED and distance/speed are only
    populated when both cameras are geolocated."""
    from_camera_id: str
    from_camera_code: Optional[str] = None
    to_camera_id: str
    to_camera_code: Optional[str] = None
    from_timestamp: datetime
    to_timestamp: datetime
    time_diff_seconds: int
    distance_meters: Optional[float] = None
    estimated_speed_kmh: Optional[float] = None
    kind: str = "INFERRED"
    confidence_level: str = "MEDIUM"     # HIGH | MEDIUM | LOW
    match_method: str = "consecutive exact-plate sightings; movement inferred, not observed"
    notes: List[str] = []
    # Phase 14 §3: how the observed gap compares to the historical /
    # distance-model travel band for this camera pair. One of
    # PLAUSIBLE / FAST / SLOW / IMPOSSIBLE / UNKNOWN (None if not computed).
    transition_classification: Optional[str] = None
    expected_travel_band: Optional[str] = None


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
    # Phase 13: derived camera-to-camera transitions (see JourneyTransition).
    transitions: List[JourneyTransition] = []
    confirmed_sightings: int = 0
    inferred_transitions: int = 0


class VehicleHistoryResponse(BaseModel):
    plate_number: str
    total_sightings: int
    is_watchlisted: bool
    sightings: list[VehicleSighting]
    journey: VehicleJourneySummary = VehicleJourneySummary()


class CameraSeen(BaseModel):
    camera_id: str
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    location_desc: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sightings: int
    first_seen: datetime
    last_seen: datetime


class RelatedRecord(BaseModel):
    kind: str            # ALERT | INCIDENT | CASE
    id: str
    label: str
    status: Optional[str] = None
    href: str


class VehicleProfile(BaseModel):
    """Phase 15D -- the consolidated view opened from a search result.
    Everything derived live from persisted rows."""
    plate: str
    total_sightings: int
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    distinct_cameras: int = 0
    geolocated_sightings: int = 0
    vehicle_types: List[str] = []
    vehicle_colors: List[str] = []
    is_watchlisted: bool = False
    watchlist_category: Optional[str] = None
    cameras: List[CameraSeen] = []
    journey: VehicleJourneySummary = VehicleJourneySummary()
    # ANPR quality breakdown for this plate's sightings
    anpr_readable: int = 0
    anpr_unknown: int = 0
    anpr_failure_reasons: dict = {}
    # relationship counts + refs
    counts: dict = {}
    related: List[RelatedRecord] = []
    visual_match_count: int = 0
