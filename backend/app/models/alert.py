"""
alerts: generated whenever the watchlist engine confirms a match outside
the cooldown window. Indexed on (plate_number, camera_id, created_at) to
make cooldown lookups ("same plate + camera within last 300s?") fast.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import (
    AlertSource,
    AlertStatus,
    PriorityLevel,
    TimestampMixin,
    gen_uuid,
)


class Alert(TimestampMixin, table=True):
    __tablename__ = "alerts"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)

    plate_number: str = Field(nullable=False, index=True)
    plate_number_normalized: str = Field(nullable=False, index=True)

    camera_id: str = Field(foreign_key="cameras.id", nullable=False, index=True)
    vehicle_event_id: str = Field(
        foreign_key="vehicle_events.id", nullable=False, index=True
    )
    # Phase 12: nullable. A WATCHLIST alert always has one (the engine sets
    # it); an ANOMALY alert has none. The watchlist->alert path is unchanged.
    watchlist_id: Optional[str] = Field(
        default=None, foreign_key="watchlist.id", nullable=True, index=True
    )
    source: AlertSource = Field(default=AlertSource.WATCHLIST, nullable=False, index=True)
    anomaly_event_id: Optional[str] = Field(
        default=None, foreign_key="anomaly_events.id", nullable=True, index=True
    )

    priority_level: PriorityLevel = Field(default=PriorityLevel.MEDIUM, nullable=False)
    status: AlertStatus = Field(default=AlertStatus.NEW, nullable=False, index=True)

    acknowledged_by_user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    # Phase 11: escalation workflow. The watchlist engine never sets any of
    # these -- they are only ever written by the alert-workflow API.
    assigned_to_user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", nullable=True, index=True
    )
    escalated_by_user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    escalated_at: Optional[datetime] = Field(default=None, nullable=True)
    escalation_reason: Optional[str] = Field(default=None, nullable=True)
    resolved_by_user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    resolved_at: Optional[datetime] = Field(default=None, nullable=True)

    snapshot_url: Optional[str] = Field(default=None, nullable=True)

    __table_args__ = (
        Index(
            "ix_alerts_plate_camera_created_composite",
            "plate_number_normalized",
            "camera_id",
            "created_at",
        ),
        Index("ix_alerts_status_btree", "status"),
    )
