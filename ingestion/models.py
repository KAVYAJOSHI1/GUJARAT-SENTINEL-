"""
Shared data structures for the ingestion module.

Kept framework-agnostic (plain dataclasses / enums) so Kavya's AI queue
consumer and Vanshal's backend can import these without pulling in
OpenCV or FastAPI as a dependency.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

import numpy as np


class StreamStatus(str, Enum):
    ONLINE = "ONLINE"
    RECONNECTING = "RECONNECTING"
    OFFLINE = "OFFLINE"


@dataclass
class CameraLocation:
    """GPS coordinates as provided by the registry."""

    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass
class CameraRecord:
    """A single validated entry from the camera catalogue.

    Two real sources have been confirmed so far, with genuinely different
    shapes -- this record is a superset of both:

    1. docs/API_CONTRACTS.md#1-camera-registry-api (GET /api/v1/cameras):
       {"camera_id", "name", "department", "location":{lat,lng},
        "stream_url", "stream_protocol", "status"}

    2. https://cctv.corp8.cloud/cameras.json (confirmed live, 2026-09-02):
       a bare list of {"id", "name"} only -- no stream_url, department,
       location, or status at all.

    stream_url is Optional for exactly this reason: source #2 genuinely
    doesn't provide one. A None here means "not yet known", not "empty
    string" or a guessed value -- nothing in this module invents one.
    """

    camera_id: str
    name: Optional[str] = None
    stream_url: Optional[str] = None       # None when the source doesn't provide one (see above)
    stream_protocol: Optional[str] = None  # e.g. "RTSP/TCP", as declared by the registry
    department: Optional[str] = None
    location: Optional[CameraLocation] = None
    codec_hint: Optional[str] = None       # e.g. "h264" / "h265" -- if a source adds it later
    registry_status: Optional[str] = None  # registry's OWN last-known status (e.g. "ONLINE").
    # NOT the same thing as StreamStatus below -- that one is computed live,
    # frame-by-frame, by this module. registry_status is just what the
    # catalogue last reported and may be stale (or, for source #2, absent).
    webrtc_url: Optional[str] = None       # NOT YET in either confirmed source
    hls_url: Optional[str] = None          # NOT YET in either confirmed source
    raw: Dict[str, Any] = field(default_factory=dict)  # original payload, for audit

    @property
    def rtsp_url(self) -> Optional[str]:
        """Alias for stream_url for backwards compatibility."""
        return self.stream_url


@dataclass
class FrameEnvelope:
    """What gets pushed to Kavya's AI queue for every successfully decoded frame."""

    camera_id: str
    frame: np.ndarray
    pts_ms: float          # CAP_PROP_POS_MSEC -- the authoritative timing source
    seq_num: int           # monotonically increasing per connection, for gap detection
    # Local bookkeeping only (e.g. queue latency logging) -- NEVER used for
    # pacing or sequencing. PTS is authoritative per the integration spec.
    received_at_s: float = field(default_factory=time.monotonic)


@dataclass
class StreamMetrics:
    """Per-camera telemetry snapshot."""

    camera_id: str
    status: StreamStatus = StreamStatus.OFFLINE
    measured_fps: float = 0.0
    pts_jitter_ms: float = 0.0
    frame_drop_count: int = 0
    reconnect_count: int = 0
    last_pts_ms: Optional[float] = None
    last_error: Optional[str] = None
    updated_at_s: float = field(default_factory=time.time)
    # Wall-clock duration (seconds) of the most recently completed
    # (re)connect -- from RECONNECTING/first-attempt to ONLINE. None until
    # the first successful connect. Timed with time.monotonic() deltas in
    # StreamWorker._reconnect(), never PTS.
    last_reconnect_duration_s: Optional[float] = None
