"""
Stream telemetry & health tracking.

Ownership note: per the execution guide, this module does NOT own a
database or the production REST server (that's Vanshal's FastAPI
backend). What it owns is:

  1. An in-memory, thread-safe HealthRegistry that StreamWorkers update
     on every frame / status change.
  2. A read-only snapshot API (`get_snapshot`) that Vanshal's backend can
     import and mount directly, or poll.
  3. An optional local FastAPI app exposing GET /api/v1/streams/health,
     useful for local development / Isha's frontend during integration
     testing before Vanshal's backend is wired up.
  4. An optional push loop that POSTs snapshots to the real backend
     endpoint, ``POST /api/v1/cameras/health``
     (``backend/app/api/v1/cameras.py::push_camera_health``), if
     SENTINEL_HEALTH_PUSH_URL is configured (defaults to
     ``<backend base>/cameras/health`` when unset -- see
     ``scripts/run_pipeline_service.py``).

This used to target a placeholder URL with no matching backend route
(SENTINEL_System_Audit_Report.md §11 "health-push endpoint... hasn't been
shared into this session yet"); ``push_camera_health`` now really exists,
and the payload shape below matches its ``CameraHealthPush`` schema
field-for-field. ``build_health_app()`` below is still a separate,
optional local dev server (not mounted into the real backend) -- useful
for polling health directly without a database round-trip during local
development.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from statistics import pstdev
from typing import Deque, Dict, List, Optional

from .models import StreamMetrics, StreamStatus

logger = logging.getLogger("sentinel.ingestion.health")


class _CameraTelemetry:
    """Internal rolling-window bookkeeping for a single camera."""

    def __init__(self, camera_id: str, window_size: int) -> None:
        self.camera_id = camera_id
        self.window_size = window_size
        self.pts_history: Deque[float] = deque(maxlen=window_size)
        self.metrics = StreamMetrics(camera_id=camera_id)

    def record_frame(self, pts_ms: float) -> None:
        if self.pts_history:
            last_pts = self.pts_history[-1]
            delta = pts_ms - last_pts
            if delta > 0:
                self.pts_history.append(pts_ms)
            else:
                # Non-monotonic PTS means a discontinuity (reconnect, loop
                # point, GOP rewind) -- don't let it corrupt the jitter
                # window, just start a fresh window from this frame.
                logger.debug(
                    "Camera %s: non-monotonic PTS (%.1f -> %.1f), treating as discontinuity",
                    self.camera_id, last_pts, pts_ms,
                )
                self.pts_history.clear()
                self.pts_history.append(pts_ms)
        else:
            self.pts_history.append(pts_ms)

        if len(self.pts_history) >= 2:
            history = list(self.pts_history)
            # Ignore sub-millisecond / non-positive gaps (H.265 B-frame PTS
            # reordering can produce them) so measured_fps stays sane.
            pts_deltas = [b - a for a, b in zip(history, history[1:]) if (b - a) >= 1.0]
            if pts_deltas:
                avg_delta_ms = sum(pts_deltas) / len(pts_deltas)
                fps = 1000.0 / avg_delta_ms if avg_delta_ms > 0 else 0.0
                self.metrics.measured_fps = min(fps, 240.0)  # clamp to a plausible ceiling
                self.metrics.pts_jitter_ms = pstdev(pts_deltas) if len(pts_deltas) > 1 else 0.0

        self.metrics.last_pts_ms = pts_ms
        self.metrics.status = StreamStatus.ONLINE
        self.metrics.updated_at_s = time.time()

    def record_frame_drop(self) -> None:
        self.metrics.frame_drop_count += 1
        self.metrics.updated_at_s = time.time()

    def record_status(self, status: StreamStatus, error: Optional[str] = None) -> None:
        self.metrics.status = status
        if status == StreamStatus.RECONNECTING:
            self.metrics.reconnect_count += 1
        if error is not None:
            self.metrics.last_error = error
        self.metrics.updated_at_s = time.time()


class HealthRegistry:
    """Thread-safe registry of per-camera telemetry.

    One instance is shared across all StreamWorkers in the process.
    """

    def __init__(self, window_size: int = 60) -> None:
        self._window_size = window_size
        self._lock = threading.Lock()
        self._cameras: Dict[str, _CameraTelemetry] = {}

    def _get_or_create(self, camera_id: str) -> _CameraTelemetry:
        telem = self._cameras.get(camera_id)
        if telem is None:
            telem = _CameraTelemetry(camera_id, self._window_size)
            self._cameras[camera_id] = telem
        return telem

    def on_frame(self, camera_id: str, pts_ms: float) -> None:
        with self._lock:
            self._get_or_create(camera_id).record_frame(pts_ms)

    def on_frame_drop(self, camera_id: str) -> None:
        with self._lock:
            self._get_or_create(camera_id).record_frame_drop()

    def on_status(self, camera_id: str, status: StreamStatus, error: Optional[str] = None) -> None:
        with self._lock:
            self._get_or_create(camera_id).record_status(status, error)

    def on_reconnect_duration(self, camera_id: str, duration_s: float) -> None:
        """Record how long the most recently completed (re)connect took,
        wall-clock, timed by the caller with time.monotonic() deltas --
        Task 1 "reconnect count/time" (count was already tracked via
        on_status(..., RECONNECTING); this adds the missing duration)."""
        with self._lock:
            self._get_or_create(camera_id).metrics.last_reconnect_duration_s = duration_s

    def remove(self, camera_id: str) -> None:
        with self._lock:
            self._cameras.pop(camera_id, None)

    def get_snapshot(self) -> List[StreamMetrics]:
        """Returns a point-in-time copy -- safe to serialize outside the lock."""
        with self._lock:
            return [StreamMetrics(**vars(t.metrics)) for t in self._cameras.values()]


# --- Optional local FastAPI exposure -----------------------------------
# Import of fastapi is local/lazy so this module has zero hard dependency
# on it for teams that only need the HealthRegistry in-process.

def build_health_app(registry: HealthRegistry):
    """Returns a FastAPI app exposing GET /api/v1/streams/health."""
    from fastapi import FastAPI

    app = FastAPI(title="SENTINEL Stream Health (dev)")

    @app.get("/api/v1/streams/health")
    def get_health():
        return {
            "streams": [
                {
                    "camera_id": m.camera_id,
                    "status": m.status.value,
                    "fps": round(m.measured_fps, 2),
                    "pts_jitter_ms": round(m.pts_jitter_ms, 2),
                    "frame_drop_count": m.frame_drop_count,
                    "reconnect_count": m.reconnect_count,
                    "last_reconnect_duration_s": m.last_reconnect_duration_s,
                    "last_error": m.last_error,
                    "updated_at": m.updated_at_s,
                }
                for m in registry.get_snapshot()
            ]
        }

    return app


def push_loop(
    registry: HealthRegistry,
    push_url: str,
    interval_s: float,
    stop_event: threading.Event,
    headers: Optional[Dict[str, str]] = None,
) -> None:
    """POSTs periodic health snapshots to the backend's
    ``POST /api/v1/cameras/health`` (``CameraHealthPush`` schema), if
    configured.

    Runs in its own thread; never raises -- network errors are logged and
    the loop keeps going on the next interval. This never touches the AI
    inference hot path: it lives entirely on its own daemon thread, reading
    only a point-in-time copy of the registry (`get_snapshot()`), so a slow
    or unreachable backend can only ever delay the NEXT telemetry push, not
    a single frame of detection.

    ``headers`` carries auth (e.g. ``{"X-Ingest-Key": ...}``) -- callers are
    responsible for not logging it; this function never logs `headers`.
    """
    import requests

    while not stop_event.wait(interval_s):
        try:
            snapshot = registry.get_snapshot()
            payload = {
                "streams": [
                    {
                        "camera_id": m.camera_id,
                        "status": m.status.value,
                        "fps": round(m.measured_fps, 2),
                        "pts_jitter_ms": round(m.pts_jitter_ms, 2),
                        "frame_drop_count": m.frame_drop_count,
                        "reconnect_count": m.reconnect_count,
                        "last_reconnect_duration_s": m.last_reconnect_duration_s,
                        "last_error": m.last_error,
                    }
                    for m in snapshot
                ]
            }
            requests.post(push_url, json=payload, headers=headers, timeout=5.0)
        except Exception as exc:  # noqa: BLE001 -- never let telemetry push kill the loop
            logger.warning("Health push to %s failed: %s", push_url, exc)
