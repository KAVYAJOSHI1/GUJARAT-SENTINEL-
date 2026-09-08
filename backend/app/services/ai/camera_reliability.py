"""
Camera Reliability Intelligence (Phase 14 §9).

Statistics over the EXISTING `camera_health_history` + `cameras` +
`vehicle_events` -- NOT failure prediction. For each camera we compute:

  * disconnect_count       ONLINE -> OFFLINE/DEGRADED transitions in window
  * mean_recovery_seconds  average OFFLINE -> ONLINE gap
  * heartbeat_stale        is the last health push older than the freshness
                           threshold right now
  * fps_current / degraded is stream_fps below FPS_FLOOR
  * detection_rate_drop    recent detections/hour vs the camera's earlier rate
  * reconnect_count        cumulative reconnects reported

  -> health_score      0-100  (weighted, higher = healthier)
  -> reliability_score HIGH | MEDIUM | LOW  (label from the score)
  -> degradation_indicator  a bounded flag + reason list

> This is "Camera Reliability Intelligence", not failure prediction. We do
> not claim a camera *will* fail -- only that its recent behaviour is
> (un)stable, with the evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlmodel import Session

from app.config import settings
from app.models.base import CameraStatus
from app.models.camera import Camera
from app.models.camera_health_history import CameraHealthHistory
from app.models.vehicle_event import VehicleEvent

_STALE_AFTER = timedelta(seconds=20)


class CameraReliabilityService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    def assess_all(self, *, window_hours: Optional[int] = None) -> dict:
        hours = window_hours or settings.CAMERA_RELIABILITY_WINDOW_HOURS
        cams = self.db.execute(select(Camera)).scalars().all()
        assessed = [self._assess(c, hours) for c in cams]
        # worst (lowest score) first; never-reported cameras (score None) last
        assessed.sort(key=lambda a: a["health_score"] if a["health_score"] is not None else 101.0)
        return {
            "generated_at": datetime.utcnow(),
            "window_hours": hours,
            "camera_count": len(assessed),
            "degraded_count": sum(1 for a in assessed if a["degradation_indicator"]),
            "poor_video_count": sum(1 for a in assessed if a["video_quality_label"] == "POOR"),
            "cameras": assessed,
            "note": (
                "Camera Reliability Intelligence -- a statistical view of recent "
                "stability from camera_health_history. NOT a failure prediction. "
                "video_quality_* is a SEPARATE axis: a camera can be online "
                "(reliable) but produce unusable video (poor quality)."
            ),
        }

    def assess_one(self, camera_code: str, *, window_hours: Optional[int] = None) -> Optional[dict]:
        cam = self.db.execute(
            select(Camera).where(Camera.code == camera_code)
        ).scalar_one_or_none()
        if cam is None:
            return None
        return self._assess(cam, window_hours or settings.CAMERA_RELIABILITY_WINDOW_HOURS,
                            include_history=True)

    # ------------------------------------------------------------------ #
    def _assess(self, cam: Camera, hours: int, *, include_history: bool = False) -> dict:
        since = datetime.utcnow() - timedelta(hours=hours)
        history = self.db.execute(
            select(CameraHealthHistory)
            .where(CameraHealthHistory.camera_id == cam.id,
                   CameraHealthHistory.detected_at >= since)
            .order_by(CameraHealthHistory.detected_at.asc())
        ).scalars().all()

        observations: list[str] = []

        # --- disconnects + recovery ---
        disconnects = [h for h in history
                       if h.status in (CameraStatus.OFFLINE, CameraStatus.DEGRADED)
                       and h.previous_status == CameraStatus.ONLINE]
        recoveries = [h for h in history
                      if h.status == CameraStatus.ONLINE
                      and h.previous_status in (CameraStatus.OFFLINE, CameraStatus.DEGRADED)]
        disconnect_count = len(disconnects)
        rec_gaps = []
        for d in disconnects:
            nxt = next((r for r in recoveries if r.detected_at > d.detected_at), None)
            if nxt:
                rec_gaps.append((nxt.detected_at - d.detected_at).total_seconds())
        mean_recovery = round(sum(rec_gaps) / len(rec_gaps), 1) if rec_gaps else None
        if disconnect_count:
            observations.append(
                f"{disconnect_count} disconnect(s) in {hours}h"
                + (f", avg recovery {int(mean_recovery)}s" if mean_recovery else "")
            )

        # --- heartbeat freshness ---
        stale = (
            cam.health_updated_at is not None
            and datetime.utcnow() - cam.health_updated_at > _STALE_AFTER
        )
        never_reported = cam.health_updated_at is None
        if stale:
            age = int((datetime.utcnow() - cam.health_updated_at).total_seconds())
            observations.append(f"last heartbeat {age}s ago (stale)")

        # --- fps ---
        fps = cam.stream_fps
        fps_degraded = fps is not None and fps < settings.CAMERA_RELIABILITY_FPS_FLOOR
        if fps_degraded:
            observations.append(f"stream FPS {fps:.1f} below floor {settings.CAMERA_RELIABILITY_FPS_FLOOR}")

        # --- reconnects ---
        reconnects = cam.reconnect_count or 0
        if reconnects >= settings.CAMERA_RELIABILITY_RECONNECT_WARN:
            observations.append(f"{reconnects} cumulative reconnects reported")

        # --- detection-rate drop (own baseline) ---
        det_recent = int(self.db.execute(
            select(func.count(VehicleEvent.id)).where(
                VehicleEvent.camera_id == cam.id, VehicleEvent.timestamp >= since)
        ).scalar() or 0)

        # --- Phase 15F: VIDEO QUALITY (distinct from reliability/uptime) ---
        vq_row = self.db.execute(
            select(
                func.count(VehicleEvent.id),
                func.count(VehicleEvent.id).filter(VehicleEvent.anpr_status == "OK"),
                func.avg(VehicleEvent.anpr_quality_score),
                func.avg(VehicleEvent.plate_quality),
            ).where(VehicleEvent.camera_id == cam.id, VehicleEvent.timestamp >= since)
        ).one()
        vq_total = int(vq_row[0] or 0)
        vq_ok = int(vq_row[1] or 0)
        anpr_success_rate = round(vq_ok / vq_total, 3) if vq_total else None
        mean_anpr_q = round(float(vq_row[2]), 3) if vq_row[2] is not None else None
        mean_plate_q = round(float(vq_row[3]), 3) if vq_row[3] is not None else None
        prev_since = since - timedelta(hours=hours)
        det_prev = int(self.db.execute(
            select(func.count(VehicleEvent.id)).where(
                VehicleEvent.camera_id == cam.id,
                VehicleEvent.timestamp >= prev_since, VehicleEvent.timestamp < since)
        ).scalar() or 0)
        det_rate_recent = round(det_recent / hours, 2)
        detection_drop = None
        if det_prev >= settings.CAMERA_RELIABILITY_MIN_BASELINE_DETECTIONS:
            change = (det_recent - det_prev) / det_prev
            detection_drop = round(change * 100, 1)
            if change < -0.5:
                observations.append(
                    f"detections down {abs(detection_drop):.0f}% vs the prior {hours}h "
                    f"({det_prev} -> {det_recent})"
                )

        # ---------------- score ----------------
        score = 100.0
        score -= min(45, disconnect_count * settings.CAMERA_RELIABILITY_DISCONNECT_PENALTY)
        if stale:
            score -= 25
        if fps_degraded:
            score -= 15
        if reconnects >= settings.CAMERA_RELIABILITY_RECONNECT_WARN:
            score -= min(15, (reconnects - settings.CAMERA_RELIABILITY_RECONNECT_WARN + 1) * 3)
        if detection_drop is not None and detection_drop < -50:
            score -= 12
        if mean_recovery is not None and mean_recovery > settings.CAMERA_RELIABILITY_SLOW_RECOVERY_S:
            score -= 8
        score = max(0.0, round(score, 1))

        if never_reported:
            reliability = "UNKNOWN"
            observations = ["no health telemetry has ever been received for this camera"]
        elif score >= settings.CAMERA_RELIABILITY_HIGH_SCORE:
            reliability = "HIGH"
        elif score >= settings.CAMERA_RELIABILITY_MEDIUM_SCORE:
            reliability = "MEDIUM"
        else:
            reliability = "LOW"

        degradation = reliability in ("LOW", "MEDIUM") and bool(observations) and not never_reported

        # --- video quality score (0-100): can this camera produce USABLE
        #     video, regardless of whether it is up? ---
        vq_reasons: list[str] = []
        vq_score: Optional[float] = None
        if vq_total >= settings.CAMERA_VIDEO_QUALITY_MIN_SAMPLES:
            s = 100.0
            if anpr_success_rate is not None and anpr_success_rate < 0.6:
                s -= min(45, (0.6 - anpr_success_rate) * 120)
                vq_reasons.append(f"ANPR success {int(anpr_success_rate*100)}% "
                                  f"({vq_ok}/{vq_total} plates readable)")
            if mean_anpr_q is not None and mean_anpr_q < 0.55:
                s -= min(25, (0.55 - mean_anpr_q) * 90)
                vq_reasons.append(f"mean plate-crop quality {mean_anpr_q}")
            if mean_plate_q is not None and mean_plate_q < 0.5:
                s -= 10
                vq_reasons.append(f"mean plate-locator confidence {mean_plate_q}")
            if fps is not None and fps < settings.CAMERA_VIDEO_QUALITY_FPS_NOMINAL:
                s -= min(20, (settings.CAMERA_VIDEO_QUALITY_FPS_NOMINAL - fps) * 2)
                vq_reasons.append(f"stream FPS {fps} below nominal "
                                  f"{settings.CAMERA_VIDEO_QUALITY_FPS_NOMINAL}")
            vq_score = max(0.0, round(s, 1))
        if vq_score is None:
            vq_label = "UNKNOWN"
        elif vq_score >= 80:
            vq_label = "GOOD"
        elif vq_score >= 55:
            vq_label = "FAIR"
        else:
            vq_label = "POOR"

        out = {
            "camera_id": cam.id,
            "camera_code": cam.code,
            "camera_name": cam.name,
            "location_desc": cam.location_desc,
            "current_status": _eff(cam).value,
            "health_score": score if not never_reported else None,
            "reliability_score": reliability,
            "degradation_indicator": degradation,
            "window_hours": hours,
            "disconnect_count": disconnect_count,
            "mean_recovery_seconds": mean_recovery,
            "heartbeat_stale": stale,
            "stream_fps": fps,
            "fps_degraded": fps_degraded,
            "reconnect_count": reconnects,
            "detection_rate_per_hour": det_rate_recent,
            "detection_rate_change_pct": detection_drop,
            "observations": observations,
            # Phase 15F: video quality -- CAN this camera produce usable video,
            # separate from whether it stays online.
            "video_quality_score": vq_score,
            "video_quality_label": vq_label,
            "video_quality_reasons": vq_reasons,
            "anpr_success_rate": anpr_success_rate,
            "mean_plate_quality": mean_plate_q,
            "mean_anpr_quality": mean_anpr_q,
        }
        if include_history:
            out["transitions"] = [{
                "status": h.status.value if hasattr(h.status, "value") else str(h.status),
                "previous_status": (h.previous_status.value if h.previous_status else None),
                "source": h.source,
                "detected_at": h.detected_at,
                "stream_fps": h.stream_fps,
            } for h in history[-50:]]
        return out


def _eff(cam: Camera) -> CameraStatus:
    if cam.health_updated_at is None:
        return cam.status
    if datetime.utcnow() - cam.health_updated_at > _STALE_AFTER:
        return CameraStatus.OFFLINE
    return cam.status
