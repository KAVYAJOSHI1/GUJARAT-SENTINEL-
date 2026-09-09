"""
backend/app/services/capacity.py

Phase 17 Step 11 -- GET /api/v1/system/capacity.

Composed entirely from EXISTING data: the latest ``PipelineStatus`` push
(same row ``/api/v1/pipeline/status`` already reads -- see
app/services/system_metrics.py for the identical pattern), a live
``Camera`` count, and a committed benchmark summary file written by
``scripts/benchmark_phase17.py`` / ``scripts/benchmark_pipeline.py``
(``backend/data/phase17_benchmark_latest.json``). Read-only; no new
tables, no background job.

If that benchmark file is missing (a fresh checkout that hasn't run one
yet), a clearly-labeled conservative default baseline is used instead --
never silently treated as if it were measured.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlmodel import Session

from app.models.base import CameraStatus
from app.models.camera import Camera
from app.models.pipeline_status import PipelineStatus
from app.services.capacity_model import (
    CapacityAssumptions,
    MeasuredBaseline,
    classify_load,
    compute_capacity,
)

_BENCHMARK_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "phase17_benchmark_latest.json")
_PIPELINE_STALE = timedelta(seconds=30)

# Used ONLY when no benchmark file has been committed yet -- deliberately
# conservative and clearly labeled as an assumption, not a measurement.
_FALLBACK_BASELINE = MeasuredBaseline(
    worker_fps_budget=1.0,
    source="no benchmark file found -- fallback assumption, NOT measured; "
           "run scripts/benchmark_phase17.py --tier ai and copy its summary to "
           "backend/data/phase17_benchmark_latest.json",
    anpr_cost_multiplier=3.7,  # ~169ms OCR / ~45ms YOLO, from AI_ARCHITECTURE.md's own measured figures
    measured_cameras=0,
)


def _load_benchmark_summary() -> Optional[dict]:
    path = os.path.abspath(_BENCHMARK_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 -- a malformed file must never break the API
        return None


def _baseline_from_summary(summary: Optional[dict]) -> MeasuredBaseline:
    if not summary:
        return _FALLBACK_BASELINE
    try:
        return MeasuredBaseline(
            worker_fps_budget=float(summary["worker_fps_budget"]),
            source=str(summary.get("source", "backend/data/phase17_benchmark_latest.json")),
            anpr_cost_multiplier=float(summary.get("anpr_cost_multiplier", 3.7)),
            measured_cameras=int(summary.get("measured_cameras", 0)),
            measured_at=summary.get("measured_at"),
        )
    except (KeyError, TypeError, ValueError):
        return _FALLBACK_BASELINE


def system_capacity(db: Session, *, target_cameras: int = 80_000) -> dict:
    now = datetime.utcnow()

    ps = db.execute(
        select(PipelineStatus).order_by(PipelineStatus.reported_at.desc()).limit(1)
    ).scalar_one_or_none()

    total_cameras = int(db.execute(select(func.count(Camera.id))).scalar() or 0)
    online_cameras = int(
        db.execute(select(func.count(Camera.id)).where(Camera.status == CameraStatus.ONLINE)).scalar() or 0
    )

    pipeline_reported = ps is not None
    pipeline_stale = None
    num_workers = None
    cameras_processing = None
    cpu_percent = None
    queue_ratio = None
    if ps:
        age = (now - ps.reported_at).total_seconds()
        pipeline_stale = age > _PIPELINE_STALE.total_seconds()
        num_workers = ps.num_workers
        cameras_processing = ps.cameras_processing
        cpu_percent = ps.cpu_percent
        if ps.event_queue_depth is not None and ps.event_queue_max_depth:
            # event_queue_max_depth is a high-water mark, not the configured
            # maxsize -- used here only as a rough backpressure signal when
            # the true maxsize isn't itself reported.
            queue_ratio = min(1.0, ps.event_queue_depth / max(1, ps.event_queue_max_depth))

    degradation = classify_load(cpu_percent, queue_ratio)

    summary = _load_benchmark_summary()
    baseline = _baseline_from_summary(summary)
    assumptions = CapacityAssumptions()
    estimate = compute_capacity(baseline, assumptions, target_cameras=target_cameras)

    effective_workers_now = num_workers or 1
    estimated_current_capacity = round(estimate.effective_cameras_per_worker * effective_workers_now, 1)
    current_utilization = (
        round(cameras_processing / estimated_current_capacity, 3)
        if cameras_processing and estimated_current_capacity > 0 else None
    )

    return {
        "generated_at": now.isoformat() + "Z",
        "current": {
            "cameras_total": total_cameras,
            "cameras_active": online_cameras,
            "cameras_processing": cameras_processing,
            "workers": num_workers,
            "pipeline_reported": pipeline_reported,
            "pipeline_stale": pipeline_stale,
        },
        "health": {
            "cpu_percent": cpu_percent,
            "event_queue_depth": ps.event_queue_depth if ps else None,
            "event_queue_max_depth": ps.event_queue_max_depth if ps else None,
            "yolo_p95_ms": ps.yolo_p95_ms if ps else None,
            "ocr_p95_ms": ps.ocr_p95_ms if ps else None,
        },
        "degradation": degradation,
        "scaling": {
            "measured_worker_capacity": estimate.baseline.worker_fps_budget,
            "measured_source": estimate.baseline.source,
            "effective_cameras_per_worker": estimate.effective_cameras_per_worker,
            "estimated_current_capacity": estimated_current_capacity,
            "current_utilization": current_utilization,
            "target_capacity": target_cameras,
            "required_workers_for_target": estimate.required_workers,
            "workers_per_region": estimate.workers_per_region,
            "num_regions_assumed": assumptions.num_regions,
            "estimated_gpu_count": estimate.estimated_gpu_count,
            "estimated_ingress_bandwidth_gbps": round(estimate.estimated_ingress_bandwidth_gbps, 3),
            "estimated_storage_tb_per_day": round(estimate.estimated_storage_tb_per_day, 3),
        },
        "benchmark_summary": summary,
        "capacity_model": estimate.to_dict(),
        "note": (
            "PoC measured/simulated capacity model -- see docs/SCALE_TO_80000.md and "
            "docs/PHASE17_BENCHMARK.md. 'estimated_current_capacity' and "
            "'required_workers_for_target' are calculations from a measured or "
            "assumption-labeled baseline, never a claim that 80,000 cameras have "
            "actually been processed by this system."
        ),
    }
