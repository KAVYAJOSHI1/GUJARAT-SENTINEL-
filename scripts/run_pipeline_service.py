#!/usr/bin/env python3
"""
SENTINEL ingestion + AI pipeline service — one command to run the whole thing.

    Camera registry
          -> StreamManager.sync_cameras()  -> StreamWorker threads
          -> FrameEnvelope queue
          -> FrameConsumer  -> envelope_to_frame_input()
          -> AIPipeline (YOLO -> plate -> OCR -> consensus -> ByteTrack)
          -> AI events  -> POST /api/v1/events/ai-detection  (X-Ingest-Key)
          -> backend -> watchlist -> alerts

Reuses the existing modules; it does not introduce a parallel architecture.

Phase 2C: with --ai-workers/SENTINEL_AI_WORKERS > 1, the single
FrameConsumer above is replaced by ai/worker_pool.py's camera-sharded,
fair-scheduled multi-process pool instead -- see that module's docstring.
Default (1) is byte-for-byte the diagram above, unchanged.

Usage:
    .venv/bin/python scripts/run_pipeline_service.py --cameras cam04,cam06
    .venv/bin/python scripts/run_pipeline_service.py --all --frame-skip 2
    .venv/bin/python scripts/run_pipeline_service.py --camera cam04 --no-backend --duration 30
    .venv/bin/python scripts/run_pipeline_service.py --all --ai-workers 2

Env:
    SENTINEL_RTSP_USERNAME / SENTINEL_RTSP_PASSWORD   (RTSP Basic auth)
    SENTINEL_BACKEND_URL                              (default http://localhost:8000/api/v1/events/ai-detection)
    SENTINEL_INGEST_API_KEY                           (X-Ingest-Key sent to the backend)
    SENTINEL_RTSP_BASE                                (fallback rtsp base when a camera has no rtsp_url)
    SENTINEL_AI_WORKERS                               (default 1; >1 activates the Phase 2C worker pool)
"""
import argparse
import json
import logging
import os
import queue
import signal
import sys
import threading
import time
from typing import Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests  # noqa: E402

from ai.adapter.ingestion_bridge import FrameConsumer  # noqa: E402
from ai.pipeline import AIPipeline  # noqa: E402
from ai.sampling import SamplingConfig  # noqa: E402
from ai.scheduled_consumer import ScheduledFrameConsumer  # noqa: E402
from ai.worker_pool import AIWorkerPool  # noqa: E402
from ingestion.config import CONFIG  # noqa: E402
from ingestion.models import CameraLocation, CameraRecord  # noqa: E402
from ingestion.rtsp_auth import redact_rtsp_url  # noqa: E402
from ingestion.stream_health import push_loop  # noqa: E402
from ingestion.stream_manager import StreamManager  # noqa: E402

logging.basicConfig(
    level=os.getenv("SENTINEL_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
)
log = logging.getLogger("sentinel.service")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGISTRY = os.path.join(REPO_ROOT, "data", "camera_registry.json")
RTSP_BASE = os.getenv("SENTINEL_RTSP_BASE", "rtsp://103.250.160.189:8554/stream")


def _resolve_source(rtsp: str) -> str:
    """A mock-camera registry may point ``rtsp_url`` at a local video file
    with a repo-relative path (e.g. ``demo_assets/clips/mockcam01.mp4`` in
    data/demo_camera_registry.json). Resolve that against the repo root so
    the pipeline works regardless of the process's CWD; leave real
    ``rtsp://`` / ``http(s)://`` URLs and already-absolute paths untouched."""
    if not rtsp or "://" in rtsp or os.path.isabs(rtsp):
        return rtsp
    candidate = os.path.join(REPO_ROOT, rtsp)
    return candidate if os.path.exists(candidate) else rtsp


# --------------------------------------------------------------------------- #
#  registry -> CameraRecord                                                     #
# --------------------------------------------------------------------------- #
def load_registry(path: str) -> list:
    """Load one registry file, or several merged into one camera list.

    ``path`` may be a comma-separated list, e.g.
    ``"data/camera_registry.json,data/trafficdataset_camera_registry.json"``
    -- this is how real Sentinel cameras (cam04/cam06) and local MOCK_CAM*
    cameras run in the SAME process / SAME AIPipeline instance (see
    scripts/run_mock_cameras.py), which matters: two separate Python
    processes each loading their own AIPipeline (YOLO/torch/OpenCV) have
    been observed to crash on interpreter shutdown on this machine, so
    "real + mock simultaneously" is done as one process with more workers,
    not two competing processes. A single path (the default / existing
    behavior) is unaffected -- it just loads that one file."""
    entries: list = []
    for p in [part.strip() for part in path.split(",") if part.strip()]:
        with open(p) as f:
            entries.extend(json.load(f))
    return entries


def to_camera_record(entry: dict) -> CameraRecord:
    cam_id = str(entry.get("camera_id") or entry.get("id"))
    rtsp = _resolve_source(entry.get("rtsp_url") or f"{RTSP_BASE}/{cam_id}")
    loc = None
    if entry.get("latitude") is not None and entry.get("longitude") is not None:
        loc = CameraLocation(latitude=float(entry["latitude"]), longitude=float(entry["longitude"]))
    return CameraRecord(
        camera_id=cam_id,
        name=entry.get("name"),
        stream_url=rtsp,
        stream_protocol="RTSP/TCP",
        department=entry.get("department"),
        location=loc,
        codec_hint=entry.get("codec"),
        registry_status=entry.get("status"),
        hls_url=entry.get("hls_url"),
        raw=entry,
    )


def select_cameras(entries: list, args) -> list:
    by_id = {str(e.get("camera_id") or e.get("id")): e for e in entries}
    if args.all:
        chosen = list(by_id.values())
    elif args.cameras:
        ids = [c.strip() for c in args.cameras.split(",") if c.strip()]
        chosen = [by_id[i] for i in ids if i in by_id]
        missing = [i for i in ids if i not in by_id]
        if missing:
            log.warning("camera(s) not in registry, skipped: %s", missing)
    elif args.camera:
        chosen = [by_id[args.camera]] if args.camera in by_id else []
    else:
        chosen = [by_id[c] for c in ("cam04", "cam06") if c in by_id]
    return chosen


# --------------------------------------------------------------------------- #
#  service                                                                      #
# --------------------------------------------------------------------------- #
class PipelineService:
    def __init__(self, entries: list, args):
        self.args = args
        self.entries = entries
        self.records = [to_camera_record(e) for e in entries]
        self.camera_names = {r.camera_id: (r.name or r.camera_id) for r in self.records}
        self.backend_events_url = args.backend_url
        self.ingest_key = os.getenv("SENTINEL_INGEST_API_KEY") or os.getenv("INGEST_API_KEY")
        self._stop = threading.Event()

        self.manager = StreamManager(max_queue_size=args.max_queue)

        # Phase 2C: SENTINEL_AI_WORKERS (default 1) selects between the
        # exact pre-Phase-2C single-consumer-thread path (unchanged below)
        # and a camera-sharded multi-process pool (ai/worker_pool.py) that
        # also replaces the plain FIFO frame_queue drain with per-camera
        # fair round-robin scheduling. A camera is assigned to exactly one
        # worker for the pool's lifetime, so its tracker/consensus/cooldown
        # state only ever lives in one process -- see ai/worker_pool.py's
        # module docstring for the full design rationale.
        self.ai_workers = max(1, getattr(args, "ai_workers", 1))
        self.pool: Optional[AIWorkerPool] = None
        self.pipeline: Optional[AIPipeline] = None
        self.consumer: Optional[Any] = None

        # Phase 17: --fair-scheduler / SENTINEL_FAIR_SCHEDULER=1 swaps the
        # plain-FIFO FrameConsumer for ai.scheduled_consumer's bounded,
        # priority-weighted fair scheduler -- same single consumer THREAD
        # (no added CPU parallelism, unlike --ai-workers>1), just a
        # different service order. Only meaningful on the single-consumer
        # path; --ai-workers>1 already has its own (differently-scoped,
        # currently not-recommended-on-constrained-hardware) fairness fix
        # in ai/worker_pool.py, so the two are not combined here.
        self.fair_scheduler = bool(getattr(args, "fair_scheduler", False)) and self.ai_workers <= 1
        if getattr(args, "fair_scheduler", False) and self.ai_workers > 1:
            log.warning("--fair-scheduler is ignored when --ai-workers>1 (ai.worker_pool has its own fairness fix)")

        if self.ai_workers <= 1:
            self.pipeline = AIPipeline(
                backend_url=self.backend_events_url,
                evidence_dir=args.evidence_dir,
                device=args.device,
            )
            if self.ingest_key:
                self.pipeline.ingest_api_key = self.ingest_key
            if args.no_backend:
                # dry run: swallow dispatch so we still exercise detection/OCR/tracking
                self.pipeline._dispatch_event = lambda payload: True

            if self.fair_scheduler:
                self.consumer = ScheduledFrameConsumer(
                    self.manager.frame_queue,
                    self.pipeline,
                    on_events=self._on_events,
                    camera_names=self.camera_names,
                    stop_event=self._stop,
                )
                self._configure_scheduled_cameras()
            else:
                self.consumer = FrameConsumer(
                    self.manager.frame_queue,
                    self.pipeline,
                    on_events=self._on_events,
                    camera_names=self.camera_names,
                    stop_event=self._stop,
                    frame_skip=args.frame_skip,
                )
        else:
            self.pool = AIWorkerPool(
                self.manager.frame_queue,
                [r.camera_id for r in self.records],
                self.ai_workers,
                backend_url=self.backend_events_url,
                ingest_api_key=self.ingest_key,
                evidence_dir=args.evidence_dir,
                device=args.device,
                no_backend=args.no_backend,
                stats_interval=args.stats_interval,
            )

    # -- Phase 17: per-camera priority/mode/sampling from the registry ---- #
    def _configure_scheduled_cameras(self) -> None:
        """Reads optional ``priority`` / ``processing_mode`` / ``target_fps``
        / ``min_fps`` / ``max_fps`` fields from each registry entry (all
        optional -- a registry with none of these fields behaves exactly
        like the plain FrameConsumer path: every camera at NORMAL priority,
        ANPR mode, unrestricted sampling)."""
        assert isinstance(self.consumer, ScheduledFrameConsumer)
        default_target_fps = getattr(self.args, "target_fps", None)
        for e in self.entries:
            cam_id = str(e.get("camera_id") or e.get("id"))
            priority = e.get("priority")
            mode = e.get("processing_mode")
            sampling = None
            target_fps = e.get("target_fps", default_target_fps)
            if target_fps is not None:
                sampling = SamplingConfig(
                    target_fps=float(target_fps),
                    min_fps=float(e.get("min_fps", 0.5)),
                    max_fps=float(e.get("max_fps", max(15.0, float(target_fps) * 3))),
                )
            if priority or mode or sampling:
                self.consumer.configure_camera(cam_id, priority=priority, mode=mode, sampling=sampling)
                log.info(
                    "camera %s: priority=%s mode=%s target_fps=%s",
                    cam_id, priority or "NORMAL (default)", mode or "ANPR (default)", target_fps,
                )

    # -- backend registration ---------------------------------------------- #
    def _api_base(self) -> str:
        return self.backend_events_url.split("/events/ai-detection")[0]

    # -- pipeline metrics push (AIPipeline.get_metrics() -> backend) ------ #
    def _push_pipeline_status(self, metrics: dict, *, processed_fps: float,
                              num_workers: int) -> None:
        """Best-effort POST of the current metrics snapshot to
        `<api base>/pipeline/status` so the command-center dashboard can show
        real processed-FPS / queue-depth / YOLO+OCR latency / per-camera
        processing state (Phase 7). Never raises, never blocks the stats
        loop; skipped entirely on --no-backend."""
        if self.args.no_backend:
            return
        url = f"{self._api_base()}/pipeline/status"
        payload = {
            "service_id": "default",
            "num_workers": num_workers,
            "processed_frames": metrics.get("processed_frames"),
            "processed_fps": round(processed_fps, 2),
            "total_vehicles_detected": metrics.get("total_vehicles_detected"),
            "total_ai_events_generated": metrics.get("total_ai_events_generated"),
            "events_sent_ok": metrics.get("events_sent_ok"),
            "events_dropped": (
                (metrics.get("events_dropped_queue_full") or 0)
                + (metrics.get("events_dropped_backend_rejected") or 0)
                + (metrics.get("events_dropped_buffer_full") or 0)
            ),
            "event_queue_depth": metrics.get("event_queue_depth"),
            "event_queue_max_depth": metrics.get("event_queue_max_depth"),
            "yolo_latency_ms": metrics.get("yolo_latency_ms")
            or metrics.get("combined_latency", {}).get("yolo_latency_ms"),
            "ocr_latency_ms": metrics.get("ocr_latency_ms")
            or metrics.get("combined_latency", {}).get("ocr_latency_ms"),
            "cpu_percent": metrics.get("resource_usage", {}).get("cpu_percent"),
            "rss_mb": metrics.get("resource_usage", {}).get("rss_mb"),
            "frames_by_camera": metrics.get("frames_by_camera") or {},
            "events_by_camera": metrics.get("events_by_camera") or {},
        }
        headers = {"X-Ingest-Key": self.ingest_key} if self.ingest_key else None
        try:
            requests.post(url, json=payload, headers=headers, timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            log.debug("pipeline status push to %s failed: %s", url, exc)

    def sync_registry_to_backend(self) -> None:
        if self.args.no_backend:
            return
        base = self._api_base()
        try:
            tok = None
            if self.args.admin_user and self.args.admin_password:
                r = requests.post(f"{base}/auth/login",
                                  json={"username": self.args.admin_user, "password": self.args.admin_password},
                                  timeout=10)
                if r.ok:
                    tok = r.json().get("access_token")
            headers = {"Authorization": f"Bearer {tok}"} if tok else {}
            payload = [
                {
                    "camera_id": e.get("camera_id") or e.get("id"),
                    "name": e.get("name"),
                    "latitude": e.get("latitude"),
                    "longitude": e.get("longitude"),
                    "rtsp_url": e.get("rtsp_url"),
                    "resolved_address": e.get("resolved_address"),
                    "status": e.get("status"),
                }
                for e in self.entries
            ]
            r = requests.post(f"{base}/cameras/sync", json=payload, headers=headers, timeout=20)
            if r.ok:
                log.info("POST /cameras/sync -> %s (%s cameras)", r.status_code, r.json().get("synced"))
            else:
                log.warning("POST /cameras/sync -> %s %s (continuing; auto-onboard will handle it)",
                            r.status_code, r.text[:120])
        except Exception as exc:  # noqa: BLE001
            log.warning("camera registry sync skipped (%s)", exc)

    # -- event callback (single-worker path only) ------------------------ #
    def _on_events(self, camera_id: str, events: list) -> None:
        # Dispatch is async now (Task 2) -- events_buffer here reflects the
        # RETRY backlog only, not "in flight, not yet attempted" (those are
        # in the event queue, see get_metrics()['event_queue_depth']).
        for ev in events:
            plate = ev.get("license_plate", {}).get("plate_number", "?")
            log.info("AI event  cam=%s track=%s plate=%s queued=%d buffered=%d",
                     camera_id, ev.get("track_id"),
                     plate, self.pipeline.get_metrics()["event_queue_depth"],
                     len(self.pipeline.event_buffer))

    # -- unified frame/event counters (both paths) ------------------------ #
    def _total_frames_processed(self) -> int:
        return self.consumer.frames_processed if self.consumer else (self.pool.get_metrics()["processed_frames"] if self.pool else 0)

    def _total_frames_skipped(self) -> int:
        return self.consumer.frames_skipped if self.consumer else 0  # pool has no frame-skip sampling (Task 2C out of scope)

    def _total_events_emitted(self) -> int:
        return self.consumer.events_emitted if self.consumer else (self.pool.get_metrics()["total_ai_events_generated"] if self.pool else 0)

    # -- stats loop ---------------------------------------------------- #
    def _stats_loop(self) -> None:
        if self.pool is not None:
            self._stats_loop_pool()
        else:
            self._stats_loop_single()

    def _stats_loop_single(self) -> None:
        interval = self.args.stats_interval
        last_frames = 0
        while not self._stop.wait(interval):
            snap = {m.camera_id: m for m in self.manager.health.get_snapshot()}
            metrics = self.pipeline.get_metrics()
            fps = (self.consumer.frames_processed - last_frames) / max(interval, 1e-9)
            last_frames = self.consumer.frames_processed
            res = metrics["resource_usage"]
            log.info(
                "STATS | consumed=%d skipped=%d fps=%.1f | vehicles=%d events=%d "
                "yolo=%.0fms(p95=%s) ocr=%.0fms(p95=%s) | "
                "queue=%d/%d(max %d) sent=%d q_full_drop=%d rejected=%d retry_buf=%d | "
                "cpu=%s%% rss=%sMB",
                self.consumer.frames_processed, self.consumer.frames_skipped, fps,
                metrics["total_vehicles_detected"], metrics["total_ai_events_generated"],
                metrics["avg_vehicle_detection_ms"], metrics["yolo_latency_ms"]["p95_ms"],
                metrics["avg_ocr_ms"], metrics["ocr_latency_ms"]["p95_ms"],
                metrics["event_queue_depth"], metrics["event_queue_maxsize"], metrics["event_queue_max_depth"],
                metrics["events_sent_ok"], metrics["events_dropped_queue_full"],
                metrics["events_dropped_backend_rejected"], metrics["events_buffered_for_retry"],
                res["cpu_percent"], res["rss_mb"],
            )
            for cam_id in self.camera_names:
                m = snap.get(cam_id)
                if m:
                    log.info("  cam %s status=%s fps=%.1f drops=%d reconnects=%d last_reconnect=%ss "
                             "frames=%d events=%d",
                             cam_id, m.status.value, m.measured_fps, m.frame_drop_count, m.reconnect_count,
                             round(m.last_reconnect_duration_s, 1) if m.last_reconnect_duration_s else "n/a",
                             metrics["frames_by_camera"].get(cam_id, 0),
                             metrics["events_by_camera"].get(cam_id, 0))
            self._push_pipeline_status(metrics, processed_fps=fps, num_workers=1)

    def _stats_loop_pool(self) -> None:
        interval = self.args.stats_interval
        last_frames = 0
        while not self._stop.wait(interval):
            snap = {m.camera_id: m for m in self.manager.health.get_snapshot()}
            metrics = self.pool.get_metrics()
            frames_now = metrics["processed_frames"]
            fps = (frames_now - last_frames) / max(interval, 1e-9)
            last_frames = frames_now
            log.info(
                "STATS(pool=%d workers) | processed=%d fps=%.1f | events=%d sent=%d "
                "q_full_drop=%d rejected=%d retry_buf=%d | routed=%d handoff_drop=%d",
                metrics["num_workers"], frames_now, fps,
                metrics["total_ai_events_generated"], metrics["events_sent_ok"],
                metrics["events_dropped_queue_full"], metrics["events_dropped_backend_rejected"],
                metrics["events_buffered_for_retry"], metrics["frames_routed"], metrics["frames_handoff_dropped"],
            )
            for w in metrics["per_worker_resource_usage"]:
                log.info("  worker %d: cpu=%s%% rss=%sMB queue_depth=%d handoff_drops=%d cameras=%s",
                         w["worker_id"], w.get("cpu_percent"), w.get("rss_mb"),
                         metrics["per_worker_queue_depth"].get(w["worker_id"], 0),
                         metrics["per_worker_handoff_drops"].get(w["worker_id"], 0),
                         metrics["worker_assignment"].get(w["worker_id"], []))
            for cam_id in self.camera_names:
                m = snap.get(cam_id)
                if m:
                    stale = sum(s.get(cam_id, 0) for s in metrics["per_worker_stale_evicted"].values())
                    log.info("  cam %s status=%s fps=%.1f drops=%d reconnects=%d "
                             "frames=%d events=%d stale_evicted=%d",
                             cam_id, m.status.value, m.measured_fps, m.frame_drop_count, m.reconnect_count,
                             metrics["frames_by_camera"].get(cam_id, 0),
                             metrics["events_by_camera"].get(cam_id, 0), stale)
            # normalise the pool snapshot to the single-pipeline metric names
            # the push helper expects
            _cl = metrics.get("combined_latency", {})
            _res = (metrics.get("per_worker_resource_usage") or [{}])
            self._push_pipeline_status(
                {
                    "processed_frames": frames_now,
                    "total_vehicles_detected": metrics.get("total_ai_events_generated"),
                    "total_ai_events_generated": metrics.get("total_ai_events_generated"),
                    "events_sent_ok": metrics.get("events_sent_ok"),
                    "events_dropped_queue_full": metrics.get("events_dropped_queue_full"),
                    "events_dropped_backend_rejected": metrics.get("events_dropped_backend_rejected"),
                    "events_dropped_buffer_full": metrics.get("events_dropped_buffer_full"),
                    "event_queue_depth": sum(metrics.get("per_worker_queue_depth", {}).values()) or None,
                    "event_queue_max_depth": metrics.get("event_queue_max_depth"),
                    "yolo_latency_ms": _cl.get("yolo_latency_ms"),
                    "ocr_latency_ms": _cl.get("ocr_latency_ms"),
                    "resource_usage": {
                        "cpu_percent": sum(w.get("cpu_percent") or 0 for w in _res) or None,
                        "rss_mb": sum(w.get("rss_mb") or 0 for w in _res) or None,
                    },
                    "frames_by_camera": metrics.get("frames_by_camera"),
                    "events_by_camera": metrics.get("events_by_camera"),
                },
                processed_fps=fps,
                num_workers=metrics.get("num_workers", 1),
            )

    # -- stream health push (HealthRegistry -> backend camera status) ---- #
    def _health_push_url(self) -> str | None:
        """Where to POST HealthRegistry snapshots so real stream health
        actually reaches `cameras.status` (SENTINEL_System_Audit_Report.md
        §11/§15). Defaults to the same backend this pipeline already POSTs
        detections to (`<api base>/cameras/health`) so it works out of the
        box in the docker-compose demo with no extra env var; set
        SENTINEL_HEALTH_PUSH_URL="" explicitly to disable it, or to another
        URL to override it. Never pushed at all in --no-backend dry runs."""
        if self.args.no_backend:
            return None
        if CONFIG.health_push_url is not None:
            return CONFIG.health_push_url
        if os.environ.get("SENTINEL_HEALTH_PUSH_URL", None) == "":
            return None  # explicitly disabled
        return f"{self._api_base()}/cameras/health"

    def _start_health_push(self) -> None:
        url = self._health_push_url()
        if not url:
            return
        headers = {"X-Ingest-Key": self.ingest_key} if self.ingest_key else None
        threading.Thread(
            target=push_loop,
            args=(self.manager.health, url, CONFIG.health_push_interval_s, self._stop),
            kwargs={"headers": headers},
            name="health-push",
            daemon=True,
        ).start()
        log.info("stream health push -> %s every %.0fs", url, CONFIG.health_push_interval_s)

    # -- lifecycle --------------------------------------------------- #
    def start(self) -> None:
        log.info("cameras: %s", [r.camera_id for r in self.records])
        for r in self.records:
            log.info("  %s -> %s (%s)", r.camera_id, redact_rtsp_url(r.stream_url), r.codec_hint)

        self.sync_registry_to_backend()
        if self.pool is not None:
            self.pool.start()
        else:
            self.consumer.start()
        self.manager.sync_cameras(self.records)
        threading.Thread(target=self._stats_loop, name="stats", daemon=True).start()
        self._start_health_push()

        supervise_interval = 15.0
        deadline = time.time() + self.args.duration if self.args.duration else None
        while not self._stop.wait(supervise_interval):
            self.manager.sync_cameras(self.records)  # restarts dead workers
            if deadline and time.time() >= deadline:
                log.info("duration reached, shutting down")
                break
        self.shutdown()

    def shutdown(self) -> None:
        if self._stop.is_set() and not self.manager.active_camera_ids():
            return
        log.info("shutting down...")
        self._stop.set()
        self.manager.stop_all(join_timeout_s=5.0)
        if self.pool is not None:
            try:
                self.pool.shutdown(timeout=15.0)
            except Exception:  # noqa: BLE001
                log.exception("worker pool shutdown failed")
        else:
            self.consumer.join(timeout=5.0)
            try:
                left = self.pipeline.flush_events()
                log.info("final flush: %d events still buffered", left)
            except Exception:  # noqa: BLE001
                pass
            try:
                # Graceful drain (Task 2): stop the background sender thread,
                # moving anything still stuck in its queue into the retry
                # buffer rather than losing it on process exit.
                still_buffered = self.pipeline.shutdown(drain_timeout=5.0)
                if still_buffered:
                    log.warning("%d event(s) never delivered before shutdown", still_buffered)
            except Exception:  # noqa: BLE001
                pass
        log.info("stopped. frames processed=%d, AI events=%d",
                 self._total_frames_processed(), self._total_events_emitted())


def main():
    ap = argparse.ArgumentParser(description="SENTINEL ingestion + AI pipeline service")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--camera", help="single camera id")
    g.add_argument("--cameras", help="comma-separated camera ids")
    g.add_argument("--all", action="store_true", help="every camera in the registry")
    ap.add_argument("--registry", default=REGISTRY,
                    help="registry file, or a comma-separated list of registry files to merge "
                         "(e.g. data/camera_registry.json,data/trafficdataset_camera_registry.json "
                         "to run real Sentinel + MOCK_CAM* cameras together)")
    ap.add_argument("--backend-url",
                    default=os.getenv("SENTINEL_BACKEND_URL",
                                      "http://localhost:8000/api/v1/events/ai-detection"))
    ap.add_argument("--no-backend", action="store_true", help="run pipeline without POSTing events")
    ap.add_argument("--ai-workers", type=int, default=int(os.getenv("SENTINEL_AI_WORKERS", "1")),
                    help="number of parallel AI worker processes, camera-sharded (default 1 -- "
                         "preserves the exact pre-Phase-2C single-consumer-thread behavior)")
    ap.add_argument("--frame-skip", type=int, default=int(os.getenv("FRAME_SKIP", "0")))
    ap.add_argument(
        "--fair-scheduler", action="store_true",
        default=os.getenv("SENTINEL_FAIR_SCHEDULER", "0").lower() in ("1", "true", "yes", "on"),
        help="Phase 17: single-consumer path only (--ai-workers=1, default) -- swap the plain FIFO "
             "FrameConsumer for ai.scheduled_consumer's bounded, priority-weighted fair scheduler + "
             "adaptive sampling. Same one consumer thread, no added CPU parallelism.",
    )
    ap.add_argument(
        "--target-fps", type=float, default=None,
        help="Phase 17: --fair-scheduler only -- default per-camera AdaptiveFrameSampler target FPS "
             "for any camera whose registry entry doesn't specify its own target_fps.",
    )
    ap.add_argument("--device", default=os.getenv("SENTINEL_AI_DEVICE", "cpu"))
    ap.add_argument("--evidence-dir", default=os.getenv("SENTINEL_EVIDENCE_DIR", "evidence/live"))
    ap.add_argument("--max-queue", type=int, default=500)
    ap.add_argument("--stats-interval", type=float, default=10.0)
    ap.add_argument("--duration", type=float, default=0.0, help="auto-stop after N seconds (0 = run forever)")
    ap.add_argument("--admin-user",
                    default=os.getenv("ADMIN_USER") or os.getenv("ADMIN_USERNAME", ""))
    ap.add_argument("--admin-password", default=os.getenv("ADMIN_PASSWORD", ""))
    args = ap.parse_args()

    entries = load_registry(args.registry)
    chosen = select_cameras(entries, args)
    if not chosen:
        log.error("no cameras selected")
        sys.exit(2)

    svc = PipelineService(chosen, args)

    def _sig(_signum, _frame):
        log.info("signal received")
        svc.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    svc.start()


if __name__ == "__main__":
    main()
