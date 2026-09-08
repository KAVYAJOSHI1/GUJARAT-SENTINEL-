"""
Lightweight system observability summary (Phase 15G).

One consolidated snapshot for the command centre:
  * pipeline   -- the AI pipeline's last self-reported metrics
                  (frames, fps, detections, events gen/delivered/dropped,
                   queue depth/max, YOLO/OCR p50/p95, CPU, RSS)
  * anpr       -- readable / unknown split + failure-reason breakdown (24h)
  * detections -- vehicle_events totals + rate
  * alerts / anomalies / incidents / cases -- open counts
  * cameras    -- total / online / offline / cumulative reconnects

No Prometheus, no time-series store -- every value is a live query or the
latest pushed snapshot; a missing metric is NULL, never a fabricated 0.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlmodel import Session

from app.models.alert import Alert
from app.models.anomaly_event import AnomalyEvent
from app.models.base import AlertStatus, AnomalyStatus, CaseStatus, IncidentStatus
from app.models.camera import Camera
from app.models.case import Case
from app.models.incident import Incident
from app.models.pipeline_status import PipelineStatus
from app.models.vehicle_event import VehicleEvent

_PIPELINE_STALE = timedelta(seconds=30)


def system_metrics_summary(db: Session, *, window_hours: int = 24) -> dict:
    now = datetime.utcnow()
    since = now - timedelta(hours=window_hours)

    # --- pipeline snapshot ---
    ps = db.execute(
        select(PipelineStatus).order_by(PipelineStatus.reported_at.desc()).limit(1)
    ).scalar_one_or_none()
    pipeline: dict = {"reported": ps is not None}
    if ps:
        age = (now - ps.reported_at).total_seconds()
        pipeline.update({
            "service_id": ps.service_id,
            "reported_at": ps.reported_at,
            "age_seconds": round(age, 1),
            "stale": age > _PIPELINE_STALE.total_seconds(),
            "num_workers": ps.num_workers,
            "cameras_processing": ps.cameras_processing,
            "processed_frames": ps.processed_frames,
            "processed_fps": ps.processed_fps,
            "vehicles_detected": ps.vehicles_detected,
            "events_generated": ps.events_generated,
            "events_delivered": ps.events_delivered,
            "events_dropped": ps.events_dropped,
            "event_queue_depth": ps.event_queue_depth,
            "event_queue_max_depth": ps.event_queue_max_depth,
            "yolo_p50_ms": ps.yolo_p50_ms,
            "yolo_p95_ms": ps.yolo_p95_ms,
            "ocr_p50_ms": ps.ocr_p50_ms,
            "ocr_p95_ms": ps.ocr_p95_ms,
            "cpu_percent": ps.cpu_percent,
            "rss_mb": ps.rss_mb,
            "detail": ps.detail,
        })

    # --- ANPR (window) ---
    total_w, ok_w = db.execute(
        select(
            func.count(VehicleEvent.id),
            func.count(VehicleEvent.id).filter(VehicleEvent.anpr_status == "OK"),
        ).where(VehicleEvent.timestamp >= since)
    ).one()
    total_w = int(total_w or 0)
    ok_w = int(ok_w or 0)
    reason_rows = db.execute(
        select(VehicleEvent.anpr_failure_reason, func.count(VehicleEvent.id))
        .where(VehicleEvent.timestamp >= since,
               VehicleEvent.anpr_failure_reason.is_not(None))
        .group_by(VehicleEvent.anpr_failure_reason)
        .order_by(func.count(VehicleEvent.id).desc())
    ).all()

    total_all = int(db.execute(select(func.count(VehicleEvent.id))).scalar() or 0)

    # --- open work counts ---
    def _count(model, col, val):
        return int(db.execute(select(func.count(model.id)).where(col == val)).scalar() or 0)

    cameras = db.execute(select(Camera)).scalars().all()
    # mirror cameras.py::_effective_status: a camera with no health telemetry
    # keeps its onboard status; one that reported and went silent is OFFLINE.
    def _eff_online(c) -> bool:
        if c.status.value != "ONLINE":
            return False
        if c.health_updated_at is None:
            return True
        return (now - c.health_updated_at) <= timedelta(seconds=20)

    online = sum(1 for c in cameras if _eff_online(c))

    return {
        "generated_at": datetime.now(timezone.utc),
        "window_hours": window_hours,
        "pipeline": pipeline,
        "anpr": {
            "window_total": total_w,
            "readable": ok_w,
            "unknown": total_w - ok_w,
            "success_rate": round(ok_w / total_w, 3) if total_w else None,
            "failure_reasons": {r: int(n) for r, n in reason_rows},
        },
        "detections": {
            "total_all_time": total_all,
            "window_total": total_w,
            "per_hour": round(total_w / max(1, window_hours), 2),
        },
        "alerts": {
            "new": _count(Alert, Alert.status, AlertStatus.NEW),
            "total": int(db.execute(select(func.count(Alert.id))).scalar() or 0),
        },
        "anomalies": {
            "new": _count(AnomalyEvent, AnomalyEvent.status, AnomalyStatus.NEW),
        },
        "incidents": {
            "open": int(db.execute(
                select(func.count(Incident.id)).where(
                    Incident.status.in_([IncidentStatus.NEW, IncidentStatus.ACKNOWLEDGED,
                                         IncidentStatus.INVESTIGATING]))
            ).scalar() or 0),
        },
        "cases": {
            "open": int(db.execute(
                select(func.count(Case.id)).where(
                    Case.status.in_([CaseStatus.OPEN, CaseStatus.INVESTIGATING,
                                     CaseStatus.ON_HOLD]))
            ).scalar() or 0),
        },
        "cameras": {
            "total": len(cameras),
            "online": online,
            "offline": len(cameras) - online,
            "cumulative_reconnects": sum(c.reconnect_count or 0 for c in cameras),
        },
        "note": (
            "Live queries + the pipeline's last pushed snapshot. No "
            "Prometheus / time-series store. A NULL metric was not reported, "
            "not zero. Per-camera fair scheduling + bounded queues + "
            "latest-frame-wins backpressure are in ai/worker_pool.py "
            "(Phase 2C)."
        ),
    }
