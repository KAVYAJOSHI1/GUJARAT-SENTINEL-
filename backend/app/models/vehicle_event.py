"""
vehicle_events: every AI detection logged from Kavya's ANPR/YOLO pipeline.
B-Tree indexes on (plate_number) and (timestamp) satisfy the <50ms
trajectory search requirement at 100k+ rows; a GiST index on the derived
point geometry backs spatial trajectory queries.
"""
from datetime import datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Column, Index, Float
from sqlmodel import Field

from app.models.base import TimestampMixin, gen_uuid


class VehicleEvent(TimestampMixin, table=True):
    __tablename__ = "vehicle_events"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)
    plate_number: str = Field(nullable=False, index=True)
    plate_number_normalized: str = Field(nullable=False, index=True)

    camera_id: str = Field(foreign_key="cameras.id", nullable=False, index=True)
    # Raw external camera id from the AI event, kept for traceability even
    # after camera_id has been resolved to the cameras.id UUID.
    camera_code: Optional[str] = Field(default=None, nullable=True, index=True)
    timestamp: datetime = Field(nullable=False, index=True)

    # Persistent per-camera ByteTrack id for this sighting.
    track_id: Optional[int] = Field(default=None, nullable=True, index=True)

    vehicle_type: Optional[str] = Field(default=None, nullable=True)
    vehicle_color: Optional[str] = Field(default=None, nullable=True)
    confidence_score: Optional[float] = Field(default=None, sa_column=Column(Float))

    # Object storage reference only — never store raw binary in Postgres.
    snapshot_url: Optional[str] = Field(default=None, nullable=True)

    latitude: Optional[float] = Field(default=None, sa_column=Column(Float))
    longitude: Optional[float] = Field(default=None, sa_column=Column(Float))

    location: Optional[str] = Field(
        default=None,
        sa_column=Column(Geometry(geometry_type="POINT", srid=4326), nullable=True),
    )

    __table_args__ = (
        Index("ix_vehicle_events_plate_btree", "plate_number_normalized"),
        Index("ix_vehicle_events_timestamp_btree", "timestamp"),
        Index(
            "ix_vehicle_events_plate_ts_composite",
            "plate_number_normalized",
            "timestamp",
        ),
        Index("ix_vehicle_events_location_gist", "location", postgresql_using="gist"),
    )
