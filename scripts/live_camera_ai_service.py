#!/usr/bin/env python3
"""
GUJARAT SENTINEL — Live Camera & AI micro-service (on-demand, multi-camera).

Standalone "Live Camera & AI" page backend for the real Sentinel RTSP camera
fleet (cam01..cam30, sourced from data/camera_registry.json -- the same
camera_id/name pairs used elsewhere in the project, so the dropdown shows
real names like "01 Chiman bhai Bridge", not synthetic ids).

On-demand connection model (this is the whole point of this revision):
  - At startup, NO camera is connected. The dropdown/camera list is served
    from the registry file alone -- a pure, side-effect-free read.
  - A camera's real RTSP connection is opened ONLY the first time its
    per-camera status or stream endpoint is requested (i.e. the moment a
    user picks it from the dropdown).
  - An idle camera (no request touching it for LIVE_CAMERA_IDLE_TIMEOUT_S)
    is automatically disconnected by a background reaper, freeing that RTSP
    session and its capture thread. Switching the dropdown to a different
    camera therefore costs one new connection, not thirty.
  - Independent per-camera state either way: one camera connecting/failing
    never affects another, exactly as before.

Same pattern as ingestion/stream_health.py's build_health_app(): a small,
optional, local FastAPI app that is NOT mounted into Vanshal's main backend,
kept deliberately isolated so this one feature can be added (or removed)
without touching the rest of SENTINEL.

Reuses, rather than reimplements:
  - data/camera_registry.json                     (camera_id + name + rtsp_url)
  - ingestion.reconnect.ReconnectSupervisor        (2s->4s->8s->16s->30s backoff)
  - ingestion.rtsp_auth                            (credential injection / redaction)
  - ingestion.models.StreamStatus                  (ONLINE / RECONNECTING / OFFLINE)
  - ingestion.config.CONFIG                        (RTSP-over-TCP, open timeout)
  - ai.detection.vehicle_detector.VehicleDetector  (existing YOLOv8 vehicle detector) --
    loaded ONCE (eagerly, in the background, so it's warm by the time a
    camera is first selected) and shared by every camera; never one model
    instance per camera.

Pipeline per active camera (never a desktop cv2.imshow window -- the whole
point of this service is to put the real feed in a browser):

    RTSP camera -> cv2.VideoCapture(url, cv2.CAP_FFMPEG) [forced TCP]
        -> single-slot "latest frame" holder (newest frame always wins,
           no queue / no backlog, so the AI never falls behind live)
        -> (shared, single-threaded, round-robin) VehicleDetector.detect()
        -> boxes + class + confidence drawn on a COPY of the frame
        -> per-camera MJPEG endpoints (raw / annotated) + status JSON

Zero fake data: an unconfigured, not-yet-selected, or unreachable camera
reports its OWN honest OFFLINE (with a real reason); the MJPEG endpoints for
that camera refuse the request -- never a placeholder clip, never simulated
detections, never a fabricated ONLINE, and never falls back to another
camera's feed.

Run:
    python scripts/live_camera_ai_service.py
    # or: uvicorn scripts.live_camera_ai_service:app --host 0.0.0.0 --port 8600

Env (see .env.example):
    LIVE_CAMERA_REGISTRY_PATH    default "<repo>/data/camera_registry.json"
    LIVE_CAMERA_IDLE_TIMEOUT_S   default 60 -- an unused camera connection is
                                  torn down after this many seconds of no
                                  status/stream requests touching it.
    LIVE_CAMERA_REAPER_INTERVAL_S  default 10
    LIVE_CAMERA_HTTP_PORT         default 8600
    LIVE_CAMERA_CORS_ORIGINS      JSON array; default the two local Vite dev origins
    LIVE_CAMERA_CONF_THRESHOLD    default 0.50, passed straight to VehicleDetector
    SENTINEL_RTSP_USERNAME / SENTINEL_RTSP_PASSWORD  (reused from ingestion.rtsp_auth)
"""
from __future__ import annotations

import contextlib
import itertools
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ingestion.config import CONFIG as INGESTION_CONFIG  # noqa: E402
from ingestion.models import StreamStatus  # noqa: E402
from ingestion.reconnect import ReconnectSupervisor  # noqa: E402
from ingestion.rtsp_auth import apply_rtsp_credentials, redact_rtsp_url  # noqa: E402
from ai.detection.vehicle_detector import VehicleDetector  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinel.live_camera_ai")

# RTSP over TCP, same env var ingestion/stream_manager.py sets -- must be in
# place before any cv2.VideoCapture(..., cv2.CAP_FFMPEG) call.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", INGESTION_CONFIG.ffmpeg_capture_options)

HTTP_PORT = int(os.environ.get("LIVE_CAMERA_HTTP_PORT", "8600"))
CONF_THRESHOLD = float(os.environ.get("LIVE_CAMERA_CONF_THRESHOLD", "0.50"))
JPEG_QUALITY = int(os.environ.get("LIVE_CAMERA_JPEG_QUALITY", "80"))
STREAM_FPS_CAP = float(os.environ.get("LIVE_CAMERA_STREAM_FPS_CAP", "12"))
IDLE_TIMEOUT_S = float(os.environ.get("LIVE_CAMERA_IDLE_TIMEOUT_S", "60"))
REAPER_INTERVAL_S = float(os.environ.get("LIVE_CAMERA_REAPER_INTERVAL_S", "10"))
# Round-robin AI pass: if a camera's frame hasn't changed since it was last
# processed, don't waste an inference on it -- move on immediately instead
# of sleeping, so a slow camera never throttles the others' refresh rate.
AI_IDLE_SLEEP_S = float(os.environ.get("LIVE_CAMERA_AI_IDLE_SLEEP_S", "0.05"))

try:
    CORS_ORIGINS = json.loads(os.environ.get("LIVE_CAMERA_CORS_ORIGINS", ""))
    if not isinstance(CORS_ORIGINS, list):
        raise ValueError
except Exception:
    CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]


# --------------------------------------------------------------------------- #
#  Camera fleet configuration -- read from the existing camera registry, not  #
#  hand-duplicated or synthetically generated.                                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CameraSpec:
    camera_id: str            # e.g. "cam01" -- also the RTSP path leaf
    name: str                 # e.g. "01 Chiman bhai Bridge"
    rtsp_url: Optional[str]   # None -> OFFLINE, no fake fallback


def _registry_path() -> str:
    override = os.environ.get("LIVE_CAMERA_REGISTRY_PATH")
    if override:
        return override
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(repo_root, "data", "camera_registry.json")


def build_camera_specs() -> List[CameraSpec]:
    path = _registry_path()
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
    except Exception:
        logger.exception("failed to load camera registry from %s -- no cameras configured", path)
        return []

    specs: List[CameraSpec] = []
    for entry in entries:
        camera_id = entry.get("camera_id")
        if not camera_id:
            continue
        specs.append(CameraSpec(
            camera_id=camera_id,
            name=entry.get("name") or camera_id,
            rtsp_url=entry.get("rtsp_url") or None,
        ))
    return specs


CAMERA_SPECS = build_camera_specs()


class _FrameSlot:
    """Thread-safe single-slot holder: always the newest value, never a
    queue. This is the "prioritise the latest frame, don't accumulate a
    backlog" behaviour -- a slow AI pass just skips whatever frames landed
    while it was busy instead of ever building up a queue."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._at: Optional[float] = None

    def set(self, frame: np.ndarray) -> None:
        with self._lock:
            self._frame = frame
            self._at = time.time()

    def get(self):
        with self._lock:
            return self._frame, self._at

    def clear(self) -> None:
        with self._lock:
            self._frame = None
            self._at = None


class CameraWorker:
    """Owns exactly one camera's real RTSP connection -- but only while it
    is actually being watched. `ensure_started()` opens the connection (a
    no-op if already running); an idle camera is torn down by
    LiveCameraAIManager's reaper via `stop()`. Pure capture -- no AI here;
    detection is done by the shared round-robin AI loop in
    LiveCameraAIManager so N selected cameras never load N copies of the
    model or run N concurrent inferences.

    Mirrors ingestion.stream_manager.StreamWorker's connect/reconnect
    lifecycle (same ReconnectSupervisor, same backoff ladder). Every
    instance is fully independent -- one camera's connection failure/backoff
    can never affect any other camera's worker thread.
    """

    def __init__(self, spec: CameraSpec) -> None:
        self.spec = spec
        self.camera_id = spec.camera_id
        self._lifecycle_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.last_touch: float = 0.0

        self._status = StreamStatus.OFFLINE
        self._status_lock = threading.Lock()
        self._last_error: Optional[str] = (
            None if spec.rtsp_url else "no RTSP URL configured for this camera"
        )
        self.reconnect_count = 0

        self.raw_slot = _FrameSlot()
        self.annotated_slot = _FrameSlot()
        self._detections: List[Dict[str, Any]] = []
        self._detections_lock = threading.Lock()
        self._last_detection_at: Optional[float] = None

    # -- status ------------------------------------------------------------
    def _set_status(self, status: StreamStatus, error: Optional[str] = None) -> None:
        with self._status_lock:
            self._status = status
            if error is not None:
                self._last_error = error
            elif status == StreamStatus.ONLINE:
                self._last_error = None

    def _log(self, level: int, msg: str, *args: Any) -> None:
        logger.log(level, f"[{self.camera_id}] {msg}", *args)

    def touch(self) -> None:
        self.last_touch = time.time()

    def status_snapshot(self) -> Dict[str, Any]:
        with self._status_lock:
            status, error = self._status, self._last_error
        _, raw_at = self.raw_slot.get()
        with self._detections_lock:
            detections = list(self._detections)
            last_det_at = self._last_detection_at
        return {
            "camera_id": self.camera_id,
            "name": self.spec.name,
            "configured": bool(self.spec.rtsp_url),
            "active": self.is_running,
            "status": status.value,
            "last_error": error,
            "last_frame_at": raw_at,
            "reconnect_count": self.reconnect_count,
            "vehicles_detected": len(detections),
            "detections": detections,
            "last_detection_at": last_det_at,
        }

    # -- capture lifecycle ---------------------------------------------------
    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        if not self.spec.rtsp_url:
            return None
        url = apply_rtsp_credentials(self.spec.rtsp_url)
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            self._log(logging.WARNING, "RTSP source did not open (%s)", redact_rtsp_url(url))
            return None
        # Confirm the connection is actually producing frames, not just an
        # open-but-silent socket (same trade-off ingestion/stream_manager.py
        # documents: costs one discarded frame per (re)connect).
        deadline = time.monotonic() + INGESTION_CONFIG.open_timeout_s
        while time.monotonic() < deadline:
            ok, _ = cap.read()
            if ok:
                return cap
            if self._stop_event.wait(0.05):
                cap.release()
                return None
        cap.release()
        return None

    def _release_capture(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:  # noqa: BLE001 -- release must never raise up
                self._log(logging.ERROR, "error releasing capture", exc_info=True)
            self._cap = None

    def _reconnect(self) -> bool:
        self._set_status(StreamStatus.RECONNECTING)
        self._release_capture()

        def on_attempt(attempt: int, delay: float) -> None:
            self.reconnect_count += 1
            self._log(logging.INFO, "reconnect attempt %d, next try in %.0fs", attempt, delay)

        supervisor = ReconnectSupervisor(
            connect_fn=self._open_capture,
            stop_event=self._stop_event,
            ladder=tuple(INGESTION_CONFIG.backoff_ladder_s),
            on_attempt=on_attempt,
        )
        cap = supervisor.run()
        if cap is None:
            self._set_status(
                StreamStatus.OFFLINE,
                error="RTSP connection failed" if self.spec.rtsp_url else "no RTSP URL configured for this camera",
            )
            return False
        self._cap = cap
        self._set_status(StreamStatus.ONLINE)
        self._log(logging.INFO, "connected")
        return True

    def _run(self) -> None:
        if not self.spec.rtsp_url:
            self._log(logging.WARNING, "no RTSP URL configured -- staying OFFLINE")
            return
        self._log(logging.INFO, "capture starting on demand (%s)", redact_rtsp_url(self.spec.rtsp_url))
        if not self._reconnect():
            return
        while not self._stop_event.is_set():
            assert self._cap is not None
            try:
                ok, frame = self._cap.read()
            except Exception as exc:  # noqa: BLE001 -- decoder hiccup, not fatal
                self._log(logging.WARNING, "decode exception, reconnecting: %s", exc)
                ok, frame = False, None
            if not ok or frame is None:
                if not self._reconnect():
                    break
                continue
            self.raw_slot.set(frame)
        self._release_capture()
        self._set_status(StreamStatus.OFFLINE)
        self._log(logging.INFO, "capture stopped")

    # -- on-demand lifecycle -------------------------------------------------
    def ensure_started(self) -> None:
        """Idempotent: opens the real RTSP connection if it isn't already
        running. Called on every status/stream request for this camera --
        this IS the "load only what the user selects" mechanism."""
        self.touch()
        with self._lifecycle_lock:
            if self.is_running or not self.spec.rtsp_url:
                return
            self._stop_event = threading.Event()
            self.is_running = True
            self._thread = threading.Thread(target=self._run, name=f"live-cam-{self.camera_id}", daemon=True)
            self._thread.start()

    def stop(self, join_timeout_s: float = 3.0) -> None:
        """Tears the connection down (called by the idle reaper). Safe to
        call on an already-stopped worker."""
        with self._lifecycle_lock:
            if not self.is_running:
                return
            self._stop_event.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=join_timeout_s)
        with self._lifecycle_lock:
            self.is_running = False
        # Honest reset: a stopped/idle camera reports OFFLINE with no stale
        # frame/detection count left behind implying it's still live.
        self.raw_slot.clear()
        self.annotated_slot.clear()
        with self._detections_lock:
            self._detections = []
            self._last_detection_at = None
        self._set_status(StreamStatus.OFFLINE, error="idle -- not currently selected")
        self._log(logging.INFO, "released (idle timeout)")

    # -- called only by LiveCameraAIManager's single AI thread ---------------
    def apply_detection(self, annotated: np.ndarray, detections: List[Dict[str, Any]]) -> None:
        self.annotated_slot.set(annotated)
        with self._detections_lock:
            self._detections = detections
            self._last_detection_at = time.time()


class LiveCameraAIManager:
    """Owns the whole camera fleet definition (from the registry) plus:
      - ONE shared VehicleDetector and ONE dedicated AI thread that
        round-robins inference across whichever cameras are currently active.
      - ONE idle-reaper thread that disconnects a camera nobody has touched
        (via a status/stream request) for LIVE_CAMERA_IDLE_TIMEOUT_S.

    No camera is ever connected until something asks for it -- see
    CameraWorker.ensure_started().
    """

    def __init__(self, specs: List[CameraSpec]) -> None:
        self.workers: Dict[str, CameraWorker] = {s.camera_id: CameraWorker(s) for s in specs}
        self.specs = specs
        self._stop_event = threading.Event()
        self._ai_thread: Optional[threading.Thread] = None
        self._reaper_thread: Optional[threading.Thread] = None
        self.detector: Optional[VehicleDetector] = None
        self.detector_error: Optional[str] = None
        self._detector_ready = threading.Event()

    def camera_ids(self) -> List[str]:
        return list(self.workers.keys())

    def get(self, camera_id: str) -> Optional[CameraWorker]:
        return self.workers.get(camera_id)

    def ai_state(self) -> str:
        if self.detector_error:
            return "UNAVAILABLE"
        if not self._detector_ready.is_set():
            return "STARTING"
        return "READY"

    # -- lifecycle -------------------------------------------------------------
    def start(self) -> None:
        # No camera workers are started here -- they start on demand (see
        # CameraWorker.ensure_started, called from the per-camera endpoints).
        self._ai_thread = threading.Thread(target=self._ai_loop, name="live-cam-ai-dispatch", daemon=True)
        self._ai_thread.start()
        self._reaper_thread = threading.Thread(target=self._reaper_loop, name="live-cam-idle-reaper", daemon=True)
        self._reaper_thread.start()
        logger.info("manager started: %d camera(s) in registry, none connected yet (on-demand)", len(self.workers))

    def stop(self) -> None:
        self._stop_event.set()
        for worker in self.workers.values():
            worker.stop()
        if self._ai_thread is not None:
            self._ai_thread.join(timeout=5.0)
        if self._reaper_thread is not None:
            self._reaper_thread.join(timeout=REAPER_INTERVAL_S + 2.0)

    # -- idle reaper -----------------------------------------------------------
    def _reaper_loop(self) -> None:
        while not self._stop_event.wait(REAPER_INTERVAL_S):
            now = time.time()
            for worker in self.workers.values():
                if worker.is_running and (now - worker.last_touch) > IDLE_TIMEOUT_S:
                    worker.stop()

    # -- shared round-robin AI loop -------------------------------------------
    def _ai_loop(self) -> None:
        try:
            self.detector = VehicleDetector(conf_threshold=CONF_THRESHOLD, device="cpu")
            self._detector_ready.set()
            logger.info("shared VehicleDetector loaded -- round-robin AI dispatch ready for %d registered camera(s)",
                        len(self.workers))
        except Exception as exc:  # noqa: BLE001 -- AI degrades honestly, never fakes a result
            logger.exception("failed to load shared YOLO vehicle detector")
            self.detector_error = str(exc)
            return

        last_seen_at: Dict[str, float] = {}
        ids = self.camera_ids()
        if not ids:
            return
        idle_streak = 0
        for camera_id in itertools.cycle(ids):
            if self._stop_event.is_set():
                return
            worker = self.workers[camera_id]
            if not worker.is_running:
                idle_streak += 1
                if idle_streak >= len(ids):
                    idle_streak = 0
                    self._stop_event.wait(AI_IDLE_SLEEP_S)
                continue
            frame, at = worker.raw_slot.get()
            if frame is None or at == last_seen_at.get(camera_id):
                idle_streak += 1
                if idle_streak >= len(ids):
                    idle_streak = 0
                    self._stop_event.wait(AI_IDLE_SLEEP_S)
                continue  # this camera has nothing new -- move straight to the next one
            idle_streak = 0
            last_seen_at[camera_id] = at

            try:
                detections = self.detector.detect(frame)
            except Exception:  # noqa: BLE001 -- one bad frame must not kill the AI loop
                logger.exception("[%s] YOLO inference failed on a frame", camera_id)
                continue

            annotated = frame.copy()
            for det in detections:
                x1, y1, x2, y2 = det["bbox"]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (63, 179, 127), 2)
                label = f"{det['class']} {det['confidence']:.2f}"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                ly = max(0, y1 - th - 8)
                cv2.rectangle(annotated, (x1, ly), (x1 + tw + 6, ly + th + 8), (63, 179, 127), -1)
                cv2.putText(annotated, label, (x1 + 3, ly + th + 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2, cv2.LINE_AA)
                logger.debug("[%s] vehicle detected: %s %.2f", camera_id, det["class"], det["confidence"])

            worker.apply_detection(annotated, detections)
        # itertools.cycle over a non-empty list never exits on its own; the
        # `return` above (on stop_event) is the only way out.


manager = LiveCameraAIManager(CAMERA_SPECS)


def _resize_for_output(frame: np.ndarray, max_width: Optional[int]) -> np.ndarray:
    if not max_width or max_width <= 0:
        return frame
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / float(w)
    return cv2.resize(frame, (max_width, max(1, int(h * scale))), interpolation=cv2.INTER_AREA)


async def _mjpeg_generator(request: "Request", worker: "CameraWorker", slot_attr: str,
                            max_width: Optional[int] = None):
    """Multipart JPEG ASYNC generator. Encodes whatever is currently the
    newest frame in the worker's `slot_attr` slot -- never re-encodes/repeats
    a stale frame if the source stalls. Touches the worker on every iteration
    so a long-lived open connection keeps this camera's idle timer from
    expiring even if the client isn't separately polling /status.
    `max_width` optionally downsizes the OUTPUT jpeg only (e.g. for a
    thumbnail) -- detection, when applicable, already ran on the full frame.

    MUST be async (not a plain sync generator): Starlette drives a sync
    generator via a background-threadpool iterator, and a loop that never
    naturally ends (a live MJPEG stream doesn't) never gives that thread
    back -- one browser tab opening and abandoning a few camera views is
    enough to permanently pin threads until the pool is exhausted and every
    later stream, for any camera, just hangs. An async generator instead
    runs on the event loop and explicitly checks `request.is_disconnected()`
    each iteration, so an abandoned connection is detected and this
    coroutine actually exits, freeing everything -- no thread ever leaks."""
    import asyncio

    boundary = b"frame"
    last_at = None
    min_interval = 1.0 / STREAM_FPS_CAP if STREAM_FPS_CAP > 0 else 0.0
    while True:
        if await request.is_disconnected():
            return
        worker.touch()
        frame, at = getattr(worker, slot_attr).get()
        if frame is not None and at != last_at:
            last_at = at
            out = _resize_for_output(frame, max_width)
            ok, buf = await asyncio.to_thread(
                cv2.imencode, ".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            if ok:
                jpg = buf.tobytes()
                yield (
                    b"--" + boundary + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
                    + jpg + b"\r\n"
                )
        await asyncio.sleep(min_interval)


@contextlib.asynccontextmanager
async def lifespan(_app):
    manager.start()
    try:
        yield
    finally:
        manager.stop()


def _build_app():
    app = FastAPI(title="SENTINEL Live Camera & AI (dev, on-demand multi-camera)", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "sentinel-live-camera-ai", "camera_count": len(manager.workers)}

    def _camera_snapshot(camera_id: str) -> Dict[str, Any]:
        worker = manager.get(camera_id)
        if worker is None:
            raise HTTPException(status_code=404, detail={"code": "CAMERA_NOT_FOUND", "camera_id": camera_id})
        snap = worker.status_snapshot()
        ai_state = manager.ai_state()
        if ai_state != "READY" or not snap["active"]:
            snap["ai_status"] = ai_state if ai_state != "READY" else "IDLE"
        elif snap["status"] != StreamStatus.ONLINE.value:
            snap["ai_status"] = "IDLE"
        elif snap["last_detection_at"] and (time.time() - snap["last_detection_at"]) < 5:
            snap["ai_status"] = "PROCESSING"
        else:
            snap["ai_status"] = "IDLE"
        snap["ai_model_error"] = manager.detector_error
        return snap

    @app.get("/api/v1/live-camera/cameras")
    def list_cameras():
        """The full registered camera list (id + real name), for populating
        the selector -- a pure read, never starts a connection. Includes
        each camera's CURRENT status (most will be inactive/OFFLINE until
        selected), so an already-active camera still shows live here too."""
        return {
            "ai_status": manager.ai_state(),
            "ai_model_error": manager.detector_error,
            "camera_count": len(manager.workers),
            "cameras": [_camera_snapshot(cid) for cid in manager.camera_ids()],
        }

    @app.get("/api/v1/live-camera/{camera_id}/status")
    def get_status(camera_id: str):
        """Selecting a camera means polling this endpoint -- it lazily opens
        the real RTSP connection (idempotent) and keeps it alive while
        polled."""
        worker = manager.get(camera_id)
        if worker is None:
            raise HTTPException(status_code=404, detail={"code": "CAMERA_NOT_FOUND", "camera_id": camera_id})
        worker.ensure_started()
        return _camera_snapshot(camera_id)

    def _stream_or_503(request: Request, camera_id: str, slot_attr: str, max_width: Optional[int]):
        worker = manager.get(camera_id)
        if worker is None:
            raise HTTPException(status_code=404, detail={"code": "CAMERA_NOT_FOUND", "camera_id": camera_id})
        worker.ensure_started()
        snap = worker.status_snapshot()
        if snap["status"] == StreamStatus.OFFLINE.value:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "CAMERA_OFFLINE",
                    "message": snap["last_error"] or "Camera is offline",
                    "camera_id": camera_id,
                    "status": snap["status"],
                },
            )
        return StreamingResponse(
            _mjpeg_generator(request, worker, slot_attr, max_width=max_width),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.get("/api/v1/live-camera/{camera_id}/stream/raw.mjpg")
    def stream_raw(request: Request, camera_id: str, w: Optional[int] = Query(default=None, ge=64, le=1920)):
        """The real, unmodified live feed for the selected camera -- the
        "Provided Data / Live Camera" view. `w` optionally caps output width."""
        return _stream_or_503(request, camera_id, "raw_slot", w)

    @app.get("/api/v1/live-camera/{camera_id}/stream/annotated.mjpg")
    def stream_annotated(request: Request, camera_id: str, w: Optional[int] = Query(default=None, ge=64, le=1920)):
        """The same real feed with real YOLO bounding boxes drawn on it --
        the "AI Vehicle Detection" view for the selected camera."""
        return _stream_or_503(request, camera_id, "annotated_slot", w)

    return app


app = _build_app()


if __name__ == "__main__":
    import uvicorn

    configured = sum(1 for s in CAMERA_SPECS if s.rtsp_url)
    print("=================================================================")
    print("  GUJARAT SENTINEL — Live Camera & AI service (on-demand, N-cam)  ")
    print("=================================================================")
    print(f" • Cameras in registry: {configured}/{len(CAMERA_SPECS)}")
    print(f" • Connections opened:  ONLY when a camera is selected")
    print(f" • Idle timeout:        {IDLE_TIMEOUT_S:.0f}s")
    if CAMERA_SPECS:
        print(f" • Example (cam 1):     {CAMERA_SPECS[0].camera_id} ({CAMERA_SPECS[0].name}) -> "
              f"{redact_rtsp_url(CAMERA_SPECS[0].rtsp_url) or '[not configured]'}")
    print(f" • HTTP port:           {HTTP_PORT}")
    print("=================================================================")
    uvicorn.run(app, host="0.0.0.0", port=HTTP_PORT)
