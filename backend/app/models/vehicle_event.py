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
    # Raw (pre-normalisation) plate string is stored for traceability but is
    # NEVER filtered on -- every lookup uses plate_number_normalized. No
    # index (the production migrations never created one either).
    plate_number: str = Field(nullable=False)
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

    # Phase 15B: explicit ANPR outcome. `anpr_status` is "OK" for a
    # recognised plate, "UNKNOWN" otherwise; `anpr_failure_reason` is one of
    # NO_PLATE / LOW_RESOLUTION / BLUR / OCCLUDED / OCR_DISAGREEMENT /
    # INVALID_FORMAT / LOW_CONFIDENCE when the read failed (NULL / "NONE" on
    # success). `anpr_quality_score` (0-1) is the crop-quality composite;
    # `plate_quality` (0-1) is the plate-locator confidence.
    anpr_status: str = Field(default="OK", nullable=False, index=True)
    anpr_failure_reason: Optional[str] = Field(default=None, nullable=True, index=True)
    anpr_quality_score: Optional[float] = Field(default=None, sa_column=Column(Float))
    plate_quality: Optional[float] = Field(default=None, sa_column=Column(Float))

    # Object storage reference only — never store raw binary in Postgres.
    snapshot_url: Optional[str] = Field(default=None, nullable=True)

    latitude: Optional[float] = Field(default=None, sa_column=Column(Float))
    longitude: Optional[float] = Field(default=None, sa_column=Column(Float))

    location: Optional[str] = Field(
        default=None,
        # spatial_index=False: GeoAlchemy2 otherwise auto-creates a second
        # GiST index (idx_vehicle_events_location) identical to the explicit
        # ix_vehicle_events_location_gist below -- see migration 0004.
        sa_column=Column(
            Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
    )

    __table_args__ = (
        # --- plate search / journey (WHERE plate = ? ORDER BY timestamp) ---
        Index(
            "ix_vehicle_events_plate_ts_composite",
            "plate_number_normalized",
            "timestamp",
        ),
        # --- dashboard event feed (ORDER BY timestamp DESC LIMIT n) + the
        #     retention timestamp < cutoff scan ---
        Index("ix_vehicle_events_timestamp_btree", "timestamp"),
        Index("ix_vehicle_events_plate_btree", "plate_number_normalized"),
        # --- Phase 6: covering indexes for the windowed analytics group-bys
        #     (index-only scans, no heap fetch) -- benchmark in
        #     scripts/db_benchmark.py + README "Database Scalability" ---
        Index("ix_ve_ts_plate", "timestamp", "plate_number_normalized"),
        Index("ix_ve_ts_camera_code", "timestamp", "camera_code"),
        Index("ix_ve_vehicle_type", "vehicle_type"),
        # roadmap: proximity search (no spatial predicate query today)
        Index("ix_vehicle_events_location_gist", "location", postgresql_using="gist"),
    )
