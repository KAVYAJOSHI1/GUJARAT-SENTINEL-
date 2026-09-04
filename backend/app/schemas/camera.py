"""Camera request/response schemas, including GeoJSON Feature representations."""
from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import CameraStatus


class CameraCreate(BaseModel):
    name: str
    code: Optional[str] = None
    rtsp_url: Optional[str] = None
    location_desc: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    status: CameraStatus = CameraStatus.OFFLINE


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    location_desc: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: Optional[CameraStatus] = None


class CameraRead(BaseModel):
    id: str
    code: Optional[str] = None
    name: str
    rtsp_url: Optional[str]
    location_desc: Optional[str]
    status: CameraStatus
    latitude: Optional[float]
    longitude: Optional[float]

    class Config:
        from_attributes = True


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
