"""
ai/capacity.py

Phase 17 Step 10 -- transparent capacity model.

The rule this module exists to enforce: NEVER "divide 80,000 by an
arbitrary number." Every number that goes into the 80,000-camera estimate
below is either:

  (a) MEASURED -- taken from an actual benchmark run
      (scripts/benchmark_phase17.py / scripts/benchmark_pipeline.py),
      carried in ``MeasuredBaseline`` with an explicit ``source`` string
      naming that run, or
  (b) an ASSUMPTION -- a named, documented, conservative default in
      ``CapacityAssumptions`` that the caller can override, and that is
      always echoed back in the result labeled as an assumption, never
      silently folded into a number that looks measured.

This module does not touch a network, a database, or a GPU -- it is pure
arithmetic over whatever ``MeasuredBaseline`` and ``CapacityAssumptions``
it is given. See docs/SCALE_TO_80000.md for the full worked example and
docs/PHASE17_BENCHMARK.md for where ``MeasuredBaseline`` numbers actually
come from.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class MeasuredBaseline:
    """Everything here MUST trace back to an actual benchmark run --
    ``source`` should name it (script + args + date), not just describe
    it. Never hand-tune these numbers to hit a target; if the measured
    number is unflattering, that is the honest result (see Step 18/19 of
    the Phase 17 brief -- document limitations, don't hide them)."""

    worker_fps_budget: float          # aggregate detection-equivalent frames/sec ONE worker process sustained
    source: str                       # e.g. "scripts/benchmark_pipeline.py --cameras MOCK_CAM01..05 --duration 60, 2026-09-09"
    anpr_cost_multiplier: float = 1.0  # measured OCR+detection cost / detection-only cost, per frame
    measured_cameras: int = 0          # how many cameras were actually in that run
    measured_at: Optional[str] = None  # ISO date string, optional


@dataclass(frozen=True)
class CapacityAssumptions:
    """Every field here is a documented, overridable ASSUMPTION -- not a
    measurement. Defaults are deliberately conservative."""

    target_fps: float = 2.0                 # desired sustained per-camera processing rate
    anpr_percentage: float = 0.30           # fraction of the 80k cameras assumed to run ANPR (vs DETECTION-only)
    redundancy_factor: float = 1.3          # >1.0 reserves capacity for failover / rolling restarts
    headroom_pct: float = 0.20              # operational headroom kept unused to avoid chronic OVERLOADED state
    gpu_speedup_factor: Optional[float] = None  # UNVERIFIED if set -- see note in compute_capacity()
    per_camera_bitrate_kbps: float = 2048.0     # ~2 Mbps H.264 stream, an industry-typical assumption
    evidence_events_per_camera_per_day: float = 200.0  # assumed ANPR/alert evidence writes per camera per day
    avg_evidence_size_kb: float = 120.0         # snapshot + plate crop, combined, assumed average size
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
            "cannot sustain even one camera at the requested target_fps/anpr_percentage; treat this "
            "result as 'not yet achievable at this configuration', not as a capacity number."
        )
        effective_cameras_per_worker = 0.0001  # avoid a divide-by-zero below; required_workers will be huge, honestly

    required_workers = math.ceil(target_cameras / effective_cameras_per_worker)
    workers_per_region = math.ceil(required_workers / max(1, a.num_regions))

    estimated_gpu_count = None
    if a.gpu_speedup_factor:
        estimated_gpu_count = math.ceil(required_workers / a.gpu_speedup_factor)
        notes.append(
            f"estimated_gpu_count assumes a {a.gpu_speedup_factor}x per-worker throughput speedup from GPU "
            "inference. This speedup is NOT measured on this project's hardware (no GPU was available during "
            "Phase 17 development) -- it is drawn from published YOLOv8n/EasyOCR GPU-vs-CPU benchmark ratios "
            "and must be re-verified on target deployment hardware before being used for procurement."
        )

    bandwidth_kbps = target_cameras * a.per_camera_bitrate_kbps
    bandwidth_mbps = bandwidth_kbps / 1000.0
    bandwidth_gbps = bandwidth_mbps / 1000.0

    storage_kb_per_day = target_cameras * a.evidence_events_per_camera_per_day * a.avg_evidence_size_kb
    storage_gb_per_day = storage_kb_per_day / (1024 * 1024)
    storage_tb_per_day = storage_gb_per_day / 1024.0

    if baseline.measured_cameras and baseline.measured_cameras < 10:
        notes.append(
            f"MeasuredBaseline was captured with only {baseline.measured_cameras} camera(s) in the run -- "
            "extrapolating a per-worker budget from a small sample is a real source of error; re-measure at "
            "higher camera counts on target hardware before treating this as final."
        )

    return CapacityEstimate(
        baseline=baseline,
        assumptions=a,
        avg_cost_units_per_camera=avg_cost_units,
        raw_cameras_per_worker=raw_cameras_per_worker,
        effective_cameras_per_worker=effective_cameras_per_worker,
        target_cameras=target_cameras,
        required_workers=required_workers,
        workers_per_region=workers_per_region,
        estimated_gpu_count=estimated_gpu_count,
        estimated_ingress_bandwidth_mbps=bandwidth_mbps,
        estimated_ingress_bandwidth_gbps=bandwidth_gbps,
        estimated_storage_gb_per_day=storage_gb_per_day,
        estimated_storage_tb_per_day=storage_tb_per_day,
        notes=notes,
    )
