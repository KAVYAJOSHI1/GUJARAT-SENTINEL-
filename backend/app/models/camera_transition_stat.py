"""
camera_transition_stats: historical travel-time baselines between camera
pairs (Phase 14 §3 -- Camera Transition Intelligence).

One row per ORDERED (from_camera, to_camera) pair that has ever been
observed as a consecutive same-plate sighting hop in `vehicle_events`.
Every figure is a plain statistic over the real event rows -- NO ML
prediction. Recomputed periodically (idempotent upsert) and on demand.

Used by:
  * VehicleCorrelationService -- the temporal-feasibility sub-score.
  * journey intelligence -- transition_classification
    (PLAUSIBLE / FAST / SLOW / IMPOSSIBLE).
  * "likely next / previous camera" lookups.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import TimestampMixin, gen_uuid


class CameraTransitionStat(TimestampMixin, table=True):
    __tablename__ = "camera_transition_stats"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)

    from_camera_id: str = Field(foreign_key="cameras.id", nullable=False, index=True)
    to_camera_id: str = Field(foreign_key="cameras.id", nullable=False, index=True)
    from_camera_code: Optional[str] = Field(default=None, nullable=True, index=True)
    to_camera_code: Optional[str] = Field(default=None, nullable=True, index=True)

    # number of consecutive same-plate hops observed for this ordered pair
    sample_count: int = Field(nullable=False, default=0)

    # travel-time statistics (seconds) over those hops
    min_seconds: Optional[int] = Field(default=None, nullable=True)
    median_seconds: Optional[int] = Field(default=None, nullable=True)
    p90_seconds: Optional[int] = Field(default=None, nullable=True)
    max_seconds: Optional[int] = Field(default=None, nullable=True)
    mean_seconds: Optional[int] = Field(default=None, nullable=True)

    # straight-line distance between the two cameras (metres), when both geolocated
    distance_meters: Optional[float] = Field(default=None, nullable=True)

    last_computed_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "ux_camera_transition_pair",
            "from_camera_id", "to_camera_id",
            unique=True,
        ),
    )
