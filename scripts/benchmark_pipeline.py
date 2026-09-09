#!/usr/bin/env python3
"""
SENTINEL pipeline benchmark harness (Phase 2A Task 3; extended Phase 2C for
the multi-worker pool).

Reuses scripts/run_pipeline_service.py's existing PipelineService (registry
loading, StreamManager + ingestion, AIPipeline / ai.worker_pool.AIWorkerPool,
camera-health push) exactly as-is -- this is NOT a second ingestion/
benchmark architecture, only a periodic sampler + end-of-run report wrapped
around the same machinery scripts/run_pipeline_service.py and
scripts/run_mock_cameras.py already use.

Usage:
    .venv/bin/python scripts/benchmark_pipeline.py --cameras cam04,cam06 --duration 60
    .venv/bin/python scripts/benchmark_pipeline.py --all --duration 30 --no-backend
    .venv/bin/python scripts/benchmark_pipeline.py --cameras MOCK_CAM01,MOCK_CAM02 \\
        --registry data/trafficdataset_camera_registry.json --duration 60 --json-out bench.json
    .venv/bin/python scripts/benchmark_pipeline.py --all --ai-workers 2 --duration 60

The same command works for 1 / 5 / 10 / 20 / 30 cameras -- just change
--cameras / --all and, for a from-scratch mock fleet,
`scripts/generate_mock_camera_registry.py --count N` first. This script
does not run 30 cameras on its own; that is an explicit choice the caller
makes by passing that many camera ids. --ai-workers similarly selects
between the single-consumer path (1, default) and the Phase 2C
camera-sharded multi-process pool (>1) -- see ai/worker_pool.py.

Every number in the report comes from an actual counter or latency sample
collected during the run (ai.pipeline.AIPipeline.get_metrics() /
ai.worker_pool.AIWorkerPool.get_metrics(),
ingestion.stream_health.HealthRegistry.get_snapshot(), and this script's own
periodic sampling of queue depth). A metric with zero samples (e.g. OCR
p95 when OCR never actually ran, or a camera with no health snapshot yet)
is reported as null/"n/a", never estimated or faked.
"""
import argparse
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.run_pipeline_service import (  # noqa: E402
    PipelineService,
    REGISTRY,
    load_registry,
    select_cameras,
    log as service_log,
)


def _fmt(v, suffix=""):
    return "n/a" if v is None else f"{v}{suffix}"


class Sampler:
    """Polls the running PipelineService at a fixed interval and keeps a
    time series of snapshots, so the report can compute steady-state
    per-camera input FPS (an average over many samples, not one noisy
    before/after delta) instead of a single reading."""

    def __init__(self, svc: PipelineService, interval_s: float = 2.0):
        self.svc = svc
        self.interval_s = max(0.5, interval_s)
        self.samples: list = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="benchmark-sampler", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5.0)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                health = {m.camera_id: m for m in self.svc.manager.health.get_snapshot()}
                sample = {
                    "t": time.monotonic(),
                    "health": health,
                    "frame_queue_depth": self.svc.manager.frame_queue.qsize(),
                }
                # Sampled WHILE the run is live -- a reading taken after
                # svc.shutdown() (workers/sender threads stopped) would
                # understate real load, especially at higher camera
                # counts where CPU/RAM peak during the run, not after.
                if self.svc.pool is not None:
                    sample["resource_usage_per_worker"] = self.svc.pool.get_metrics()["per_worker_resource_usage"]
                else:
                    sample["resource_usage"] = self.svc.pipeline.get_resource_usage()
                self.samples.append(sample)
            except Exception:  # noqa: BLE001 -- a sampling hiccup must never kill the run
                service_log.exception("benchmark sampler: snapshot failed")


def build_report(svc: PipelineService, sampler: "Sampler", args, elapsed_s: float, final_health: dict) -> dict:
    samples = sampler.samples
    pooled = svc.pool is not None
    # Skip roughly the first quarter (or first ~10s, whichever is smaller)
    # as model/connection warm-up, matching the audit's own benchmark-plan
    # methodology -- falls back to every sample collected on a short run.
    warmup_n = min(len(samples) // 4, max(1, int(10 / sampler.interval_s)))
    steady = samples[warmup_n:] or samples

    final_metrics = svc.pool.get_metrics() if pooled else svc.pipeline.get_metrics()
    # `final_health` is captured by the CALLER before svc.shutdown() runs --
    # stopping the workers marks every camera OFFLINE, which would
    # otherwise overwrite the status the camera actually had for the whole
    # benchmark with a shutdown artifact.

    per_camera = {}
    total_input_fps = 0.0
    have_any_input_fps = False
    total_dropped_frames = 0
    starved_cameras = []
    for cam_id in svc.camera_names:
        h = final_health.get(cam_id)
        fps_samples = [
            s["health"][cam_id].measured_fps for s in steady
            if cam_id in s["health"] and s["health"][cam_id].measured_fps > 0
        ]
        input_fps = round(sum(fps_samples) / len(fps_samples), 2) if fps_samples else None
        frames = final_metrics["frames_by_camera"].get(cam_id, 0)
        events = final_metrics["events_by_camera"].get(cam_id, 0)
        processed_fps = round(frames / elapsed_s, 2) if elapsed_s > 0 else None
        drops = h.frame_drop_count if h else 0
        per_camera[cam_id] = {
            "status": h.status.value if h else "n/a",
            "input_fps": input_fps,
            "processed_frames": frames,
            "processed_fps": processed_fps,
            "events_generated": events,
            "frame_drops": drops,
            "reconnects": h.reconnect_count if h else 0,
            "last_reconnect_duration_s": (
                round(h.last_reconnect_duration_s, 2)
                if h and h.last_reconnect_duration_s is not None else None
            ),
        }
        if input_fps is not None:
            total_input_fps += input_fps
            have_any_input_fps = True
        total_dropped_frames += drops
        # "Starved" = a camera that never got a single AI-processed frame
        # this whole run -- the exact fairness failure Phase 2B measured.
        if frames == 0:
            starved_cameras.append(cam_id)

    if pooled:
        total_processed_frames = final_metrics["processed_frames"]
        frames_skipped = 0  # frame-skip sampling isn't implemented in the pool path (Task 2C scope)
    else:
        total_processed_frames = svc.consumer.frames_processed
        frames_skipped = svc.consumer.frames_skipped
    total_processed_fps = round(total_processed_frames / elapsed_s, 2) if elapsed_s > 0 else None
    frame_queue_depths = [s["frame_queue_depth"] for s in samples]

    # CPU/RAM: use the DURING-RUN samples (see Sampler._run's comment) --
    # avg CPU reflects sustained load, max CPU/RSS the observed peak. A
    # post-shutdown-only reading would understate both. Pool mode sums
    # per-worker RSS (each worker is a separate process with its own model
    # in memory -- that's the real, additive memory cost) and sums CPU
    # across workers too (each can independently use up to 100% of a core).
    if pooled:
        cpu_samples, rss_samples = [], []
        for s in samples:
            per_worker = s.get("resource_usage_per_worker") or []
            cpus = [w.get("cpu_percent") for w in per_worker if w.get("cpu_percent") is not None]
            rsses = [w.get("rss_mb") for w in per_worker if w.get("rss_mb") is not None]
            if cpus:
                cpu_samples.append(sum(cpus))
            if rsses:
                rss_samples.append(sum(rsses))
        rss_final = sum(w.get("rss_mb") or 0 for w in final_metrics.get("per_worker_resource_usage", []))
    else:
        cpu_samples = [
            s["resource_usage"]["cpu_percent"] for s in samples
            if s["resource_usage"]["cpu_percent"] is not None
        ]
        rss_samples = [
            s["resource_usage"]["rss_mb"] for s in samples
            if s["resource_usage"]["rss_mb"] is not None
        ]
        rss_final = final_metrics["resource_usage"]["rss_mb"]
    resource_usage = {
        "cpu_percent_avg": round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else None,
        "cpu_percent_max": round(max(cpu_samples), 1) if cpu_samples else None,
        "rss_mb_max": round(max(rss_samples), 1) if rss_samples else None,
        "rss_mb_final": rss_final,
        "sample_count": len(cpu_samples),
    }

    if pooled:
        latency_ms = {
            "yolo": final_metrics["combined_latency"]["yolo_latency_ms"],
            "ocr": final_metrics["combined_latency"]["ocr_latency_ms"],
            "send": final_metrics["combined_latency"]["send_latency_ms"],
            "compute": final_metrics["combined_latency"]["compute_latency_ms"],
            "end_to_end": final_metrics["combined_latency"]["end_to_end_latency_ms"],
        }
        event_delivery = {
            "events_generated": final_metrics["total_ai_events_generated"],
            "events_enqueued": None,  # per-worker queue internals, not meaningfully poolable as one number
            "events_sent_ok": final_metrics["events_sent_ok"],
            "events_dropped_queue_full": final_metrics["events_dropped_queue_full"],
            "events_dropped_backend_rejected": final_metrics["events_dropped_backend_rejected"],
            "events_dropped_buffer_full": final_metrics["events_dropped_buffer_full"],
            "events_buffered_for_retry": final_metrics["events_buffered_for_retry"],
            "event_queue_maxsize": None,
            "event_queue_max_depth": final_metrics["event_queue_max_depth"],
        }
    else:
        latency_ms = {
            "yolo": final_metrics["yolo_latency_ms"],
            "ocr": final_metrics["ocr_latency_ms"],
            "send": final_metrics["send_latency_ms"],
            "compute": final_metrics["compute_latency_ms"],
            "end_to_end": final_metrics["end_to_end_latency_ms"],
        }
        event_delivery = {
            "events_generated": final_metrics["total_ai_events_generated"],
            "events_enqueued": final_metrics["events_enqueued"],
            "events_sent_ok": final_metrics["events_sent_ok"],
            "events_dropped_queue_full": final_metrics["events_dropped_queue_full"],
            "events_dropped_backend_rejected": final_metrics["events_dropped_backend_rejected"],
            "events_dropped_buffer_full": final_metrics["events_dropped_buffer_full"],
            "events_buffered_for_retry": final_metrics["events_buffered_for_retry"],
            "event_queue_maxsize": final_metrics["event_queue_maxsize"],
            # True high-water-mark, tracked continuously inside AIPipeline
            # itself -- unaffected by sampling interval or shutdown timing.
            "event_queue_max_depth": final_metrics["event_queue_max_depth"],
        }

    report = {
        "cameras": list(svc.camera_names.keys()),
        "ai_workers": svc.ai_workers,
        "no_backend": bool(args.no_backend),
        "duration_requested_s": args.duration,
        "duration_actual_s": round(elapsed_s, 2),
        "sample_count": len(samples),
        "per_camera": per_camera,
        "totals": {
            "input_fps": round(total_input_fps, 2) if have_any_input_fps else None,
            "processed_fps": total_processed_fps,
            "processed_frames": total_processed_frames,
            "frames_skipped": frames_skipped,
            "dropped_frames": total_dropped_frames,
            # Sampled, not a true always-on high-water-mark like the event
            # queue's -- a spike shorter than --sample-interval can be missed.
            # Labeled explicitly so this is never confused with a hard max.
            "frame_queue_max_depth_sampled": max(frame_queue_depths) if frame_queue_depths else None,
            "frame_queue_maxsize": args.max_queue,
            "cameras_total": len(svc.camera_names),
            "cameras_starved": len(starved_cameras),
            "starved_camera_ids": starved_cameras,
        },
        "event_delivery": event_delivery,
        "latency_ms": latency_ms,
        "resource_usage": resource_usage,
    }
    if pooled:
        report["pool"] = {
            "num_workers": final_metrics["num_workers"],
            "worker_assignment": final_metrics["worker_assignment"],
            "frames_routed": final_metrics["frames_routed"],
            "frames_handoff_dropped": final_metrics["frames_handoff_dropped"],
            "per_worker_queue_depth": final_metrics["per_worker_queue_depth"],
            "per_worker_stale_evicted": final_metrics["per_worker_stale_evicted"],
            "per_worker_handoff_drops": final_metrics["per_worker_handoff_drops"],
            "per_worker_resource_usage": final_metrics["per_worker_resource_usage"],
            "per_worker_latency": final_metrics["per_worker_latency"],
        }
    if not pooled and hasattr(svc.consumer, "scheduler"):
        # Phase 17 --fair-scheduler: the scheduler's own view of fairness
        # (per-camera starvation counts, drop reasons, queue depth) --
        # independent of / in addition to the starved_camera_ids check
        # above (which only sees "processed a frame or not", not WHY).
        report["fair_scheduler"] = svc.consumer.get_metrics()
    return report


def print_human_report(report: dict) -> None:
    print("\n" + "=" * 72)
    print(" SENTINEL PIPELINE BENCHMARK")
    print("=" * 72)
    print(f" cameras:            {', '.join(report['cameras']) or '(none)'}")
    print(f" ai_workers:         {report.get('ai_workers', 1)}")
    print(f" fair_scheduler:     {'fair_scheduler' in report}")
    print(f" duration requested: {report['duration_requested_s']}s   actual: {report['duration_actual_s']}s")
    print(f" samples collected:  {report['sample_count']}")
    print("-" * 72)
    print(" PER-CAMERA")
    for cam_id, c in report["per_camera"].items():
        print(
            f"  {cam_id}: status={c['status']} input_fps={_fmt(c['input_fps'])} "
            f"processed_fps={_fmt(c['processed_fps'])} events={c['events_generated']} "
            f"drops={c['frame_drops']} reconnects={c['reconnects']} "
            f"last_reconnect={_fmt(c['last_reconnect_duration_s'], 's')}"
        )
    print("-" * 72)
    t = report["totals"]
    print(" TOTALS")
    print(f"  input_fps (sum)........ {_fmt(t['input_fps'])}")
    print(f"  processed_fps (total).. {_fmt(t['processed_fps'])}")
    print(f"  processed_frames....... {t['processed_frames']}  skipped={t['frames_skipped']}")
    print(f"  dropped_frames (ingestion) {t['dropped_frames']}")
    print(f"  cameras starved (0 AI frames) {t['cameras_starved']}/{t['cameras_total']}  {t['starved_camera_ids']}")
    print(
        f"  frame_queue............ max_sampled={_fmt(t['frame_queue_max_depth_sampled'])} "
        f"/ maxsize={t['frame_queue_maxsize']}"
    )
    print("-" * 72)
    e = report["event_delivery"]
    print(" EVENT DELIVERY (AI pipeline -> backend)")
    if report.get("no_backend"):
        print("  (--no-backend dry run: dispatch is stubbed, sent_ok/dropped counters below are not meaningful)")
    print(f"  generated={e['events_generated']} enqueued={_fmt(e['events_enqueued'])} sent_ok={e['events_sent_ok']}")
    print(
        f"  dropped: queue_full={e['events_dropped_queue_full']} "
        f"backend_rejected={e['events_dropped_backend_rejected']} "
        f"buffer_full={e['events_dropped_buffer_full']}"
    )
    print(
        f"  buffered_for_retry={e['events_buffered_for_retry']}  "
        f"event_queue max_depth={e['event_queue_max_depth']}/{_fmt(e['event_queue_maxsize'])}"
    )
    print("-" * 72)
    print(" LATENCY (ms)")
    for name, key in (
        ("YOLO detection", "yolo"),
        ("OCR", "ocr"),
        ("Event send (dequeue->POST done)", "send"),
        ("Compute (frame recv->enqueue)", "compute"),
        ("End-to-end (frame recv->delivered)", "end_to_end"),
    ):
        s = report["latency_ms"][key]
        if s["count"] == 0:
            print(f"  {name:<36} no samples")
        else:
            note = f"  [{s['note']}]" if s.get("note") and s["note"] != "no samples" else ""
            print(f"  {name:<36} n={s['count']:<5} avg={s['avg_ms']:<8} p50={s['p50_ms']:<8} p95={s['p95_ms']}{note}")
    print("-" * 72)
    r = report["resource_usage"]
    print(
        f" RESOURCE (n={r['sample_count']} in-run samples)  "
        f"cpu avg={_fmt(r['cpu_percent_avg'], '%')} max={_fmt(r['cpu_percent_max'], '%')}  "
        f"rss max={_fmt(r['rss_mb_max'], 'MB')} (final={_fmt(r['rss_mb_final'], 'MB')})"
    )
    if "pool" in report:
        p = report["pool"]
        print("-" * 72)
        print(f" POOL ({p['num_workers']} workers)  routed={p['frames_routed']} handoff_dropped={p['frames_handoff_dropped']}")
        for wr in p["per_worker_resource_usage"]:
            wid = wr["worker_id"]
            cams = p["worker_assignment"].get(str(wid), p["worker_assignment"].get(wid, []))
            stale_total = sum((p["per_worker_stale_evicted"].get(str(wid)) or p["per_worker_stale_evicted"].get(wid) or {}).values())
            print(
                f"  worker {wid}: cameras={cams} cpu={_fmt(wr.get('cpu_percent'), '%')} "
                f"rss={_fmt(wr.get('rss_mb'), 'MB')} queue_depth={p['per_worker_queue_depth'].get(str(wid), p['per_worker_queue_depth'].get(wid))} "
                f"handoff_drops={p['per_worker_handoff_drops'].get(str(wid), p['per_worker_handoff_drops'].get(wid))} "
                f"stale_evicted_total={stale_total}"
            )
    if "fair_scheduler" in report:
        fs = report["fair_scheduler"]
        print("-" * 72)
        print(f" FAIR SCHEDULER  frames_skipped(sampling)={fs['frames_skipped']}  load_state={fs['load_state']}")
        for cam_id, c in fs["scheduler"]["cameras"].items():
            print(
                f"  {cam_id}: priority={c['priority']} processed={c['frames_processed']} "
                f"dropped={c['frames_dropped_total']} starvation={c['starvation_count']} "
                f"fps={_fmt(c['current_fps'])}"
            )
    print("=" * 72)


def main() -> None:
    ap = argparse.ArgumentParser(description="SENTINEL pipeline benchmark harness (Phase 2A Task 3 / Phase 2C pool)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--camera", help="single camera id")
    g.add_argument("--cameras", help="comma-separated camera ids, e.g. cam04,cam06")
    g.add_argument("--all", action="store_true", help="every camera in the registry")
    ap.add_argument(
        "--registry", default=REGISTRY,
        help="registry file, or a comma-separated list to merge (e.g. real + mock registries)"
    )
    ap.add_argument("--duration", type=float, default=60.0, help="benchmark duration in seconds")
    ap.add_argument("--sample-interval", type=float, default=2.0, help="metrics sampling interval, seconds")
    ap.add_argument(
        "--backend-url",
        default=os.getenv("SENTINEL_BACKEND_URL", "http://localhost:8000/api/v1/events/ai-detection"),
    )
    ap.add_argument("--no-backend", action="store_true", help="dry run: never POST events to a backend")
    ap.add_argument("--ai-workers", type=int, default=int(os.getenv("SENTINEL_AI_WORKERS", "1")),
                    help="number of parallel AI worker processes (default 1 -- pre-Phase-2C behavior)")
    ap.add_argument("--frame-skip", type=int, default=int(os.getenv("FRAME_SKIP", "0")))
    ap.add_argument(
        "--fair-scheduler", action="store_true",
        default=os.getenv("SENTINEL_FAIR_SCHEDULER", "0").lower() in ("1", "true", "yes", "on"),
        help="Phase 17: single-consumer path only -- use ai.scheduled_consumer's fair, "
             "priority-weighted scheduler instead of the plain FIFO FrameConsumer.",
    )
    ap.add_argument(
        "--target-fps", type=float, default=None,
        help="Phase 17: --fair-scheduler only -- default per-camera AdaptiveFrameSampler target FPS.",
    )
    ap.add_argument("--device", default=os.getenv("SENTINEL_AI_DEVICE", "cpu"))
    ap.add_argument("--evidence-dir", default=os.getenv("SENTINEL_EVIDENCE_DIR", "evidence/benchmark"))
    ap.add_argument("--max-queue", type=int, default=500, help="ingestion frame-queue size")
    ap.add_argument("--admin-user", default=os.getenv("ADMIN_USER") or os.getenv("ADMIN_USERNAME", ""))
    ap.add_argument("--admin-password", default=os.getenv("ADMIN_PASSWORD", ""))
    ap.add_argument("--json-out", default=None, help="also write the machine-readable report to this file")
    args = ap.parse_args()
    args.stats_interval = args.sample_interval  # PipelineService's own attribute name

    entries = load_registry(args.registry)
    chosen = select_cameras(entries, args)
    if not chosen:
        service_log.error("no cameras selected")
        sys.exit(2)

    svc = PipelineService(chosen, args)
    sampler = Sampler(svc, interval_s=args.sample_interval)

    service_log.info(
        "benchmark: cameras=%s ai_workers=%d duration=%.0fs backend=%s",
        list(svc.camera_names.keys()), svc.ai_workers, args.duration,
        "disabled (--no-backend)" if args.no_backend else args.backend_url,
    )
    svc.sync_registry_to_backend()
    if svc.pool is not None:
        svc.pool.start()
    else:
        svc.consumer.start()
    svc.manager.sync_cameras(svc.records)
    sampler.start()

    t0 = time.monotonic()
    deadline = t0 + args.duration
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(1.0, remaining))
    except KeyboardInterrupt:
        service_log.info("interrupted, stopping early")
    elapsed = time.monotonic() - t0

    sampler.stop()
    # Snapshot health BEFORE shutdown -- stopping the workers marks every
    # camera OFFLINE, which would otherwise clobber the status it actually
    # had for the whole benchmark run.
    final_health = {m.camera_id: m for m in svc.manager.health.get_snapshot()}
    svc.shutdown()

    report = build_report(svc, sampler, args, elapsed, final_health)
    print_human_report(report)
    print("\n--- JSON ---")
    print(json.dumps(report, indent=2))
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n[benchmark] wrote {args.json_out}")


if __name__ == "__main__":
    main()
