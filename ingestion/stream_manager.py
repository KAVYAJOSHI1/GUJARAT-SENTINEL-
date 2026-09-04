"""
Multi-threaded RTSP stream worker pool.

One StreamWorker thread per camera. Each worker:
  - relies on RTSP-over-TCP being forced globally (module-level env var,
    set once at import time -- see the OPENCV_FFMPEG_CAPTURE_OPTIONS line
    below)
  - opens the feed via cv2.VideoCapture(url, cv2.CAP_FFMPEG)
  - reads frames in a tight loop, tagging each with its PTS
    (CAP_PROP_POS_MSEC) -- never FPS, never wall-clock time
  - on read failure, hands off to a ReconnectSupervisor with the shared
    backoff ladder, without crashing the thread or the process
  - pushes successfully decoded frames to an output queue (consumed by
    Kavya's AI pipeline) and updates the shared HealthRegistry
  - releases its VideoCapture on stop, always -- never writes frames to
    disk and never calls back into the camera / gateway control plane
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Dict, Iterable, List, Optional

import cv2

from .config import CONFIG
from .models import CameraRecord, FrameEnvelope, StreamStatus
from .reconnect import ReconnectSupervisor
from .rtsp_auth import apply_rtsp_credentials, redact_rtsp_url
from .stream_health import HealthRegistry

logger = logging.getLogger("sentinel.ingestion.stream_manager")

# Must be set before any cv2.VideoCapture(...) call that uses the FFmpeg
# backend. Doing this at import time (rather than per-worker) keeps every
# thread consistent and stops a future contributor from "forgetting" to
# force TCP transport in some code path.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", CONFIG.ffmpeg_capture_options)


class StreamWorker(threading.Thread):
    """Owns exactly one camera's live RTSP connection for its whole lifetime."""

    def __init__(
        self,
        camera: CameraRecord,
        frame_queue: "queue.Queue[FrameEnvelope]",
        health: HealthRegistry,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        super().__init__(name=f"stream-worker-{camera.camera_id}", daemon=True)
        self.camera = camera
        self._frame_queue = frame_queue
        self._health = health
        self._stop_event = stop_event or threading.Event()
        self._seq_num = 0
        self._cap: Optional[cv2.VideoCapture] = None

    def stop(self) -> None:
        self._stop_event.set()

    # -- connection lifecycle -------------------------------------------------

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        """Attempt one connection. Returns the opened capture, or None on
        failure. This is the `connect_fn` handed to ReconnectSupervisor.

        Note: we discard the first successfully-read frame here as part of
        confirming the connection is actually producing frames (an
        open-but-silent socket is still a failed connection). This costs
        one frame per (re)connect, which is an accepted trade-off -- see
        README for details.
        """
        # RTSP first (with env / inline Basic-auth credentials injected), then
        # the camera's HLS URL as a fallback if the registry provides one.
        candidates = []
        if self.camera.stream_url:
            candidates.append(("rtsp", apply_rtsp_credentials(self.camera.stream_url)))
        if getattr(self.camera, "hls_url", None):
            candidates.append(("hls", self.camera.hls_url))
        if not candidates:
            logger.warning("Camera %s has no stream_url / hls_url configured", self.camera.camera_id)
            return None

        for kind, url in candidates:
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap.release()
                logger.debug(
                    "Camera %s: %s source did not open (%s)",
                    self.camera.camera_id, kind, redact_rtsp_url(url),
                )
                continue

            deadline = time.monotonic() + CONFIG.open_timeout_s
            while time.monotonic() < deadline:
                ok, _ = cap.read()
                if ok:
                    if kind != "rtsp":
                        logger.info("Camera %s: connected via %s fallback", self.camera.camera_id, kind)
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
                logger.exception("Error releasing capture for camera %s", self.camera.camera_id)
            self._cap = None

    def _reconnect(self) -> bool:
        self._health.on_status(self.camera.camera_id, StreamStatus.RECONNECTING)
        self._release_capture()

        def on_attempt(attempt: int, delay: float) -> None:
            logger.info(
                "Camera %s: reconnect attempt %d, next try in %.0fs",
                self.camera.camera_id, attempt, delay,
            )

        supervisor = ReconnectSupervisor(
            connect_fn=self._open_capture,
            stop_event=self._stop_event,
            ladder=tuple(CONFIG.backoff_ladder_s),
            on_attempt=on_attempt,
        )
        cap = supervisor.run()
        if cap is None:
            # Only happens if stop_event fired mid-retry (graceful shutdown).
            self._health.on_status(self.camera.camera_id, StreamStatus.OFFLINE)
            return False

        self._cap = cap
        self._seq_num = 0  # new connection = new sequence / possible discontinuity
        self._health.on_status(self.camera.camera_id, StreamStatus.ONLINE)
        logger.info("Camera %s: reconnected", self.camera.camera_id)
        return True

    # -- main loop -------------------------------------------------------------

    def run(self) -> None:
        logger.info(
            "Starting worker for camera %s (%s)",
            self.camera.camera_id,
            redact_rtsp_url(self.camera.stream_url),
        )

        if not self._reconnect():
            return  # stopped before ever connecting

        while not self._stop_event.is_set():
            assert self._cap is not None
            try:
                ok, frame = self._cap.read()
            except Exception as exc:  # noqa: BLE001 -- decoder hiccup, not fatal
                logger.warning(
                    "Camera %s: decode exception, treating as dropped frame: %s",
                    self.camera.camera_id, exc,
                )
                self._health.on_frame_drop(self.camera.camera_id)
                ok, frame = False, None

            if not ok or frame is None:
                # A single failed read (e.g. before the first keyframe of a
                # GOP) is normal per the integration spec. cv2 read()
                # returning False is our sole reconnect trigger -- we don't
                # try to interpret FFmpeg's stderr decoder warnings.
                self._health.on_frame_drop(self.camera.camera_id)
                if not self._reconnect():
                    break
                continue

            pts_ms = self._cap.get(cv2.CAP_PROP_POS_MSEC)
            self._seq_num += 1
            envelope = FrameEnvelope(
                camera_id=self.camera.camera_id,
                frame=frame,
                pts_ms=pts_ms,
                seq_num=self._seq_num,
            )
            self._health.on_frame(self.camera.camera_id, pts_ms)

            try:
                self._frame_queue.put(envelope, timeout=1.0)
            except queue.Full:
                # Never block a live feed indefinitely on a slow consumer --
                # drop the frame and count it, per the "pace your load" rule.
                logger.warning(
                    "Camera %s: frame queue full, dropping frame", self.camera.camera_id
                )
                self._health.on_frame_drop(self.camera.camera_id)

        self._release_capture()
        self._health.on_status(self.camera.camera_id, StreamStatus.OFFLINE)
        logger.info("Worker for camera %s stopped", self.camera.camera_id)


class StreamManager:
    """Owns the pool of StreamWorker threads, one per onboarded camera."""

    def __init__(
        self,
        frame_queue: Optional["queue.Queue[FrameEnvelope]"] = None,
        health: Optional[HealthRegistry] = None,
        max_queue_size: int = 500,
    ) -> None:
        self.frame_queue: "queue.Queue[FrameEnvelope]" = frame_queue or queue.Queue(
            maxsize=max_queue_size
        )
        self.health = health or HealthRegistry(window_size=CONFIG.telemetry_window_size)
        self._workers: Dict[str, StreamWorker] = {}
        self._lock = threading.Lock()

    def sync_cameras(self, cameras: Iterable[CameraRecord]) -> None:
        """Reconcile the running worker pool against a fresh catalogue read:
        start workers for new cameras, stop workers for removed ones. Never
        touches workers for cameras that are unchanged, so a re-poll never
        interrupts a healthy stream."""
        incoming = {c.camera_id: c for c in cameras}

        with self._lock:
            for camera_id in list(self._workers):
                worker = self._workers[camera_id]
                removed = camera_id not in incoming or not incoming[camera_id].stream_url
                dead = not worker.is_alive()
                if removed:
                    logger.info("Camera %s removed or has no stream URL, stopping worker", camera_id)
                    self._workers.pop(camera_id).stop()
                elif dead:
                    # A worker thread that exited on its own (unrecoverable open
                    # failure) -- drop it so the loop below restarts it. Other
                    # cameras are unaffected.
                    logger.warning("Camera %s worker died, will restart", camera_id)
                    self._workers.pop(camera_id, None)

            for camera_id, camera in incoming.items():
                if not camera.stream_url:
                    self.health.on_status(camera_id, StreamStatus.OFFLINE, error="No stream URL provided")
                    continue
                if camera_id not in self._workers:
                    logger.info("Camera %s onboarded, starting worker", camera_id)
                    worker = StreamWorker(camera, self.frame_queue, self.health)
                    self._workers[camera_id] = worker
                    worker.start()

    def stop_all(self, join_timeout_s: float = 5.0) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for w in workers:
            w.stop()
        for w in workers:
            w.join(timeout=join_timeout_s)

    def active_camera_ids(self) -> List[str]:
        with self._lock:
            return list(self._workers.keys())
