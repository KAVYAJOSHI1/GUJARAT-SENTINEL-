#!/usr/bin/env python3
"""
scripts/benchmark_phase17.py

Phase 17 Step 8 -- reproducible capacity/scale benchmark engine.

Three DELIBERATELY SEPARATE fidelity tiers, never conflated in the report:

  A. INGESTION SIMULATION -- no real video, no AI. Synthetic frame
     "arrivals" fed straight into ai.scheduler.FairCameraScheduler +
     ai.sampling.AdaptiveFrameSampler. Answers: does the SCHEDULING layer
     itself (bounded queues, fairness, drop accounting) hold up at large
     simulated camera counts, independent of decode/inference cost?
     Cheap -- can run all the way to 500 "cameras".

  B. DECODE LOAD -- real OpenCV/FFmpeg decode via the existing
     ingestion.stream_manager.StreamManager, but frames are discarded by a
     no-op drain (no YOLO/OCR). Answers: how many concurrent camera
     STREAMS can this host's decoder actually sustain? Uses the repo's
     real mock camera video files (trafficdataset/Videos/Videos/*.MOV,
     cycling through them once the camera count exceeds the file count --
     several simulated cameras legitimately decoding the same physical
     clip independently, never claimed as distinct real footage).

  C. AI-PROCESSED -- the real ai.pipeline.AIPipeline (YOLO + EasyOCR),
     via the EXISTING scripts/benchmark_pipeline.py machinery (not
     duplicated here). This is the expensive, ground-truth tier; per
     SCALABILITY.md this CPU-only dev host is already at its detection+OCR
     ceiling at single-digit camera counts, so this script only runs it at
     small tiers and CITES the existing measured table for anything larger
     rather than re-running an already-known result.

Every result names its own tier explicitly (SIMULATED / DECODED /
AI-PROCESSED) -- never presented as equivalent capacity.

Usage:
    .venv/bin/python scripts/benchmark_phase17.py --tier ingestion --cameras 10,30,50,100,250,500 --duration 10
    .venv/bin/python scripts/benchmark_phase17.py --tier decode --cameras 10,30,50 --duration 20
    .venv/bin/python scripts/benchmark_phase17.py --tier ai --cameras 5,10 --duration 30 --no-backend
    .venv/bin/python scripts/benchmark_phase17.py --tier all --json-out docs/_phase17_bench_raw.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import queue
import statistics
import sys
import threading
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import psutil
    _PSUTIL_PROCESS = psutil.Process()
    _PSUTIL_PROCESS.cpu_percent(interval=None)  # prime the counter (first real call reports 0.0 otherwise)
except Exception:  # noqa: BLE001
    psutil = None
    _PSUTIL_PROCESS = None

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MOCK_VIDEO_GLOB = os.path.join(REPO_ROOT, "trafficdataset", "Videos", "Videos", "*.MOV")


def _resource_snapshot() -> Dict[str, Any]:
    """Uses ONE persistent psutil.Process handle (primed at import time) so
    cpu_percent(interval=None) has a real "since the last call" baseline --
    a freshly-constructed Process object always reports 0.0 on its first
    call, which would silently make every snapshot after the first one
    meaningless."""
    if _PSUTIL_PROCESS is None:
        return {"cpu_percent": None, "rss_mb": None}
    return {
        "cpu_percent": _PSUTIL_PROCESS.cpu_percent(interval=None),
        "rss_mb": round(_PSUTIL_PROCESS.memory_info().rss / (1024 * 1024), 1),
    }


# ===================================================================== #
# A. INGESTION SIMULATION -- scheduler/sampler only, no decode, no AI
# ===================================================================== #
def run_ingestion_simulation(
    num_cameras: int, duration_s: float, *, worker_fps_budget: float = 5.0, source_fps: float = 15.0,
) -> Dict[str, Any]:
    """``worker_fps_budget`` simulates ONE AI worker's real sustained
    throughput (e.g. the measured YOLO+OCR budget from the AI-PROCESSED
    tier) via a sleep per pulled frame -- this is what actually makes the
    scheduler's bounded-queue / latest-wins / fairness machinery matter:
    with `num_cameras * source_fps` arrival load against a much smaller
    `worker_fps_budget`, most frames MUST be dropped (by design, latest-
    frame-wins), and the interesting question is whether that drop is fair
    across priority classes and never starves anyone outright."""
    from ai.scheduler import CameraPriority, FairCameraScheduler

    scheduler = FairCameraScheduler()
    camera_ids = [f"SIM-{i:05d}" for i in range(num_cameras)]
    # Illustrative priority mix: 5% CRITICAL, 15% HIGH, 60% NORMAL, 20% BACKGROUND.
    for idx, cam_id in enumerate(camera_ids):
        frac = idx / max(1, num_cameras)
        if frac < 0.05:
            prio = CameraPriority.CRITICAL
        elif frac < 0.20:
            prio = CameraPriority.HIGH
        elif frac < 0.80:
            prio = CameraPriority.NORMAL
        else:
            prio = CameraPriority.BACKGROUND
        scheduler.set_priority(cam_id, prio)

    stop = threading.Event()
    frames_injected = [0]
    consumer_delay_s = (1.0 / worker_fps_budget) if worker_fps_budget > 0 else 0.0

    def _injector() -> None:
        i = 0
        while not stop.is_set():
            for cam_id in camera_ids:
                scheduler.put(cam_id, i)
                frames_injected[0] += 1
            i += 1
            time.sleep(1.0 / source_fps)

    def _consumer() -> None:
        # Simulates ONE AI worker thread pulling fairly-scheduled frames
        # at its own real (measured, or assumed) throughput -- no decode,
        # no inference actually runs, only the equivalent time cost.
        while not stop.is_set():
            got = scheduler.get(timeout=0.2)
            if got is not None and consumer_delay_s > 0:
                time.sleep(consumer_delay_s)

    t0 = time.monotonic()
    threads = [threading.Thread(target=_injector, daemon=True), threading.Thread(target=_consumer, daemon=True)]
    r0 = _resource_snapshot()
    for t in threads:
        t.start()
    time.sleep(duration_s)
    stop.set()
    for t in threads:
        t.join(timeout=2.0)
    elapsed = time.monotonic() - t0
    r1 = _resource_snapshot()

    snap = scheduler.snapshot()
    per_cam_processed = [c["frames_processed"] for c in snap["cameras"].values()]
    by_priority: Dict[str, Dict[str, Any]] = {}
    for prio in CameraPriority.ALL:
        cams = [c for c in snap["cameras"].values() if c["priority"] == prio]
        processed = [c["frames_processed"] for c in cams]
        starved = sum(1 for c in cams if c["frames_processed"] == 0)
        by_priority[prio] = {
            "camera_count": len(cams),
            "median_processed": statistics.median(processed) if processed else None,
            "min_processed": min(processed) if processed else None,
            "cameras_never_served": starved,
        }

    return {
        "tier": "SIMULATED",
        "description": "scheduler/sampler only -- no video decode, no AI inference",
        "configured_cameras": num_cameras,
        "simulated_cameras": num_cameras,
        "duration_s": round(elapsed, 2),
        "assumed_worker_fps_budget": worker_fps_budget,
        "assumed_source_fps_per_camera": source_fps,
        "frames_injected": frames_injected[0],
        "frames_processed": snap["totals"]["frames_processed"],
        "frames_dropped": snap["totals"]["frames_dropped"],
        "starvation_events": snap["totals"]["starvation_events"],
        "aggregate_processed_fps": round(snap["totals"]["frames_processed"] / elapsed, 2) if elapsed > 0 else None,
        "per_camera_processed": {
            "median": statistics.median(per_cam_processed) if per_cam_processed else None,
            "min": min(per_cam_processed) if per_cam_processed else None,
            "max": max(per_cam_processed) if per_cam_processed else None,
        },
        "by_priority": by_priority,
        "rss_mb_before": r0["rss_mb"],
        "rss_mb_after": r1["rss_mb"],
        "rss_growth_mb": (r1["rss_mb"] - r0["rss_mb"]) if (r0["rss_mb"] is not None and r1["rss_mb"] is not None) else None,
    }


# ===================================================================== #
# B. DECODE LOAD -- real StreamManager decode, no AI
# ===================================================================== #
def run_decode_load(num_cameras: int, duration_s: float, max_queue: int = 2000) -> Dict[str, Any]:
    from ingestion.models import CameraRecord
    from ingestion.stream_manager import StreamManager

    videos = sorted(glob.glob(MOCK_VIDEO_GLOB))
    if not videos:
        return {"tier": "DECODED", "error": f"no mock video files found at {MOCK_VIDEO_GLOB}", "configured_cameras": num_cameras}

    records = []
    for i in range(num_cameras):
        video = videos[i % len(videos)]
        records.append(CameraRecord(
            camera_id=f"DEC-{i:05d}", name=f"decode-sim-{i}", stream_url=video, stream_protocol="FILE",
        ))

    manager = StreamManager(max_queue_size=max_queue)
    drop_stop = threading.Event()

    def _drain() -> None:
        # No-op consumer: decode load must be measured independent of any
        # inference cost, so frames are discarded immediately (never
        # inspected) after being counted by HealthRegistry inside
        # StreamWorker itself.
        while not drop_stop.is_set():
            try:
                manager.frame_queue.get(timeout=0.5)
                manager.frame_queue.task_done()
            except queue.Empty:
                continue

    drain_thread = threading.Thread(target=_drain, daemon=True)
    drain_thread.start()

    r0 = _resource_snapshot()
    t0 = time.monotonic()
    manager.sync_cameras(records)
    time.sleep(duration_s)
    elapsed = time.monotonic() - t0
    snapshot = manager.health.get_snapshot()
    r1 = _resource_snapshot()

    manager.stop_all(join_timeout_s=5.0)
    drop_stop.set()
    drain_thread.join(timeout=2.0)

    fps_values = [m.measured_fps for m in snapshot if m.measured_fps and m.measured_fps > 0]
    online = [m for m in snapshot if m.status.value == "ONLINE"]
    return {
        "tier": "DECODED",
        "description": "real OpenCV/FFmpeg decode of repo mock video clips (cycled if cameras > available clips), no AI inference",
        "configured_cameras": num_cameras,
        "active_streams": len(online),
        "distinct_source_clips_used": min(num_cameras, len(videos)),
        "duration_s": round(elapsed, 2),
        "aggregate_decoded_fps": round(sum(fps_values), 2) if fps_values else None,
        "median_per_camera_fps": round(statistics.median(fps_values), 2) if fps_values else None,
        "min_per_camera_fps": round(min(fps_values), 2) if fps_values else None,
        "max_per_camera_fps": round(max(fps_values), 2) if fps_values else None,
        "total_frame_drops": sum(m.frame_drop_count for m in snapshot),
        "cpu_percent": r1["cpu_percent"],
        "rss_mb": r1["rss_mb"],
    }


# ===================================================================== #
# C. AI-PROCESSED -- delegate to the existing real-pipeline benchmark
# ===================================================================== #
def run_ai_processed(num_cameras: int, duration_s: float, *, fair_scheduler: bool, no_backend: bool) -> Dict[str, Any]:
    from scripts.benchmark_pipeline import Sampler, build_report
    from scripts.run_pipeline_service import PipelineService, load_registry, select_cameras

    registry_path = os.path.join(REPO_ROOT, "data", "trafficdataset_camera_registry.json")
    entries = load_registry(registry_path)
    if num_cameras > len(entries):
        return {
            "tier": "AI-PROCESSED", "error": f"only {len(entries)} mock cameras available in {registry_path}",
            "configured_cameras": num_cameras,
        }

    class _Args:
        pass

    args = _Args()
    args.all = False
    args.cameras = ",".join(e["camera_id"] for e in entries[:num_cameras])
    args.camera = None
    args.backend_url = os.getenv("SENTINEL_BACKEND_URL", "http://localhost:8000/api/v1/events/ai-detection")
    args.no_backend = no_backend
    args.ai_workers = 1
    args.fair_scheduler = fair_scheduler
    args.frame_skip = 0
    args.device = os.getenv("SENTINEL_AI_DEVICE", "cpu")
    args.evidence_dir = os.path.join(REPO_ROOT, "evidence", "phase17_bench")
    args.max_queue = 500
    args.stats_interval = 2.0
    args.admin_user = os.getenv("ADMIN_USER") or os.getenv("ADMIN_USERNAME", "")
    args.admin_password = os.getenv("ADMIN_PASSWORD", "")
    args.duration = duration_s

    chosen = select_cameras(entries, args)
    svc = PipelineService(chosen, args)
    sampler = Sampler(svc, interval_s=args.stats_interval)

    if svc.pool is not None:
        svc.pool.start()
    else:
        svc.consumer.start()
    svc.manager.sync_cameras(svc.records)
    sampler.start()

    t0 = time.monotonic()
    time.sleep(duration_s)
    elapsed = time.monotonic() - t0

    sampler.stop()
    final_health = {m.camera_id: m for m in svc.manager.health.get_snapshot()}
    svc.shutdown()

    report = build_report(svc, sampler, args, elapsed, final_health)
    report["tier"] = "AI-PROCESSED"
    report["description"] = "real ai.pipeline.AIPipeline (YOLO + EasyOCR) via scripts/benchmark_pipeline.py"
    report["configured_cameras"] = num_cameras
    return report


# ===================================================================== #
# CLI
# ===================================================================== #
def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 17 capacity/scale benchmark engine")
    ap.add_argument("--tier", choices=["ingestion", "decode", "ai", "all"], default="ingestion")
    ap.add_argument("--cameras", default="10,30,50,100,250,500", help="comma-separated camera-count tiers")
    ap.add_argument("--duration", type=float, default=15.0)
    ap.add_argument("--worker-fps-budget", type=float, default=5.0,
                    help="ingestion tier only: simulated one-worker sustained FPS budget")
    ap.add_argument("--source-fps", type=float, default=15.0,
                    help="ingestion tier only: simulated per-camera source FPS")
    ap.add_argument("--no-backend", action="store_true", default=True)
    ap.add_argument("--fair-scheduler", action="store_true", default=True)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    tiers = [int(x) for x in args.cameras.split(",") if x.strip()]
    results: List[Dict[str, Any]] = []

    to_run = ["ingestion", "decode", "ai"] if args.tier == "all" else [args.tier]
    for tier in to_run:
        for n in tiers:
            print(f"\n=== {tier.upper()} tier: {n} cameras, {args.duration}s ===", flush=True)
            try:
                if tier == "ingestion":
                    res = run_ingestion_simulation(
                        n, args.duration, worker_fps_budget=args.worker_fps_budget, source_fps=args.source_fps,
                    )
                elif tier == "decode":
                    res = run_decode_load(n, args.duration)
                else:
                    res = run_ai_processed(n, args.duration, fair_scheduler=args.fair_scheduler, no_backend=args.no_backend)
            except Exception as exc:  # noqa: BLE001 -- one tier failing must not abort the rest
                res = {"tier": tier.upper(), "configured_cameras": n, "error": str(exc)}
            print(json.dumps(res, indent=2, default=str))
            results.append(res)

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n[benchmark_phase17] wrote {args.json_out}")


if __name__ == "__main__":
    main()
