"""
Camera registry table.
`location` is a PostGIS geometry(Point, 4326) column with a GiST spatial
index for fast bounding-box / proximity queries used by the GeoJSON API.
"""
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Column, Index
from sqlmodel import Field

from app.models.base import TimestampMixin, CameraStatus, gen_uuid


class Camera(TimestampMixin, table=True):
    __tablename__ = "cameras"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)
    name: str = Field(nullable=False, index=True)
    rtsp_url: Optional[str] = Field(default=None, nullable=True)
    status: CameraStatus = Field(default=CameraStatus.OFFLINE, nullable=False)
    location_desc: Optional[str] = Field(default=None, nullable=True)

    # PostGIS point (longitude, latitude) — SRID 4326 (WGS84)
    location: Optional[str] = Field(
        default=None,
        sa_column=Column(Geometry(geometry_type="POINT", srid=4326), nullable=True),
    )

    __table_args__ = (
        Index("ix_cameras_location_gist", "location", postgresql_using="gist"),
        Index("ix_cameras_status_btree", "status"),
    )
