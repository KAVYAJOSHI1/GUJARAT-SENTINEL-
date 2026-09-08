"""
BehaviorAnalyticsService -- AI-assisted anomaly detection (phase brief §4,
Phase 14 §6).

THREE detectors, all running on stored ByteTrack `vehicle_events` only
(never re-processes video):

  * STOPPED_VEHICLE  -- a track that stays at one camera, enough detections,
    longer than a configurable dwell, without moving far.
  * WRONG_WAY        -- a track whose net heading is consistently opposite
    the camera's configured `permitted_direction_deg`.
  * RESTRICTED_ZONE  -- a track with sighting(s) inside a camera's
    configured `restricted_zones` polygon.

Every result is written to `anomaly_events` AND pushed through the EXISTING
alert architecture as an `Alert(source=ANOMALY)` -> notification -> (later)
incident. The watchlist -> alert engine is not touched.

Idempotent: the unique index (camera_id, track_id, first_seen, kind) plus a
pre-check means a re-scan never double-flags the same event.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlmodel import Session

from app.config import settings
from app.models.alert import Alert
from app.models.anomaly_event import AnomalyEvent
from app.models.base import (
    AlertSource,
    AnomalyKind,
    AnomalyStatus,
    NotificationSeverity,
    PriorityLevel,
)
from app.models.camera import Camera
from app.models.vehicle_event import VehicleEvent
from app.services.ai.confidence import (
    anomaly_confidence,
    restricted_zone_confidence,
    wrong_way_confidence,
)
from app.services.geo import (
    angular_diff_deg,
    bearing_deg,
    haversine_m as _haversine_m,
    point_in_polygon,
)
from app.services.notifications import push_notification

logger = logging.getLogger("sentinel.ai.behavior")

_ALL_KINDS = (
    AnomalyKind.STOPPED_VEHICLE,
    AnomalyKind.WRONG_WAY,
    AnomalyKind.RESTRICTED_ZONE,
)


class BehaviorAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    # ================================================================== #
    #  dispatcher
    # ================================================================== #
    def scan(self, *, kinds=None, lookback_hours: int | None = None,
             camera_code: str | None = None) -> dict:
        """Run one or more detectors. Returns the merged
        {scanned_tracks, created, already_flagged, anomalies:[...]}."""
        wanted = kinds or _ALL_KINDS
        wanted = {AnomalyKind(k) if not isinstance(k, AnomalyKind) else k for k in wanted}
        agg = {"scanned_tracks": 0, "created": 0, "already_flagged": 0, "anomalies": []}
        runners = {
            AnomalyKind.STOPPED_VEHICLE: self.scan_stopped_vehicles,
            AnomalyKind.WRONG_WAY: self.scan_wrong_way,
            AnomalyKind.RESTRICTED_ZONE: self.scan_restricted_zone,
        }
        for kind in _ALL_KINDS:
            if kind not in wanted:
                continue
            r = runners[kind](lookback_hours=lookback_hours, camera_code=camera_code)
            agg["scanned_tracks"] += r["scanned_tracks"]
            agg["created"] += r["created"]
            agg["already_flagged"] += r["already_flagged"]
            agg["anomalies"].extend(r["anomalies"])
        return agg

    # ================================================================== #
    #  shared helpers
    # ================================================================== #
    def _since(self, lookback_hours: int | None) -> datetime:
        return datetime.utcnow() - timedelta(
            hours=lookback_hours or settings.ANOMALY_LOOKBACK_HOURS
        )

    def _track_events(self, cam_id: str, track_id: int) -> list[VehicleEvent]:
        return self.db.execute(
            select(VehicleEvent)
            .where(VehicleEvent.camera_id == cam_id, VehicleEvent.track_id == track_id)
            .order_by(VehicleEvent.timestamp.asc())
        ).scalars().all()

    def _already(self, cam_id: str, track_id, first_s, kind: AnomalyKind) -> bool:
        return self.db.execute(
            select(AnomalyEvent.id).where(
                AnomalyEvent.camera_id == cam_id,
                AnomalyEvent.track_id == track_id,
                AnomalyEvent.first_seen == first_s,
                AnomalyEvent.kind == kind,
            )
        ).first() is not None

    def _persist(self, anomaly: AnomalyEvent, ev: VehicleEvent | None,
                 *, notif_title: str, notif_body: str) -> AnomalyEvent:
        """Insert the anomaly, wire an ANOMALY alert + notification through
        the existing workflow, commit. Returns the refreshed anomaly."""
        self.db.add(anomaly)
        self.db.flush()

        if ev is not None:
            alert = Alert(
                plate_number=(ev.plate_number if ev else (anomaly.plate_number_normalized or "UNKNOWN")),
                plate_number_normalized=anomaly.plate_number_normalized or "UNKNOWN",
                camera_id=anomaly.camera_id,
                vehicle_event_id=ev.id,
                watchlist_id=None,
                source=AlertSource.ANOMALY,
                anomaly_event_id=anomaly.id,
                priority_level=_priority(),
                snapshot_url=ev.snapshot_url,
            )
            self.db.add(alert)
            self.db.flush()
            anomaly.alert_id = alert.id
            self.db.add(anomaly)

        self.db.commit()
        self.db.refresh(anomaly)

        push_notification(
            self.db,
            type=f"ANOMALY_{anomaly.kind.value}",
            title=notif_title,
            body=notif_body,
            severity=(
                NotificationSeverity.WARNING
                if anomaly.confidence_level.value in ("HIGH", "MEDIUM")
                else NotificationSeverity.INFO
            ),
            resource="anomaly",
            resource_id=anomaly.id,
        )
        return anomaly

    # ================================================================== #
    #  1. STOPPED / LOITERING VEHICLE
    # ================================================================== #
    def scan_stopped_vehicles(
        self, *, lookback_hours: int | None = None, camera_code: str | None = None
    ) -> dict:
        since = self._since(lookback_hours)
        min_s = settings.ANOMALY_STOPPED_MIN_SECONDS
        min_c = settings.ANOMALY_STOPPED_MIN_DETECTIONS
        max_d = settings.ANOMALY_STOPPED_MAX_DISPLACEMENT_M

        conds = [VehicleEvent.timestamp >= since, VehicleEvent.track_id.is_not(None)]
        if camera_code:
            conds.append(VehicleEvent.camera_code == camera_code)

        groups = self.db.execute(
            select(
                VehicleEvent.camera_id, VehicleEvent.camera_code, VehicleEvent.track_id,
                func.count(VehicleEvent.id),
                func.min(VehicleEvent.timestamp), func.max(VehicleEvent.timestamp),
                func.min(VehicleEvent.latitude), func.max(VehicleEvent.latitude),
                func.min(VehicleEvent.longitude), func.max(VehicleEvent.longitude),
            )
            .where(*conds)
            .group_by(VehicleEvent.camera_id, VehicleEvent.camera_code, VehicleEvent.track_id)
            .having(func.count(VehicleEvent.id) >= min_c)
        ).all()

        created: list[AnomalyEvent] = []
        already = 0
        for cam_id, cam_code, track_id, count, first_s, last_s, min_la, max_la, min_lo, max_lo in groups:
            duration = (last_s - first_s).total_seconds()
            if duration < min_s:
                continue
            disp = None
            if None not in (min_la, max_la, min_lo, max_lo):
                disp = _haversine_m(min_la, min_lo, max_la, max_lo)
                if disp > max_d:
                    continue
            if self._already(cam_id, track_id, first_s, AnomalyKind.STOPPED_VEHICLE):
                already += 1
                continue

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
                evidence_event_id=ev.id if ev else None, status=AnomalyStatus.NEW,
            )
            if ev is None:  # no representative event -> log anomaly, skip alert
                self.db.add(anomaly)
                self.db.commit()
                self.db.refresh(anomaly)
            else:
                anomaly = self._persist(
                    anomaly, ev,
                    notif_title=f"Stopped vehicle — {cam_code or cam_id}",
                    notif_body=(f"{plate or 'Unknown vehicle'} held for {int(duration)}s "
                                f"({count} detections). AI-assisted anomaly · confidence {level.value}."),
                )
            created.append(anomaly)

        return {"scanned_tracks": len(groups), "created": len(created),
                "already_flagged": already, "anomalies": created}

    # ================================================================== #
    #  2. WRONG-WAY MOVEMENT
    # ================================================================== #
    def scan_wrong_way(
        self, *, lookback_hours: int | None = None, camera_code: str | None = None
    ) -> dict:
        since = self._since(lookback_hours)
        min_dist = settings.ANOMALY_WRONGWAY_MIN_DISTANCE_M
        min_det = settings.ANOMALY_WRONGWAY_MIN_DETECTIONS
        min_angle = settings.ANOMALY_WRONGWAY_MIN_ANGLE_DEG

        cam_conds = [Camera.permitted_direction_deg.is_not(None)]
        if camera_code:
            cam_conds.append(Camera.code == camera_code)
        cams = self.db.execute(select(Camera).where(*cam_conds)).scalars().all()

        created: list[AnomalyEvent] = []
        already = 0
        scanned = 0
        for cam in cams:
            permitted = float(cam.permitted_direction_deg)
            track_ids = [
                t for (t,) in self.db.execute(
                    select(VehicleEvent.track_id)
                    .where(VehicleEvent.camera_id == cam.id,
                           VehicleEvent.track_id.is_not(None),
                           VehicleEvent.timestamp >= since,
                           VehicleEvent.latitude.is_not(None))
                    .group_by(VehicleEvent.track_id)
                    .having(func.count(VehicleEvent.id) >= min_det)
                ).all()
            ]
            for track_id in track_ids:
                scanned += 1
                evs = [e for e in self._track_events(cam.id, track_id)
                       if e.latitude is not None and e.longitude is not None]
                if len(evs) < min_det:
                    continue
                a, b = evs[0], evs[-1]
                net = _haversine_m(a.latitude, a.longitude, b.latitude, b.longitude)
                if net < min_dist:
                    continue
                heading = bearing_deg(a.latitude, a.longitude, b.latitude, b.longitude)
                diff = angular_diff_deg(heading, permitted)
                if diff < min_angle:
                    continue
                if self._already(cam.id, track_id, a.timestamp, AnomalyKind.WRONG_WAY):
                    already += 1
                    continue

                dur = (b.timestamp - a.timestamp).total_seconds()
                score, level, reason = wrong_way_confidence(diff, net, len(evs), min_dist)
                anomaly = AnomalyEvent(
                    kind=AnomalyKind.WRONG_WAY,
                    camera_id=cam.id, camera_code=cam.code,
                    plate_number_normalized=a.plate_number_normalized,
                    track_id=track_id, first_seen=a.timestamp, last_seen=b.timestamp,
                    duration_seconds=int(max(0, dur)), detection_count=len(evs),
                    displacement_meters=round(net, 1),
                    direction_deg=round(heading, 1), expected_direction_deg=round(permitted, 1),
                    confidence_score=score, confidence_level=level,
                    reasoning=f"AI-assisted wrong-way detection: {reason}",
                    evidence_event_id=a.id, status=AnomalyStatus.NEW,
                )
                anomaly = self._persist(
                    anomaly, a,
                    notif_title=f"Wrong-way vehicle — {cam.code or cam.id}",
                    notif_body=(f"{a.plate_number_normalized or 'Unknown vehicle'} moved "
                                f"{diff:.0f}° against the permitted direction over {net:.0f} m. "
                                f"AI-assisted anomaly · confidence {level.value}."),
                )
                created.append(anomaly)

        return {"scanned_tracks": scanned, "created": len(created),
                "already_flagged": already, "anomalies": created}

    # ================================================================== #
    #  3. RESTRICTED-ZONE ENTRY
    # ================================================================== #
    def scan_restricted_zone(
        self, *, lookback_hours: int | None = None, camera_code: str | None = None
    ) -> dict:
        since = self._since(lookback_hours)
        cam_conds = [Camera.restricted_zones.is_not(None)]
        if camera_code:
            cam_conds.append(Camera.code == camera_code)
        cams = self.db.execute(select(Camera).where(*cam_conds)).scalars().all()

        created: list[AnomalyEvent] = []
        already = 0
        scanned = 0
        for cam in cams:
            zones = [z for z in (cam.restricted_zones or []) if z.get("points")]
            if not zones:
                continue
            track_ids = [
                t for (t,) in self.db.execute(
                    select(VehicleEvent.track_id)
                    .where(VehicleEvent.camera_id == cam.id,
                           VehicleEvent.track_id.is_not(None),
                           VehicleEvent.timestamp >= since,
                           VehicleEvent.latitude.is_not(None))
                    .group_by(VehicleEvent.track_id)
                ).all()
            ]
            for track_id in track_ids:
                scanned += 1
                evs = [e for e in self._track_events(cam.id, track_id)
                       if e.latitude is not None and e.longitude is not None]
                if not evs:
                    continue
                for zone in zones:
                    poly = zone["points"]
                    inside = [e for e in evs if point_in_polygon(e.latitude, e.longitude, poly)]
                    if len(inside) < settings.ANOMALY_ZONE_MIN_INSIDE:
                        continue
                    entry = inside[0]
                    if self._already(cam.id, track_id, entry.timestamp, AnomalyKind.RESTRICTED_ZONE):
                        already += 1
                        continue
                    dwell = (inside[-1].timestamp - inside[0].timestamp).total_seconds()
                    score, level, reason = restricted_zone_confidence(
                        len(inside), len(evs), dwell
                    )
                    anomaly = AnomalyEvent(
                        kind=AnomalyKind.RESTRICTED_ZONE,
                        camera_id=cam.id, camera_code=cam.code,
                        plate_number_normalized=entry.plate_number_normalized,
                        track_id=track_id, first_seen=entry.timestamp,
                        last_seen=inside[-1].timestamp,
                        duration_seconds=int(max(0, dwell)), detection_count=len(inside),
                        zone_name=zone.get("name") or "restricted zone",
                        confidence_score=score, confidence_level=level,
                        reasoning=f"AI-assisted restricted-zone detection: {reason}",
                        evidence_event_id=entry.id, status=AnomalyStatus.NEW,
                    )
                    anomaly = self._persist(
                        anomaly, entry,
                        notif_title=f"Restricted-zone entry — {cam.code or cam.id}",
                        notif_body=(f"{entry.plate_number_normalized or 'Unknown vehicle'} entered "
                                    f"'{anomaly.zone_name}'. AI-assisted anomaly · "
                                    f"confidence {level.value}."),
                    )
                    created.append(anomaly)
                    break  # one zone hit per track is enough

        return {"scanned_tracks": scanned, "created": len(created),
                "already_flagged": already, "anomalies": created}


def _priority() -> PriorityLevel:
    try:
        return PriorityLevel(settings.ANOMALY_PRIORITY.upper())
    except ValueError:
        return PriorityLevel.MEDIUM
