"""Camera health history schema (FEATURE 5)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.models.base import CameraStatus


class CameraHealthHistoryRow(BaseModel):
    id: str
    camera_id: str
    status: CameraStatus
    previous_status: Optional[CameraStatus] = None
    stream_fps: Optional[float] = None
    reconnect_count: Optional[int] = None
    last_frame_age_seconds: Optional[float] = None
    source: str
    detected_at: datetime

    class Config:
        from_attributes = True


class CameraHealthHistoryResponse(BaseModel):
    camera_id: str
    camera_code: Optional[str] = None
    current_status: CameraStatus
    health_updated_at: Optional[datetime] = None
    transitions: List[CameraHealthHistoryRow]
    total: int
