"""AI-pipeline status push/read schemas (POST/GET /api/v1/pipeline/status)."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class _LatencyBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None


class PipelineStatusPush(BaseModel):
    """What scripts/run_pipeline_service.py POSTs. It's deliberately tolerant:
    the pipeline can send a subset, and unknown extra keys are ignored. Every
    field is optional -- a missing value stays NULL, it is never defaulted to
    a fake 0."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    service_id: str = "default"
    num_workers: Optional[int] = None
    processed_frames: Optional[int] = None
    processed_fps: Optional[float] = None
    vehicles_detected: Optional[int] = Field(default=None, alias="total_vehicles_detected")
    events_generated: Optional[int] = Field(default=None, alias="total_ai_events_generated")
    events_delivered: Optional[int] = Field(default=None, alias="events_sent_ok")
    events_dropped: Optional[int] = None
    event_queue_depth: Optional[int] = None
    event_queue_max_depth: Optional[int] = None
    yolo_latency_ms: Optional[_LatencyBlock] = None
    ocr_latency_ms: Optional[_LatencyBlock] = None
    cpu_percent: Optional[float] = None
    rss_mb: Optional[float] = None
    frames_by_camera: Optional[dict[str, int]] = None
    events_by_camera: Optional[dict[str, int]] = None


class PipelineStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_id: str
    reported_at: datetime
    age_seconds: Optional[float] = None
    num_workers: Optional[int] = None
    processed_frames: Optional[int] = None
    processed_fps: Optional[float] = None
    vehicles_detected: Optional[int] = None
    events_generated: Optional[int] = None
    events_delivered: Optional[int] = None
    events_dropped: Optional[int] = None
    event_queue_depth: Optional[int] = None
    event_queue_max_depth: Optional[int] = None
    yolo_p50_ms: Optional[float] = None
    yolo_p95_ms: Optional[float] = None
    ocr_p50_ms: Optional[float] = None
    ocr_p95_ms: Optional[float] = None
    cpu_percent: Optional[float] = None
    rss_mb: Optional[float] = None
    cameras_processing: Optional[int] = None
    detail: Optional[dict[str, Any]] = None
