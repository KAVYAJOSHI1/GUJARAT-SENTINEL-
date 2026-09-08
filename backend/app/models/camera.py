"""
Camera registry table.
`location` is a PostGIS geometry(Point, 4326) column with a GiST spatial
index for fast bounding-box / proximity queries used by the GeoJSON API.
"""
from datetime import datetime
from typing import List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import JSON, Column, Index
from sqlmodel import Field

from app.models.base import TimestampMixin, CameraStatus, gen_uuid


class Camera(TimestampMixin, table=True):
    __tablename__ = "cameras"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)
    # Stable external / Sentinel-catalogue identifier, e.g. "cam04". This is what
    # the AI pipeline puts in its events; the backend resolves it to `id`.
    code: Optional[str] = Field(default=None, index=True, unique=True)
    name: str = Field(nullable=False, index=True)
    rtsp_url: Optional[str] = Field(default=None, nullable=True)
    # Last-known status. For a camera actively reporting stream health (see
    # `health_updated_at` below), the API layer (cameras.py) overrides what it
    # SERVES with a freshness-checked "effective" status computed from these
    # fields -- this column is what the last health push (or manual
    # PATCH/onboard) set it to, not necessarily what's returned to clients.
    status: CameraStatus = Field(default=CameraStatus.OFFLINE, nullable=False)
    location_desc: Optional[str] = Field(default=None, nullable=True)

    # --- Stream health, pushed by ingestion.stream_health.HealthRegistry via
    # POST /api/v1/cameras/health (see cameras.py::push_camera_health).
    # SENTINEL_System_Audit_Report.md §11/§15: HealthRegistry had real FPS/
    # drop/reconnect telemetry that never reached this table, so the
    # dashboard's ONLINE/OFFLINE badge came only from whatever this column
    # was set to at onboard time. These four columns close that gap.
    stream_fps: Optional[float] = Field(default=None, nullable=True)
    frame_drop_count: Optional[int] = Field(default=None, nullable=True)
    reconnect_count: Optional[int] = Field(default=None, nullable=True)

    # --- Phase 14 §6: behaviour-analytics configuration (all optional) ---
    # Compass bearing (degrees, 0 = N, 90 = E) the traffic at this camera is
    # PERMITTED to flow. A track moving consistently opposite -> WRONG_WAY.
    permitted_direction_deg: Optional[float] = Field(default=None, nullable=True)
    # List of restricted polygons: [{"name": str, "points": [[lat, lon], ...]}].
    # A tracked vehicle whose sighting falls inside one -> RESTRICTED_ZONE.
    restricted_zones: Optional[List[dict]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    # Server-side receipt time of the last health push -- used to detect a
    # stalled/dead ingestion worker (stale health) even if the last status it
    # ever reported was ONLINE.
    health_updated_at: Optional[datetime] = Field(default=None, nullable=True)

    # PostGIS point (longitude, latitude) — SRID 4326 (WGS84).
    # spatial_index=False: the explicit ix_cameras_location_gist below is the
    # single GiST index; GeoAlchemy2's auto idx_cameras_location duplicate is
    # dropped in migration 0004.
    location: Optional[str] = Field(
        default=None,
        sa_column=Column(
            Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
    )

    __table_args__ = (
        Index("ix_cameras_location_gist", "location", postgresql_using="gist"),
        Index("ix_cameras_status_btree", "status"),
    )
