"""Camera request/response schemas, including GeoJSON Feature representations."""
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import CameraStatus


class CameraCreate(BaseModel):
    name: str
    code: Optional[str] = None
    rtsp_url: Optional[str] = None
    hls_url: Optional[str] = None
    webrtc_url: Optional[str] = None
    location_desc: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    status: CameraStatus = CameraStatus.OFFLINE


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    hls_url: Optional[str] = None
    webrtc_url: Optional[str] = None
    location_desc: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: Optional[CameraStatus] = None


class CameraStreamSource(BaseModel):
    kind: str            # webrtc | hls | recorded | snapshot
    url: str
    realtime: bool
    label: str


class CameraStreamProfile(BaseModel):
    camera_id: str
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    location_desc: Optional[str] = None
    is_mock: bool
    is_demo: bool = False
    feed_source: str = "REAL"
    effective_status: str
    mode: str            # LIVE | DEGRADED | RECORDED | OFFLINE
    mode_reasons: list[str] = []
    sources: list[CameraStreamSource] = []
    primary_source: Optional[str] = None
    stream_fps: Optional[float] = None
    last_frame_at: Optional[datetime] = None
    last_detection_at: Optional[datetime] = None
    ai_status: str
    reconnect_count: Optional[int] = None
    note: str


class RestrictedZone(BaseModel):
    name: str
    # polygon ring as [[lat, lon], ...] (>= 3 points)
    points: list[list[float]] = Field(..., min_length=3)


class CameraBehaviorConfig(BaseModel):
    """Phase 14 §6 -- wrong-way + restricted-zone detector configuration.
    Send `permitted_direction_deg: null` / `restricted_zones: []` to clear."""
    permitted_direction_deg: Optional[float] = Field(default=None, ge=0, le=360)
    restricted_zones: Optional[list[RestrictedZone]] = None


class CameraRead(BaseModel):
    id: str
    code: Optional[str] = None
    name: str
    rtsp_url: Optional[str]
    hls_url: Optional[str] = None
    webrtc_url: Optional[str] = None
    location_desc: Optional[str]
    # `status` here is the freshness-checked EFFECTIVE status (see
    # cameras.py::_effective_status) -- derived from actual stream health
    # when available, not just the raw last-written DB column.
    status: CameraStatus
    latitude: Optional[float]
    longitude: Optional[float]
    # Real stream-health telemetry (ingestion.stream_health.HealthRegistry ->
    # POST /cameras/health), None until at least one health push has landed
    # for this camera.
    fps: Optional[float] = None
    frame_drop_count: Optional[int] = None
    reconnect_count: Optional[int] = None
    health_updated_at: Optional[datetime] = None
    # Phase 13: REAL government camera vs a local MOCK/demo feed (code prefix).
    is_mock: bool = False
    is_demo: bool = False
    # Phase 15H §12: DEMO | MOCK | REAL -- derived, badged explicitly in the UI.
    feed_source: str = "REAL"
    # timestamp of the most recent vehicle_event on this camera (list view only).
    last_detection_at: Optional[datetime] = None
    # Phase 14 §6: behaviour-analytics config.
    permitted_direction_deg: Optional[float] = None
    restricted_zones: Optional[list] = None

    class Config:
        from_attributes = True


class CameraHealthEntry(BaseModel):
    """One camera's telemetry snapshot, matching
    ingestion.stream_health.StreamMetrics field-for-field (camera_id is the
    external `cameras.code`, e.g. "cam04" / "MOCK_CAM01")."""
    camera_id: str
    status: Literal["ONLINE", "OFFLINE", "RECONNECTING"]
    fps: Optional[float] = None
    pts_jitter_ms: Optional[float] = None
    frame_drop_count: Optional[int] = None
    reconnect_count: Optional[int] = None
    last_error: Optional[str] = None


class CameraHealthPush(BaseModel):
    streams: list[CameraHealthEntry]


class CameraHealthResult(BaseModel):
    updated: int
    skipped: list[str]  # camera_ids that don't resolve to a known camera yet


class CameraRegistryEntry(BaseModel):
    """One row of a camera catalogue / registry sync payload."""
    model_config = ConfigDict(extra="ignore")
    code: Optional[str] = None
    camera_id: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    stream_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    resolved_address: Optional[str] = None
    location_desc: Optional[str] = None
    status: Optional[str] = None


class CameraSyncResult(BaseModel):
    synced: int
    cameras: list[CameraRead]


class GeoJSONPointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # [lon, lat]


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: GeoJSONPointGeometry
    properties: dict


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature]
