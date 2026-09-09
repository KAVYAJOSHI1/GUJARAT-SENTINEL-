"""
backend/app/services/capacity_model.py

Phase 17 Step 10 -- transparent capacity model (backend-local copy).

The backend runs in its own container with its own dependency set (no
torch/YOLO/EasyOCR -- see backend/requirements.txt) and cannot import the
AI pipeline's ``ai/`` package, which lives in a separate service/process
entirely (see docker-compose.yml: the `backend` and `pipeline` services
have no shared Python path). This module therefore mirrors
``ai/capacity.py``'s arithmetic deliberately, not accidentally -- keep the
two in sync by hand if the formula changes; the shared idea (never
fabricate a number, always trace it to a measurement or a named
assumption) matters more than avoiding this one small duplication.

Same rule as the AI-side module: NEVER "divide 80,000 by an arbitrary
number." Every number is either MEASURED (``MeasuredBaseline.source``
names the benchmark run) or a named, documented, overridable ASSUMPTION
(``CapacityAssumptions``), and the two are never merged into one number
that looks measured.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

REGION_NAMES: List[str] = ["ahmedabad", "surat", "rajkot", "vadodara", "other"]


@dataclass(frozen=True)
class MeasuredBaseline:
    worker_fps_budget: float
    source: str
    anpr_cost_multiplier: float = 1.0
    measured_cameras: int = 0
    measured_at: Optional[str] = None


@dataclass(frozen=True)
class CapacityAssumptions:
    target_fps: float = 2.0
    anpr_percentage: float = 0.30
    redundancy_factor: float = 1.3
    headroom_pct: float = 0.20
    gpu_speedup_factor: Optional[float] = None
    per_camera_bitrate_kbps: float = 2048.0
    evidence_events_per_camera_per_day: float = 200.0
    avg_evidence_size_kb: float = 120.0
    num_regions: int = 5


@dataclass
class CapacityEstimate:
    baseline: MeasuredBaseline
    assumptions: CapacityAssumptions
    avg_cost_units_per_camera: float
    raw_cameras_per_worker: float
    effective_cameras_per_worker: float
    target_cameras: int
    required_workers: int
    workers_per_region: int
    estimated_gpu_count: Optional[int]
    estimated_ingress_bandwidth_mbps: float
    estimated_ingress_bandwidth_gbps: float
    estimated_storage_gb_per_day: float
    estimated_storage_tb_per_day: float
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "measured": {
                "worker_fps_budget": self.baseline.worker_fps_budget,
                "source": self.baseline.source,
                "anpr_cost_multiplier": self.baseline.anpr_cost_multiplier,
                "measured_cameras": self.baseline.measured_cameras,
                "measured_at": self.baseline.measured_at,
            },
            "assumptions": {
                "target_fps": self.assumptions.target_fps,
                "anpr_percentage": self.assumptions.anpr_percentage,
                "redundancy_factor": self.assumptions.redundancy_factor,
                "headroom_pct": self.assumptions.headroom_pct,
                "gpu_speedup_factor": self.assumptions.gpu_speedup_factor,
                "gpu_speedup_verified": False,
                "per_camera_bitrate_kbps": self.assumptions.per_camera_bitrate_kbps,
                "evidence_events_per_camera_per_day": self.assumptions.evidence_events_per_camera_per_day,
                "avg_evidence_size_kb": self.assumptions.avg_evidence_size_kb,
                "num_regions": self.assumptions.num_regions,
            },
            "computed": {
                "avg_cost_units_per_camera": round(self.avg_cost_units_per_camera, 3),
                "raw_cameras_per_worker": round(self.raw_cameras_per_worker, 2),
                "effective_cameras_per_worker": round(self.effective_cameras_per_worker, 2),
                "target_cameras": self.target_cameras,
                "required_workers": self.required_workers,
                "workers_per_region": self.workers_per_region,
                "estimated_gpu_count": self.estimated_gpu_count,
                "estimated_ingress_bandwidth_mbps": round(self.estimated_ingress_bandwidth_mbps, 1),
                "estimated_ingress_bandwidth_gbps": round(self.estimated_ingress_bandwidth_gbps, 3),
                "estimated_storage_gb_per_day": round(self.estimated_storage_gb_per_day, 1),
                "estimated_storage_tb_per_day": round(self.estimated_storage_tb_per_day, 3),
            },
            "notes": self.notes,
        }


def compute_capacity(
    baseline: MeasuredBaseline,
    assumptions: Optional[CapacityAssumptions] = None,
    *,
    target_cameras: int = 80_000,
) -> CapacityEstimate:
    a = assumptions or CapacityAssumptions()
    notes: List[str] = []

    avg_cost_units = a.anpr_percentage * baseline.anpr_cost_multiplier + (1 - a.anpr_percentage) * 1.0
    denom = a.target_fps * avg_cost_units
    raw_cameras_per_worker = (baseline.worker_fps_budget / denom) if denom > 0 else 0.0

    effective_cameras_per_worker = raw_cameras_per_worker / a.redundancy_factor / (1 + a.headroom_pct)
    if effective_cameras_per_worker <= 0:
        notes.append(
            "effective_cameras_per_worker computed as 0 or negative -- the measured worker_fps_budget "
            "cannot sustain even one camera at the requested target_fps/anpr_percentage."
        )
        effective_cameras_per_worker = 0.0001

    required_workers = math.ceil(target_cameras / effective_cameras_per_worker)
    workers_per_region = math.ceil(required_workers / max(1, a.num_regions))

    estimated_gpu_count = None
    if a.gpu_speedup_factor:
        estimated_gpu_count = math.ceil(required_workers / a.gpu_speedup_factor)
        notes.append(
            f"estimated_gpu_count assumes a {a.gpu_speedup_factor}x per-worker speedup from GPU inference -- "
            "NOT measured on this project's hardware; re-verify on target deployment hardware before procurement."
        )

    bandwidth_mbps = (target_cameras * a.per_camera_bitrate_kbps) / 1000.0
    storage_gb_per_day = (target_cameras * a.evidence_events_per_camera_per_day * a.avg_evidence_size_kb) / (1024 * 1024)

    if baseline.measured_cameras and baseline.measured_cameras < 10:
        notes.append(
            f"MeasuredBaseline was captured with only {baseline.measured_cameras} camera(s) -- "
            "extrapolating a per-worker budget from a small sample is a real source of error."
        )

    return CapacityEstimate(
        baseline=baseline, assumptions=a, avg_cost_units_per_camera=avg_cost_units,
        raw_cameras_per_worker=raw_cameras_per_worker, effective_cameras_per_worker=effective_cameras_per_worker,
        target_cameras=target_cameras, required_workers=required_workers, workers_per_region=workers_per_region,
        estimated_gpu_count=estimated_gpu_count, estimated_ingress_bandwidth_mbps=bandwidth_mbps,
        estimated_ingress_bandwidth_gbps=bandwidth_mbps / 1000.0, estimated_storage_gb_per_day=storage_gb_per_day,
        estimated_storage_tb_per_day=storage_gb_per_day / 1024.0, notes=notes,
    )


def classify_load(cpu_percent: Optional[float], queue_ratio: Optional[float]) -> Dict[str, object]:
    """Same measurable-threshold spirit as ai/degradation.py::SystemLoadMonitor
    (kept independent for the same cross-service reason as the rest of this
    module) -- HEALTHY/DEGRADED/OVERLOADED from real, available numbers only;
    a missing input is never treated as "0", it is simply not evaluated."""
    reasons_overloaded: List[str] = []
    reasons_degraded: List[str] = []

    if cpu_percent is not None:
        if cpu_percent >= 90.0:
            reasons_overloaded.append(f"CPU {cpu_percent:.0f}% >= 90%")
        elif cpu_percent >= 70.0:
            reasons_degraded.append(f"CPU {cpu_percent:.0f}% >= 70%")

    if queue_ratio is not None:
        if queue_ratio >= 0.85:
            reasons_overloaded.append(f"event queue {queue_ratio:.0%} full >= 85%")
        elif queue_ratio >= 0.5:
            reasons_degraded.append(f"event queue {queue_ratio:.0%} full >= 50%")

    if reasons_overloaded:
        return {"state": "OVERLOADED", "reasons": reasons_overloaded}
    if reasons_degraded:
        return {"state": "DEGRADED", "reasons": reasons_degraded}
    return {"state": "HEALTHY", "reasons": []}
