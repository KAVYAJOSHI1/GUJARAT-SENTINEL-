"""
camera_health_history: an append-only log of camera effective-status
transitions (phase brief FEATURE 5).

One row is written ONLY when a camera's *effective* status actually
changes (ONLINE <-> OFFLINE <-> DEGRADED) -- either from a real health
push (ingestion.stream_health) or from the lightweight staleness watcher
in app.main. Steady state produces no rows, so this stays tiny.

This is NOT a metrics time-series (no Prometheus / per-second sampling) --
it is a transition log for "was this camera down, and when".
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import CameraStatus, TimestampMixin, gen_uuid


class CameraHealthHistory(TimestampMixin, table=True):
    __tablename__ = "camera_health_history"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)
    camera_id: str = Field(foreign_key="cameras.id", nullable=False, index=True)

    # effective status AFTER this transition, and what it was before
    status: CameraStatus = Field(nullable=False)
    previous_status: Optional[CameraStatus] = Field(default=None, nullable=True)

    # telemetry snapshot at the moment of transition (all optional -- a
    # staleness-driven transition has no fresh push to read)
    stream_fps: Optional[float] = Field(default=None, nullable=True)
    reconnect_count: Optional[int] = Field(default=None, nullable=True)
    last_frame_age_seconds: Optional[float] = Field(default=None, nullable=True)

    # what caused the row: "health_push" | "staleness_watcher" | "manual"
    source: str = Field(default="health_push", nullable=False)
    detected_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_camera_health_history_cam_time", "camera_id", "detected_at"),
    )
