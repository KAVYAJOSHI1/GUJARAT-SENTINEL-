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
  4. An optional push loop that POSTs snapshots to Vanshal's backend if
     SENTINEL_HEALTH_PUSH_URL is configured.

*** SCHEMA PLACEHOLDER -- READ THIS ***
The exact wire schema for GET /api/v1/streams/health lives in
docs/API_CONTRACTS.md#5-camera-telemetry--health-schema, owned by
Vanshal, which hasn't been shared into this session yet. The dict shape
returned by `build_health_app()` and `push_loop()` below is a reasonable
placeholder based on what the execution guide asks for (status, FPS, PTS
jitter, frame drop count). Once you paste the real contract, only the
two small dict-building blocks marked "PLACEHOLDER SHAPE" need to
change -- all measurement, storage, and threading logic stays the same.
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
            pts_deltas = [b - a for a, b in zip(history, history[1:])]
            avg_delta_ms = sum(pts_deltas) / len(pts_deltas)
            self.metrics.measured_fps = 1000.0 / avg_delta_ms if avg_delta_ms > 0 else 0.0
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
        # PLACEHOLDER SHAPE -- replace with docs/API_CONTRACTS.md#5 once shared.
        return {
            "streams": [
                {
                    "camera_id": m.camera_id,
                    "status": m.status.value,
                    "fps": round(m.measured_fps, 2),
                    "pts_jitter_ms": round(m.pts_jitter_ms, 2),
                    "frame_drop_count": m.frame_drop_count,
                    "reconnect_count": m.reconnect_count,
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
) -> None:
    """POSTs periodic health snapshots to Vanshal's backend, if configured.

    Runs in its own thread; never raises -- network errors are logged and
    the loop keeps going on the next interval.
    """
    import requests

    while not stop_event.wait(interval_s):
        try:
            snapshot = registry.get_snapshot()
            payload = {
                # PLACEHOLDER SHAPE -- replace with docs/API_CONTRACTS.md#5 once shared.
                "streams": [
                    {
                        "camera_id": m.camera_id,
                        "status": m.status.value,
                        "fps": round(m.measured_fps, 2),
                        "pts_jitter_ms": round(m.pts_jitter_ms, 2),
                        "frame_drop_count": m.frame_drop_count,
                        "reconnect_count": m.reconnect_count,
                    }
                    for m in snapshot
                ]
            }
            requests.post(push_url, json=payload, timeout=5.0)
        except Exception as exc:  # noqa: BLE001 -- never let telemetry push kill the loop
            logger.warning("Health push to %s failed: %s", push_url, exc)
