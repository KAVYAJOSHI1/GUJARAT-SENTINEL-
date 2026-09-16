#!/usr/bin/env python3
"""
GUJARAT SENTINEL — Live Camera & AI micro-service (single real camera).

Standalone "Live Camera & AI" page backend for exactly ONE real RTSP
camera (CAM_AHM_001 by default). Same pattern as
ingestion/stream_health.py's build_health_app(): a small, optional, local
FastAPI app that is NOT mounted into Vanshal's main backend, kept
deliberately isolated so this one feature can be added (or removed)
without touching the rest of SENTINEL.

Reuses, rather than reimplements:
  - ingestion.reconnect.ReconnectSupervisor        (2s->4s->8s->16s->30s backoff)
  - ingestion.rtsp_auth                            (credential injection / redaction)
  - ingestion.models.StreamStatus                  (ONLINE / RECONNECTING / OFFLINE)
  - ingestion.config.CONFIG                        (RTSP-over-TCP, open timeout)
  - ai.detection.vehicle_detector.VehicleDetector  (existing YOLOv8 vehicle detector)

Pipeline (never a desktop cv2.imshow window -- the whole point of this
service is to put the real feed in a browser):

    RTSP camera -> cv2.VideoCapture(url, cv2.CAP_FFMPEG) [forced TCP]
        -> single-slot "latest frame" holder (newest frame always wins,
           no queue / no backlog, so the AI never falls behind live)
        -> VehicleDetector.detect() (unmodified existing model)
        -> boxes + class + confidence drawn on a COPY of the frame
        -> two MJPEG endpoints (raw / annotated) + one JSON status endpoint

Zero fake data: if LIVE_CAMERA_RTSP_URL is unset, or the camera can't be
opened, status is honestly OFFLINE/RECONNECTING (with a real reason) and
the MJPEG endpoints refuse the request -- never a placeholder clip, never
simulated detections, never a fabricated ONLINE.

Run:
    python scripts/live_camera_ai_service.py
    # or: uvicorn scripts.live_camera_ai_service:app --host 0.0.0.0 --port 8600

Env (see .env.example):
    LIVE_CAMERA_ID              default "CAM_AHM_001"
    LIVE_CAMERA_RTSP_URL        required to actually connect; blank -> OFFLINE
    LIVE_CAMERA_HTTP_PORT       default 8600
    LIVE_CAMERA_CORS_ORIGINS    JSON array; default the two local Vite dev origins
    LIVE_CAMERA_CONF_THRESHOLD  default 0.50, passed straight to VehicleDetector
    SENTINEL_RTSP_USERNAME / SENTINEL_RTSP_PASSWORD  (reused from ingestion.rtsp_auth)
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

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

CAMERA_ID = os.environ.get("LIVE_CAMERA_ID", "CAM_AHM_001")
RTSP_URL = os.environ.get("LIVE_CAMERA_RTSP_URL") or None
HTTP_PORT = int(os.environ.get("LIVE_CAMERA_HTTP_PORT", "8600"))
CONF_THRESHOLD = float(os.environ.get("LIVE_CAMERA_CONF_THRESHOLD", "0.50"))
JPEG_QUALITY = int(os.environ.get("LIVE_CAMERA_JPEG_QUALITY", "80"))
STREAM_FPS_CAP = float(os.environ.get("LIVE_CAMERA_STREAM_FPS_CAP", "15"))

try:
    CORS_ORIGINS = json.loads(os.environ.get("LIVE_CAMERA_CORS_ORIGINS", ""))
    if not isinstance(CORS_ORIGINS, list):
        raise ValueError
except Exception:
    CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]


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


class LiveCameraAIWorker:
    """Owns the one real RTSP connection for CAMERA_ID, plus the AI
    detection loop over its latest frame.

    Mirrors ingestion.stream_manager.StreamWorker's connect/reconnect
    lifecycle (same ReconnectSupervisor, same backoff ladder) without
    pulling in the full multi-camera StreamManager: this service is scoped
    to exactly one camera by design (see task constraint), so a second,
    simpler single-camera loop is clearer than repurposing the multi-camera
    pool manager for a pool of one.
    """

    def __init__(self, camera_id: str, rtsp_url: Optional[str]) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self._stop_event = threading.Event()
        self._cap: Optional[cv2.VideoCapture] = None

        self._status = StreamStatus.OFFLINE
        self._status_lock = threading.Lock()
        self._last_error: Optional[str] = (
            None if rtsp_url else "LIVE_CAMERA_RTSP_URL is not configured"
        )
        self.reconnect_count = 0

        self.raw_slot = _FrameSlot()
        self.annotated_slot = _FrameSlot()
        self._detections: List[Dict[str, Any]] = []
        self._detections_lock = threading.Lock()
        self._last_detection_at: Optional[float] = None

        self._detector: Optional[VehicleDetector] = None
        self._detector_error: Optional[str] = None

        self._capture_thread: Optional[threading.Thread] = None
        self._ai_thread: Optional[threading.Thread] = None

    # -- status ------------------------------------------------------------
    def _set_status(self, status: StreamStatus, error: Optional[str] = None) -> None:
        with self._status_lock:
            self._status = status
            if error is not None:
                self._last_error = error
            elif status == StreamStatus.ONLINE:
                self._last_error = None

    def status_snapshot(self) -> Dict[str, Any]:
        with self._status_lock:
            status, error = self._status, self._last_error
        _, raw_at = self.raw_slot.get()
        with self._detections_lock:
            detections = list(self._detections)
            last_det_at = self._last_detection_at

        if self._detector_error:
            ai_status = "UNAVAILABLE"
        elif self._detector is None:
            ai_status = "STARTING"
        elif status == StreamStatus.ONLINE and raw_at and (time.time() - raw_at) < 5:
            ai_status = "PROCESSING"
        else:
            ai_status = "IDLE"

        return {
            "camera_id": self.camera_id,
            "configured": bool(self.rtsp_url),
            "status": status.value,
            "last_error": error,
            "last_frame_at": raw_at,
            "reconnect_count": self.reconnect_count,
            "ai_status": ai_status,
            "ai_model_error": self._detector_error,
            "vehicles_detected": len(detections),
            "detections": detections,
            "last_detection_at": last_det_at,
            "note": (
                "status reflects the real RTSP connection state; ONLINE only "
                "appears once a live frame has actually been decoded."
            ),
        }

    # -- capture lifecycle ---------------------------------------------------
    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        if not self.rtsp_url:
            return None
        url = apply_rtsp_credentials(self.rtsp_url)
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            logger.warning(
                "Camera %s: RTSP source did not open (%s)",
                self.camera_id, redact_rtsp_url(url),
            )
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
                logger.exception("Error releasing capture for %s", self.camera_id)
            self._cap = None

    def _reconnect(self) -> bool:
        self._set_status(StreamStatus.RECONNECTING)
        self._release_capture()

        def on_attempt(attempt: int, delay: float) -> None:
            self.reconnect_count += 1
            logger.info(
                "Camera %s: reconnect attempt %d, next try in %.0fs",
                self.camera_id, attempt, delay,
            )

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
                error="RTSP connection failed" if self.rtsp_url else "LIVE_CAMERA_RTSP_URL is not configured",
            )
            return False
        self._cap = cap
        self._set_status(StreamStatus.ONLINE)
        logger.info("Camera %s: connected", self.camera_id)
        return True

    def _capture_loop(self) -> None:
        if not self.rtsp_url:
            logger.warning("Camera %s: LIVE_CAMERA_RTSP_URL not set -- staying OFFLINE", self.camera_id)
            return
        logger.info("Camera %s: capture loop starting (%s)", self.camera_id, redact_rtsp_url(self.rtsp_url))
        if not self._reconnect():
            return
        while not self._stop_event.is_set():
            assert self._cap is not None
            try:
                ok, frame = self._cap.read()
            except Exception as exc:  # noqa: BLE001 -- decoder hiccup, not fatal
                logger.warning("Camera %s: decode exception, reconnecting: %s", self.camera_id, exc)
                ok, frame = False, None
            if not ok or frame is None:
                if not self._reconnect():
                    break
                continue
            self.raw_slot.set(frame)
        self._release_capture()
        self._set_status(StreamStatus.OFFLINE)
        logger.info("Camera %s: capture loop stopped", self.camera_id)

    # -- AI loop -------------------------------------------------------------
    def _ai_loop(self) -> None:
        try:
            self._detector = VehicleDetector(conf_threshold=CONF_THRESHOLD, device="cpu")
        except Exception as exc:  # noqa: BLE001 -- AI degrades honestly, never fakes a result
            logger.exception("Camera %s: failed to load YOLO vehicle detector", self.camera_id)
            self._detector_error = str(exc)
            return

        last_seen_at = None
        while not self._stop_event.is_set():
            frame, at = self.raw_slot.get()
            if frame is None or at == last_seen_at:
                self._stop_event.wait(0.05)
                continue
            last_seen_at = at  # always the newest frame -- never a backlog
            try:
                detections = self._detector.detect(frame)
            except Exception:  # noqa: BLE001 -- one bad frame must not kill the AI loop
                logger.exception("Camera %s: YOLO inference failed on a frame", self.camera_id)
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

            self.annotated_slot.set(annotated)
            with self._detections_lock:
                self._detections = detections
                self._last_detection_at = time.time()

    # -- lifecycle -------------------------------------------------------------
    def start(self) -> None:
        self._capture_thread = threading.Thread(
            target=self._capture_loop, name=f"live-cam-{self.camera_id}", daemon=True
        )
        self._capture_thread.start()
        self._ai_thread = threading.Thread(
            target=self._ai_loop, name=f"live-cam-ai-{self.camera_id}", daemon=True
        )
        self._ai_thread.start()

    def stop(self, join_timeout_s: float = 3.0) -> None:
        self._stop_event.set()
        for t in (self._capture_thread, self._ai_thread):
            if t is not None:
                t.join(timeout=join_timeout_s)


worker = LiveCameraAIWorker(CAMERA_ID, RTSP_URL)


def _mjpeg_generator(slot: "_FrameSlot"):
    """Multipart JPEG generator. Encodes whatever is currently the newest
    frame in `slot` -- never re-encodes/repeats a stale frame if the source
    stalls (a stalled camera just means the browser stops receiving new
    parts, which is honest: it should NOT keep looping old footage)."""
    boundary = b"frame"
    last_at = None
    min_interval = 1.0 / STREAM_FPS_CAP if STREAM_FPS_CAP > 0 else 0.0
    while True:
        frame, at = slot.get()
        if frame is not None and at != last_at:
            last_at = at
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                jpg = buf.tobytes()
                yield (
                    b"--" + boundary + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
                    + jpg + b"\r\n"
                )
        time.sleep(min_interval)


@contextlib.asynccontextmanager
async def lifespan(_app):
    worker.start()
    try:
        yield
    finally:
        worker.stop()


def _build_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse

    app = FastAPI(title="SENTINEL Live Camera & AI (dev)", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "sentinel-live-camera-ai", "camera_id": CAMERA_ID}

    @app.get("/api/v1/live-camera/status")
    def get_status():
        return worker.status_snapshot()

    def _stream_or_503(slot: "_FrameSlot"):
        snap = worker.status_snapshot()
        if snap["status"] == StreamStatus.OFFLINE.value:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "CAMERA_OFFLINE",
                    "message": snap["last_error"] or "Camera is offline",
                    "camera_id": CAMERA_ID,
                    "status": snap["status"],
                },
            )
        return StreamingResponse(
            _mjpeg_generator(slot),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.get("/api/v1/live-camera/stream/raw.mjpg")
    def stream_raw():
        """The real, unmodified live feed -- the "Provided Data / Live
        Camera" section."""
        return _stream_or_503(worker.raw_slot)

    @app.get("/api/v1/live-camera/stream/annotated.mjpg")
    def stream_annotated():
        """The same real feed with real YOLO bounding boxes drawn on it --
        the "AI Vehicle Detection" section."""
        return _stream_or_503(worker.annotated_slot)

    return app


app = _build_app()


if __name__ == "__main__":
    import uvicorn

    print("=================================================================")
    print("   GUJARAT SENTINEL — Live Camera & AI service (single camera)   ")
    print("=================================================================")
    print(f" • Camera ID:  {CAMERA_ID}")
    print(f" • RTSP URL:   {redact_rtsp_url(RTSP_URL) or '[not configured -- status will be OFFLINE]'}")
    print(f" • HTTP port:  {HTTP_PORT}")
    print("=================================================================")
    uvicorn.run(app, host="0.0.0.0", port=HTTP_PORT)
