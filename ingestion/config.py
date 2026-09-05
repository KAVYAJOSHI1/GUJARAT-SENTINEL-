"""
Runtime configuration for the SENTINEL stream ingestion module.

All values can be overridden via environment variables so the same
codebase runs unchanged across dev / staging / production without
touching source.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class IngestionConfig:
    # Where an external government camera inventory is published, for the
    # optional standalone catalogue-poll path (ingestion/catalogue_ingest.py).
    # The live pipeline normally syncs the local registry straight to the
    # backend via POST /api/v1/cameras/sync instead.
    catalogue_url: str = os.environ.get(
        "SENTINEL_CATALOGUE_URL", "http://localhost:8000/api/v1/cameras/sync"
    )
    # How often (seconds) to re-poll the catalogue for added/removed cameras.
    catalogue_poll_interval_s: float = _env_float("SENTINEL_CATALOGUE_POLL_INTERVAL", 60.0)

    # Backoff ladder in seconds, per spec: 2 -> 4 -> 8 -> 16 -> 30 (then cap).
    backoff_ladder_s: List[float] = field(
        default_factory=lambda: [2.0, 4.0, 8.0, 16.0, 30.0]
    )

    # RTSP over TCP is mandatory (never UDP) per the integration spec.
    ffmpeg_capture_options: str = "rtsp_transport;tcp"

    # Sliding window size (frame count) used to compute measured FPS / PTS jitter.
    telemetry_window_size: int = _env_int("SENTINEL_TELEMETRY_WINDOW", 60)

    # If a worker gets no successful frame read within this many seconds of
    # opening a connection, treat the connection attempt as failed.
    open_timeout_s: float = _env_float("SENTINEL_OPEN_TIMEOUT", 10.0)

    # Optional: where to push health snapshots (Vanshal's backend). If unset,
    # telemetry stays in-memory / served only via the local dev health API.
    health_push_url: Optional[str] = os.environ.get("SENTINEL_HEALTH_PUSH_URL") or None
    health_push_interval_s: float = _env_float("SENTINEL_HEALTH_PUSH_INTERVAL", 5.0)


CONFIG = IngestionConfig()
