"""
anomaly_events: AI-assisted behaviour analysis results (phase brief §4).

This phase implements ONE detector -- STOPPED / LOITERING VEHICLE -- and it
works purely on stored ByteTrack `vehicle_events` (never re-processes
video). One row per (camera, track, first_seen) that crossed the
configurable duration + detection-count thresholds.

Each anomaly row optionally links to the `alerts` row it generated
(`Alert.source == ANOMALY`), so an anomaly flows through the EXISTING
alert workflow (acknowledge / assign / escalate / promote to incident)
rather than a parallel mechanism.

Every figure here is DERIVED from the real event rows; `confidence_*` is an
explicit inference marker, never presented as confirmed fact.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import (
    AnomalyKind,
    AnomalyStatus,
    ConfidenceLevel,
    TimestampMixin,
    gen_uuid,
)


class AnomalyEvent(TimestampMixin, table=True):
    __tablename__ = "anomaly_events"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)
    kind: AnomalyKind = Field(default=AnomalyKind.STOPPED_VEHICLE, nullable=False, index=True)

    camera_id: str = Field(foreign_key="cameras.id", nullable=False, index=True)
    camera_code: Optional[str] = Field(default=None, nullable=True, index=True)
    plate_number_normalized: Optional[str] = Field(default=None, nullable=True, index=True)
    track_id: Optional[int] = Field(default=None, nullable=True)

    first_seen: datetime = Field(nullable=False)
    last_seen: datetime = Field(nullable=False)
    duration_seconds: int = Field(nullable=False)
    detection_count: int = Field(nullable=False)
    displacement_meters: Optional[float] = Field(default=None, nullable=True)

    confidence_score: float = Field(nullable=False)
    confidence_level: ConfidenceLevel = Field(default=ConfidenceLevel.LOW, nullable=False)
    reasoning: Optional[str] = Field(default=None, nullable=True)

    # Phase 14 §6 -- extra detectors. All optional; STOPPED_VEHICLE leaves
    # them NULL.
    zone_name: Optional[str] = Field(default=None, nullable=True)           # RESTRICTED_ZONE
    direction_deg: Optional[float] = Field(default=None, nullable=True)     # WRONG_WAY: observed heading
    expected_direction_deg: Optional[float] = Field(default=None, nullable=True)  # WRONG_WAY: permitted heading

    # a representative vehicle_event (first sighting of the track) for evidence
    evidence_event_id: Optional[str] = Field(
        default=None, foreign_key="vehicle_events.id", nullable=True
    )
    alert_id: Optional[str] = Field(
        default=None, foreign_key="alerts.id", nullable=True, index=True
    )

    status: AnomalyStatus = Field(default=AnomalyStatus.NEW, nullable=False, index=True)
    reviewed_by_user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    reviewed_at: Optional[datetime] = Field(default=None, nullable=True)

    __table_args__ = (
        # dedup lookup: "already flagged this camera+track+start FOR THIS KIND?"
        # (Phase 14 §6: kind is in the key so one track can be both a
        # STOPPED_VEHICLE and a WRONG_WAY without colliding.)
        Index(
            "ux_anomaly_camera_track_start_kind",
            "camera_id", "track_id", "first_seen", "kind",
            unique=True,
        ),
        Index("ix_anomaly_events_status_created", "status", "created_at"),
    )
