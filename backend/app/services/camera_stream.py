"""
Camera playback abstraction (Phase 15A).

`CameraStreamService.profile(camera)` resolves, for one camera, the ordered
list of sources a browser can actually play, plus an honest playback
`mode`:

  LIVE      -- a real-time source (WHEP / HLS) is configured AND the camera
               is ONLINE with fresh health.
  DEGRADED  -- a real-time source exists but health is stale / FPS is low,
               OR only a non-real-time source (recorded clip) is available
               while the camera reports ONLINE.
  RECORDED  -- no live source; a mock/simulated clip or a recent evidence
               snapshot is the best we have.
  OFFLINE   -- the camera is OFFLINE and there is nothing to show but an old
               snapshot (or nothing at all).

The fallback order the frontend player walks is: webrtc -> hls ->
recorded-clip -> latest-snapshot. A snapshot is NEVER presented as a live
feed -- its source `kind` is "snapshot" and the mode reflects reality.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlmodel import Session

from app.config import settings
from app.models.base import CameraStatus
from app.models.camera import Camera
from app.models.vehicle_event import VehicleEvent

_MOCK_RE = re.compile(r"^mock[_-]?cam", re.IGNORECASE)
_HEALTH_STALE = timedelta(seconds=20)
_SNAPSHOT_FRESH = timedelta(minutes=10)


class CameraStreamService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    def _effective_status(self, cam: Camera) -> CameraStatus:
        if cam.health_updated_at is None:
            return cam.status
        if datetime.utcnow() - cam.health_updated_at > _HEALTH_STALE:
            return CameraStatus.OFFLINE
        return cam.status

    def _latest_detection(self, cam: Camera):
        return self.db.execute(
            select(VehicleEvent.id, VehicleEvent.timestamp, VehicleEvent.snapshot_url)
            .where(VehicleEvent.camera_id == cam.id)
            .order_by(desc(VehicleEvent.timestamp))
            .limit(1)
        ).first()

    # ------------------------------------------------------------------ #
    def profile(self, cam: Camera) -> dict:
        is_mock = bool(cam.code and _MOCK_RE.match(cam.code))
        is_demo = bool(getattr(cam, "is_demo", False))
        feed = "DEMO" if is_demo else ("MOCK" if is_mock else "REAL")
        eff = self._effective_status(cam)
        health_fresh = (
            cam.health_updated_at is not None
            and datetime.utcnow() - cam.health_updated_at <= _HEALTH_STALE
        )
        fps = cam.stream_fps
        low_fps = fps is not None and fps < settings.STREAM_LOW_FPS

        det = self._latest_detection(cam)
        last_event_id = det[0] if det else None
        last_detection_at = det[1] if det else None
        last_snapshot_url = det[2] if det and det[2] else None

        sources: list[dict] = []
        if cam.webrtc_url:
            sources.append({"kind": "webrtc", "url": cam.webrtc_url, "realtime": True,
                            "label": "WebRTC (WHEP) — low latency"})
        if cam.hls_url:
            sources.append({"kind": "hls", "url": cam.hls_url, "realtime": True,
                            "label": "HLS"})
        # recorded / simulated clip (the existing mock-video endpoint)
        if is_mock or (cam.rtsp_url and _is_local_clip(cam.rtsp_url)):
            sources.append({
                "kind": "recorded",
                "url": f"{settings.API_V1_PREFIX}/cameras/{cam.id}/mock-video",
                "realtime": False,
                "label": "Recorded / simulated clip",
            })
        if last_event_id:
            fresh = (
                last_detection_at is not None
                and datetime.utcnow() - last_detection_at <= _SNAPSHOT_FRESH
            )
            sources.append({
                "kind": "snapshot",
                "url": f"{settings.API_V1_PREFIX}/vehicles/evidence/{last_event_id}",
                "realtime": False,
                "label": "Latest detection frame" + ("" if fresh else " (stale)"),
            })

        has_realtime = any(s["realtime"] for s in sources)
        has_any = bool(sources)
        # raw operator/onboard status -- a definitive "this camera is down"
        raw_offline = cam.status == CameraStatus.OFFLINE

        if has_realtime and not raw_offline and health_fresh and not low_fps:
            mode = "LIVE"
        elif has_realtime and not raw_offline:
            mode = "DEGRADED"
        elif has_any:
            mode = "RECORDED"
        else:
            mode = "OFFLINE"

        reasons: list[str] = []
        if mode == "DEGRADED":
            if not health_fresh:
                reasons.append("no fresh health telemetry — the stream may be stalled")
            if low_fps:
                reasons.append(f"stream FPS {fps} is below {settings.STREAM_LOW_FPS}")
            if not reasons:
                reasons.append("a real-time source is configured but its health is uncertain")
        if mode == "RECORDED":
            if has_realtime:
                reasons.append("camera is marked OFFLINE — showing recorded material only")
            else:
                reasons.append("no real-time browser source configured for this camera")
        if mode == "OFFLINE":
            reasons.append("camera is offline and no playable source is available")

        ai_status = "PROCESSING" if (last_detection_at is not None
                                     and datetime.utcnow() - last_detection_at <= timedelta(minutes=5)) \
            else ("IDLE" if last_detection_at is not None else "NO DATA")

        return {
            "camera_id": cam.id,
            "camera_code": cam.code,
            "camera_name": cam.name,
            "location_desc": cam.location_desc,
            "is_mock": is_mock,
            "is_demo": is_demo,
            "feed_source": feed,
            "effective_status": eff.value,
            "mode": mode,
            "mode_reasons": reasons,
            "sources": sources,
            "primary_source": sources[0]["kind"] if sources else None,
            "stream_fps": fps,
            "last_frame_at": cam.health_updated_at,
            "last_detection_at": last_detection_at,
            "ai_status": ai_status,
            "reconnect_count": cam.reconnect_count,
            "note": (
                "A snapshot is never a live feed. 'LIVE' means a real-time "
                "WebRTC/HLS source with fresh telemetry; otherwise the mode "
                "reflects exactly what is being shown."
            ),
        }


def _is_local_clip(url: Optional[str]) -> bool:
    if not url:
        return False
    return not url.startswith(("rtsp://", "http://", "https://"))
