"""
AI pipeline status API.

  POST /api/v1/pipeline/status   (ingest auth -- service-to-service push)
      the AI pipeline reports its latest AIPipeline.get_metrics() snapshot

  GET  /api/v1/pipeline/status   (operator JWT)
      the command-center dashboard reads it back

The backend cannot see YOLO/OCR/queue internals directly; this is the same
pattern ingestion already uses for per-camera health. A missing metric is
stored/returned as NULL -- never defaulted to a fabricated 0.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_current_user, require_ingest_auth
from app.database import get_db
from app.models.pipeline_status import PipelineStatus
from app.schemas.pipeline import PipelineStatusPush, PipelineStatusRead

router = APIRouter()


def _pick_percentile(block) -> tuple:
    if block is None:
        return None, None
    return block.p50_ms, block.p95_ms


@router.post("/status", response_model=PipelineStatusRead)
def push_pipeline_status(
    payload: PipelineStatusPush,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_ingest_auth),
):
    row = db.get(PipelineStatus, payload.service_id) or PipelineStatus(service_id=payload.service_id)

    row.reported_at = datetime.utcnow()
    row.num_workers = payload.num_workers
    row.processed_frames = payload.processed_frames
    row.processed_fps = payload.processed_fps
    row.vehicles_detected = payload.vehicles_detected
    row.events_generated = payload.events_generated
    row.events_delivered = payload.events_delivered
    row.events_dropped = payload.events_dropped
    row.event_queue_depth = payload.event_queue_depth
    row.event_queue_max_depth = payload.event_queue_max_depth
    row.yolo_p50_ms, row.yolo_p95_ms = _pick_percentile(payload.yolo_latency_ms)
    row.ocr_p50_ms, row.ocr_p95_ms = _pick_percentile(payload.ocr_latency_ms)
    row.cpu_percent = payload.cpu_percent
    row.rss_mb = payload.rss_mb

    fbc = payload.frames_by_camera or {}
    row.cameras_processing = sum(1 for v in fbc.values() if v and v > 0) if fbc else None
    row.detail = {
        "frames_by_camera": fbc or None,
        "events_by_camera": payload.events_by_camera or None,
    }

    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_read(row)


@router.get("/status", response_model=PipelineStatusRead | None)
def get_pipeline_status(
    service_id: str = "default",
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    row = db.get(PipelineStatus, service_id)
    if row is None:
        return None
    return _to_read(row)


def _to_read(row: PipelineStatus) -> PipelineStatusRead:
    now = datetime.now(timezone.utc)
    reported = row.reported_at if row.reported_at.tzinfo else row.reported_at.replace(tzinfo=timezone.utc)
    r = PipelineStatusRead.model_validate(row)
    r.age_seconds = round((now - reported).total_seconds(), 1)
    return r
