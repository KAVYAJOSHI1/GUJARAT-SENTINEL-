"""GET /api/v1/dashboard/health — command-center observability aggregate.

Every field is a live measurement or NULL. Nothing here is estimated or
defaulted to a placeholder; an absent AI-pipeline report yields
`ai_pipeline.status == "unknown"` with null metrics, not zeros.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ComponentHealth(BaseModel):
    status: str                      # "ok" | "degraded" | "down" | "unknown"
    detail: Optional[str] = None
    latency_ms: Optional[float] = None


class CameraHealthCounts(BaseModel):
    total: int
    online: int
    degraded: int
    offline: int
    # a camera whose last health push is older than the freshness window
    # (or that has never pushed) -- distinct from "offline"
    stale: int
    never_reported: int
    oldest_health_age_seconds: Optional[float] = None


class Latency(BaseModel):
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None


class AiPipelineHealth(BaseModel):
    # "online": a fresh metrics report; "stale": last report too old;
    # "unknown": the pipeline has never reported to this backend
    status: str
    reported_at: Optional[datetime] = None
    age_seconds: Optional[float] = None
    num_workers: Optional[int] = None
    processed_fps: Optional[float] = None
    frames_processed: Optional[int] = None
    vehicles_detected: Optional[int] = None
    events_generated: Optional[int] = None
    events_delivered: Optional[int] = None
    events_dropped: Optional[int] = None
    event_queue_depth: Optional[int] = None
    event_queue_max_depth: Optional[int] = None
    yolo_latency_ms: Latency = Latency()
    ocr_latency_ms: Latency = Latency()
    cpu_percent: Optional[float] = None
    rss_mb: Optional[float] = None
    cameras_processing: Optional[int] = None


class EventFlowHealth(BaseModel):
    last_event_at: Optional[datetime] = None
    last_event_age_seconds: Optional[float] = None
    events_last_15min: int
    readable_last_15min: int
    unknown_last_15min: int


class AlertHealth(BaseModel):
    total: int
    active: int                      # status = NEW
    acknowledged: int
    high_or_critical_active: int


class SystemHealth(BaseModel):
    generated_at: datetime
    backend: ComponentHealth
    database: ComponentHealth
    ai_pipeline: AiPipelineHealth
    cameras: CameraHealthCounts
    events: EventFlowHealth
    alerts: AlertHealth
