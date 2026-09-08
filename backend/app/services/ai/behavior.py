"""
BehaviorAnalyticsService — AI-assisted anomaly detection (phase brief §4).

ONE detector: STOPPED / LOITERING VEHICLE. It runs on stored ByteTrack
`vehicle_events` only (never re-processes video). A track that stays at one
camera, with enough detections, for longer than a configurable duration
(and, where GPS exists, without moving far) is flagged.

The result is written to `anomaly_events` AND pushed through the EXISTING
alert architecture as an `Alert(source=ANOMALY)` — so it is acknowledged,
assigned, escalated and promoted to an incident exactly like a watchlist
alert. The watchlist -> alert engine is not touched.

Idempotent: the unique index (camera_id, track_id, first_seen) plus a
pre-check means a re-scan never double-flags the same event.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlmodel import Session

from app.config import settings
from app.models.alert import Alert
from app.models.anomaly_event import AnomalyEvent
from app.models.base import AlertSource, AnomalyKind, AnomalyStatus, NotificationSeverity, PriorityLevel
from app.models.camera import Camera
from app.models.vehicle_event import VehicleEvent
from app.services.ai.confidence import anomaly_confidence
from app.services.notifications import push_notification

logger = logging.getLogger("sentinel.ai.behavior")


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


class BehaviorAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def scan_stopped_vehicles(
        self, *, lookback_hours: int | None = None, camera_code: str | None = None
    ) -> dict:
        """Returns {scanned_tracks, created, already_flagged, anomalies:[AnomalyEvent]}.
        Creates AnomalyEvent + ANOMALY Alert + notification for each new hit.
        Commits its own rows. Does NOT broadcast (async caller does)."""
        hours = lookback_hours or settings.ANOMALY_LOOKBACK_HOURS
        since = datetime.utcnow() - timedelta(hours=hours)
        min_s = settings.ANOMALY_STOPPED_MIN_SECONDS
        min_c = settings.ANOMALY_STOPPED_MIN_DETECTIONS
        max_d = settings.ANOMALY_STOPPED_MAX_DISPLACEMENT_M

        conds = [VehicleEvent.timestamp >= since, VehicleEvent.track_id.is_not(None)]
        if camera_code:
            conds.append(VehicleEvent.camera_code == camera_code)

        # one aggregate pass over the window -- bounded
        groups = self.db.execute(
            select(
                VehicleEvent.camera_id,
                VehicleEvent.camera_code,
                VehicleEvent.track_id,
                func.count(VehicleEvent.id),
                func.min(VehicleEvent.timestamp),
                func.max(VehicleEvent.timestamp),
                func.min(VehicleEvent.latitude),
                func.max(VehicleEvent.latitude),
                func.min(VehicleEvent.longitude),
                func.max(VehicleEvent.longitude),
            )
            .where(*conds)
            .group_by(VehicleEvent.camera_id, VehicleEvent.camera_code, VehicleEvent.track_id)
            .having(func.count(VehicleEvent.id) >= min_c)
        ).all()

        created: list[AnomalyEvent] = []
        already = 0
        scanned = len(groups)

        for cam_id, cam_code, track_id, count, first_s, last_s, min_la, max_la, min_lo, max_lo in groups:
            duration = (last_s - first_s).total_seconds()
            if duration < min_s:
                continue

            disp = None
            if None not in (min_la, max_la, min_lo, max_lo):
                disp = _haversine_m(min_la, min_lo, max_la, max_lo)
                if disp > max_d:
                    continue  # it moved -> not stopped

            # dedup
            exists = self.db.execute(
                select(AnomalyEvent.id).where(
                    AnomalyEvent.camera_id == cam_id,
                    AnomalyEvent.track_id == track_id,
                    AnomalyEvent.first_seen == first_s,
                )
            ).first()
            if exists:
                already += 1
                continue

            # representative event (first sighting) for evidence + plate
            ev = self.db.execute(
                select(VehicleEvent)
                .where(VehicleEvent.camera_id == cam_id, VehicleEvent.track_id == track_id)
                .order_by(VehicleEvent.timestamp.asc()).limit(1)
            ).scalar_one_or_none()
            plate = ev.plate_number_normalized if ev else None

            score, level, reason = anomaly_confidence(duration, count, disp, min_s, min_c, max_d)

            anomaly = AnomalyEvent(
                kind=AnomalyKind.STOPPED_VEHICLE,
                camera_id=cam_id, camera_code=cam_code, plate_number_normalized=plate,
                track_id=track_id, first_seen=first_s, last_seen=last_s,
                duration_seconds=int(duration), detection_count=int(count),
                displacement_meters=round(disp, 1) if disp is not None else None,
                confidence_score=score, confidence_level=level,
                reasoning=f"AI-assisted anomaly detection: {reason}",
                evidence_event_id=ev.id if ev else None,
                status=AnomalyStatus.NEW,
            )
            self.db.add(anomaly)
            self.db.flush()  # get anomaly.id

            alert = Alert(
                plate_number=(ev.plate_number if ev else (plate or "UNKNOWN")),
                plate_number_normalized=plate or "UNKNOWN",
                camera_id=cam_id,
                vehicle_event_id=ev.id if ev else None,
                watchlist_id=None,
                source=AlertSource.ANOMALY,
                anomaly_event_id=anomaly.id,
                priority_level=_priority(),
                snapshot_url=ev.snapshot_url if ev else None,
            )
            # vehicle_event_id is NOT NULL on the alerts table -- if we somehow
            # have no representative event we skip the alert (anomaly still logged)
            if alert.vehicle_event_id:
                self.db.add(alert)
                self.db.flush()
                anomaly.alert_id = alert.id
                self.db.add(anomaly)

            self.db.commit()
            self.db.refresh(anomaly)
            created.append(anomaly)

            push_notification(
                self.db, type="ANOMALY_STOPPED_VEHICLE",
                title=f"Stopped vehicle — {cam_code or cam_id}",
                body=(f"{plate or 'Unknown vehicle'} held for {int(duration)}s "
                      f"({count} detections). AI-assisted anomaly · confidence {level.value}."),
                severity=(NotificationSeverity.WARNING if level.value in ("HIGH", "MEDIUM")
                          else NotificationSeverity.INFO),
                resource="anomaly", resource_id=anomaly.id,
            )

        return {
            "scanned_tracks": scanned, "created": len(created),
            "already_flagged": already, "anomalies": created,
        }


def _priority() -> PriorityLevel:
    try:
        return PriorityLevel(settings.ANOMALY_PRIORITY.upper())
    except ValueError:
        return PriorityLevel.MEDIUM
