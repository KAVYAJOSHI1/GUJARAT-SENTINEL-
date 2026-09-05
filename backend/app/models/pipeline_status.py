"""
pipeline_status: the latest self-reported metrics snapshot from the AI
pipeline service (scripts/run_pipeline_service.py). One row per running
service, keyed by `service_id` (default "default").

This is the AI-pipeline analogue of the per-camera health push
(cameras.health_updated_at + stream_fps + ...): the backend can't observe
YOLO/OCR/queue internals directly, so the pipeline POSTs a snapshot of
`AIPipeline.get_metrics()` here every few seconds and the dashboard reads
it back. Every value is either a real measurement or NULL -- never a
placeholder.
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class PipelineStatus(SQLModel, table=True):
    __tablename__ = "pipeline_status"

    service_id: str = Field(default="default", primary_key=True)
    reported_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    # scalar metrics lifted out for cheap querying / display
    num_workers: Optional[int] = Field(default=None)
    processed_frames: Optional[int] = Field(default=None)
    processed_fps: Optional[float] = Field(default=None)
    vehicles_detected: Optional[int] = Field(default=None)
    events_generated: Optional[int] = Field(default=None)
    events_delivered: Optional[int] = Field(default=None)
    events_dropped: Optional[int] = Field(default=None)
    event_queue_depth: Optional[int] = Field(default=None)
    event_queue_max_depth: Optional[int] = Field(default=None)
    yolo_p50_ms: Optional[float] = Field(default=None)
    yolo_p95_ms: Optional[float] = Field(default=None)
    ocr_p50_ms: Optional[float] = Field(default=None)
    ocr_p95_ms: Optional[float] = Field(default=None)
    cpu_percent: Optional[float] = Field(default=None)
    rss_mb: Optional[float] = Field(default=None)
    cameras_processing: Optional[int] = Field(default=None)

    # per-camera frame/event counts + anything else the snapshot carried,
    # bounded by the pipeline's own get_metrics() shape
    detail: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
