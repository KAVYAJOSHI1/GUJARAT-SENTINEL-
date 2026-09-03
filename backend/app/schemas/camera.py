"""Camera request/response schemas, including GeoJSON Feature representations."""
from typing import Optional, Literal

from pydantic import BaseModel, Field

from app.models.base import CameraStatus


class CameraCreate(BaseModel):
    name: str
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
    name: str
    rtsp_url: Optional[str]
    location_desc: Optional[str]
    status: CameraStatus
    latitude: Optional[float]
    longitude: Optional[float]

    class Config:
        from_attributes = True


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
