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

Usage:
    .venv/bin/python scripts/run_pipeline_service.py --cameras cam04,cam06
    .venv/bin/python scripts/run_pipeline_service.py --all --frame-skip 2
    .venv/bin/python scripts/run_pipeline_service.py --camera cam04 --no-backend --duration 30

Env:
    SENTINEL_RTSP_USERNAME / SENTINEL_RTSP_PASSWORD   (RTSP Basic auth)
    SENTINEL_BACKEND_URL                              (default http://localhost:8000/api/v1/events/ai-detection)
    SENTINEL_INGEST_API_KEY                           (X-Ingest-Key sent to the backend)
    SENTINEL_RTSP_BASE                                (fallback rtsp base when a camera has no rtsp_url)
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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests  # noqa: E402

from ai.adapter.ingestion_bridge import FrameConsumer  # noqa: E402
from ai.pipeline import AIPipeline  # noqa: E402
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

REGISTRY = os.path.join(os.path.dirname(__file__), "..", "data", "camera_registry.json")
RTSP_BASE = os.getenv("SENTINEL_RTSP_BASE", "rtsp://103.250.160.189:8554/stream")


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
    rtsp = entry.get("rtsp_url") or f"{RTSP_BASE}/{cam_id}"
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
        self.backend_ok = 0
        self.backend_fail = 0

        self.manager = StreamManager(max_queue_size=args.max_queue)
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

        self.consumer = FrameConsumer(
            self.manager.frame_queue,
            self.pipeline,
            on_events=self._on_events,
            camera_names=self.camera_names,
            stop_event=self._stop,
            frame_skip=args.frame_skip,
        )

    # -- backend registration ---------------------------------------------- #
    def _api_base(self) -> str:
        return self.backend_events_url.split("/events/ai-detection")[0]

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

    # -- event callback -------------------------------------------------- #
    def _on_events(self, camera_id: str, events: list) -> None:
        for ev in events:
            plate = ev.get("license_plate", {}).get("plate_number", "?")
            log.info("AI event  cam=%s track=%s plate=%s buffered=%d",
                     camera_id, ev.get("track_id"), plate, len(self.pipeline.event_buffer))
        # delivery status is inferred from the pipeline buffer
        self.backend_ok = self.pipeline.stats["total_detections"] - len(self.pipeline.event_buffer)
        self.backend_fail = len(self.pipeline.event_buffer)

    # -- stats loop ---------------------------------------------------- #
    def _stats_loop(self) -> None:
        interval = self.args.stats_interval
        last_frames = 0
        while not self._stop.wait(interval):
            snap = {m.camera_id: m for m in self.manager.health.get_snapshot()}
            bs = self.pipeline.get_benchmark_stats()
            fps = (self.consumer.frames_processed - last_frames) / max(interval, 1e-9)
            last_frames = self.consumer.frames_processed
            log.info(
                "STATS | consumed=%d skipped=%d fps=%.1f | vehicles=%d events=%d "
                "yolo=%.0fms ocr=%.0fms | backend_ok~%d buffered=%d",
                self.consumer.frames_processed, self.consumer.frames_skipped, fps,
                bs["total_vehicles_detected"], bs["total_ai_events_generated"],
                bs["avg_vehicle_detection_ms"], bs["avg_ocr_ms"],
                max(0, self.backend_ok), self.backend_fail,
            )
            for cam_id in self.camera_names:
                m = snap.get(cam_id)
                if m:
                    log.info("  cam %s status=%s fps=%.1f drops=%d reconnects=%d",
                             cam_id, m.status.value, m.measured_fps, m.frame_drop_count, m.reconnect_count)

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
        self.consumer.join(timeout=5.0)
        try:
            left = self.pipeline.flush_events()
            log.info("final flush: %d events still buffered", left)
        except Exception:  # noqa: BLE001
            pass
        log.info("stopped. frames processed=%d, AI events=%d",
                 self.consumer.frames_processed, self.consumer.events_emitted)


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
    ap.add_argument("--frame-skip", type=int, default=int(os.getenv("FRAME_SKIP", "0")))
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
