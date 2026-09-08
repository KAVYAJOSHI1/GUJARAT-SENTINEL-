"""Schemas for Camera Reliability Intelligence (Phase 14 §9)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class HealthTransition(BaseModel):
    status: str
    previous_status: Optional[str] = None
    source: str
    detected_at: datetime
    stream_fps: Optional[float] = None


class CameraReliability(BaseModel):
    camera_id: str
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    location_desc: Optional[str] = None
    current_status: str
    health_score: Optional[float] = None            # 0-100, None if never reported
    reliability_score: str                          # HIGH | MEDIUM | LOW | UNKNOWN
    degradation_indicator: bool
    window_hours: int
    disconnect_count: int
    mean_recovery_seconds: Optional[float] = None
    heartbeat_stale: bool
    stream_fps: Optional[float] = None
    fps_degraded: bool
    reconnect_count: int
    detection_rate_per_hour: float
    detection_rate_change_pct: Optional[float] = None
    observations: List[str] = []
    # Phase 15F -- video quality (separate axis from reliability/uptime)
    video_quality_score: Optional[float] = None
    video_quality_label: str = "UNKNOWN"
    video_quality_reasons: List[str] = []
    anpr_success_rate: Optional[float] = None
    mean_plate_quality: Optional[float] = None
    mean_anpr_quality: Optional[float] = None
    transitions: Optional[List[HealthTransition]] = None


class CameraIntelligenceResponse(BaseModel):
    generated_at: datetime
    window_hours: int
    camera_count: int
    degraded_count: int
    poor_video_count: int = 0
    cameras: List[CameraReliability] = []
    note: str
