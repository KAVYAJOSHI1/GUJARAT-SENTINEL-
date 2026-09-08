"""
ANPR Performance analytics (Phase 15H §10).

SQL aggregates over `vehicle_events` (Phase 15B `anpr_status` /
`anpr_failure_reason` / `anpr_quality_score` / `plate_quality`) plus the
pipeline's last OCR-latency snapshot. Video is never re-processed.

> Accuracy is NOT claimed -- there is no labelled ground-truth set for the
> government feeds. "ANPR success rate" == the fraction of detections that
> produced a validated plate, which is a throughput/quality signal, not an
> accuracy measurement.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlmodel import Session

from app.config import settings
from app.models.camera import Camera
from app.models.pipeline_status import PipelineStatus
from app.models.vehicle_event import VehicleEvent

_LOW_QUALITY = 0.45


class AnprAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def summary(
        self,
        *,
        window_hours: int = 24,
        camera_code: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> dict:
        until = date_to or datetime.utcnow()
        since = date_from or (until - timedelta(hours=window_hours))
        conds = [VehicleEvent.timestamp >= since, VehicleEvent.timestamp < until]
        if camera_code:
            conds.append(VehicleEvent.camera_code == camera_code)
        if vehicle_type:
            conds.append(func.lower(VehicleEvent.vehicle_type) == vehicle_type.lower())

        total, readable, low_q, avg_q = self.db.execute(
            select(
                func.count(VehicleEvent.id),
                func.count(VehicleEvent.id).filter(VehicleEvent.anpr_status == "OK"),
                func.count(VehicleEvent.id).filter(
                    VehicleEvent.anpr_quality_score.is_not(None),
                    VehicleEvent.anpr_quality_score < _LOW_QUALITY,
                ),
                func.avg(VehicleEvent.anpr_quality_score),
            ).where(*conds)
        ).one()
        total = int(total or 0)
        readable = int(readable or 0)

        # failure reasons
        reasons = {
            r: int(n) for r, n in self.db.execute(
                select(VehicleEvent.anpr_failure_reason, func.count(VehicleEvent.id))
                .where(*conds, VehicleEvent.anpr_failure_reason.is_not(None))
                .group_by(VehicleEvent.anpr_failure_reason)
                .order_by(func.count(VehicleEvent.id).desc())
            ).all()
        }

        # by camera
        cam_rows = self.db.execute(
            select(
                VehicleEvent.camera_code,
                func.count(VehicleEvent.id),
                func.count(VehicleEvent.id).filter(VehicleEvent.anpr_status == "OK"),
            ).where(*conds).group_by(VehicleEvent.camera_code)
        ).all()
        by_camera = []
        for code, cnt, ok in cam_rows:
            cnt = int(cnt or 0)
            ok = int(ok or 0)
            by_camera.append({
                "camera_code": code or "unknown",
                "total": cnt, "readable": ok,
                "success_rate": round(ok / cnt, 3) if cnt else None,
            })
        by_camera.sort(key=lambda x: (x["success_rate"] if x["success_rate"] is not None else 1.0))
        codes = [c["camera_code"] for c in by_camera if c["camera_code"] != "unknown"]
        names = dict(self.db.execute(
            select(Camera.code, Camera.name).where(Camera.code.in_(codes or ["-"]))
        ).all())
        for c in by_camera:
            c["camera_name"] = names.get(c["camera_code"])
        top_cameras = sorted(
            [c for c in by_camera if c["total"] >= 3 and c["success_rate"] is not None],
            key=lambda x: x["success_rate"], reverse=True)[: settings.TRAFFIC_TOPN]
        worst_cameras = sorted(
            [c for c in by_camera if c["total"] >= 3 and c["success_rate"] is not None],
            key=lambda x: x["success_rate"])[: settings.TRAFFIC_TOPN]

        # by hour
        _h = func.date_trunc("hour", VehicleEvent.timestamp)
        hour_rows = self.db.execute(
            select(_h, func.count(VehicleEvent.id),
                   func.count(VehicleEvent.id).filter(VehicleEvent.anpr_status == "OK"))
            .where(*conds).group_by(_h).order_by(_h)
        ).all()
        by_hour = [
            {"hour": _iso_hour(h), "total": int(c),
             "readable": int(r or 0),
             "success_rate": round(int(r or 0) / int(c), 3) if c else None}
            for h, c, r in hour_rows
        ]

        # plate-confidence distribution (readable only)
        buckets = [0] * 10
        for (conf,) in self.db.execute(
            select(VehicleEvent.confidence_score)
            .where(*conds, VehicleEvent.anpr_status == "OK",
                   VehicleEvent.confidence_score.is_not(None))
        ).all():
            b = min(9, max(0, int(float(conf) * 10)))
            buckets[b] += 1
        confidence_distribution = [
            {"bucket": f"{i/10:.1f}-{(i+1)/10:.1f}", "count": n} for i, n in enumerate(buckets)
        ]

        ps = self.db.execute(
            select(PipelineStatus).order_by(PipelineStatus.reported_at.desc()).limit(1)
        ).scalar_one_or_none()

        return {
            "generated_at": datetime.now(timezone.utc),
            "window_start": since, "window_end": until,
            "total_vehicles": total,
            "readable_plates": readable,
            "unknown_plates": total - readable,
            "success_rate": round(readable / total, 3) if total else None,
            "low_quality_frames": int(low_q or 0),
            "mean_quality_score": round(float(avg_q), 3) if avg_q is not None else None,
            "failure_reasons": reasons,
            "ocr_p50_ms": ps.ocr_p50_ms if ps else None,
            "ocr_p95_ms": ps.ocr_p95_ms if ps else None,
            "top_cameras": top_cameras,
            "worst_cameras": worst_cameras,
            "by_camera": by_camera,
            "by_hour": by_hour,
            "confidence_distribution": confidence_distribution,
            "filters": {"camera_code": camera_code, "vehicle_type": vehicle_type,
                        "date_from": date_from, "date_to": date_to},
            "disclaimer": (
                "'Success rate' is the fraction of detections that produced a "
                "validated plate -- a throughput/quality signal, NOT an accuracy "
                "measurement (there is no labelled ground-truth set for the "
                "government feeds)."
            ),
        }


def _iso_hour(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00Z")
