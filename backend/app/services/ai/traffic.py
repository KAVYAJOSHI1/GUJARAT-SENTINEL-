"""
Traffic Analytics (Phase 14 §4, §5).

Pure SQL aggregates over the existing `vehicle_events` / `alerts` /
`anomaly_events` / `incidents` -- **never re-processes video**. Every figure
is a live count; an empty database returns zeros / empty lists.

    TrafficAnalyticsService(db).overview(...)      # volume, peak hour, trend, congestion
    .by_camera(...)                                # per-camera breakdown
    .trends(...)                                   # hourly / daily time series
    .heatmap(kind, ...)                            # GIS density -- geolocated cameras only

Filters (all optional): date_from / date_to, camera_codes[], vehicle_type,
zone (matched against camera name / location_desc, case-insensitive).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import Float, and_, cast, func, or_, select
from sqlmodel import Session

from app.config import settings
from app.models.alert import Alert
from app.models.anomaly_event import AnomalyEvent
from app.models.camera import Camera
from app.models.incident import Incident
from app.models.vehicle_event import VehicleEvent

_UNKNOWN = "UNKNOWN"
_HEATMAP_KINDS = ("vehicle_density", "alert_density", "anomaly_density", "incident_density")


class TrafficFilters:
    def __init__(
        self,
        *,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        camera_codes: Optional[list[str]] = None,
        vehicle_type: Optional[str] = None,
        zone: Optional[str] = None,
    ):
        self.date_from = date_from
        self.date_to = date_to
        self.camera_codes = [c for c in (camera_codes or []) if c]
        self.vehicle_type = vehicle_type
        self.zone = zone

    def resolve_camera_codes(self, db: Session) -> Optional[list[str]]:
        """The concrete camera-code set this filter restricts to, or None
        for 'all cameras'."""
        codes: Optional[set[str]] = set(self.camera_codes) if self.camera_codes else None
        if self.zone:
            like = f"%{self.zone}%"
            zone_codes = {
                c for (c,) in db.execute(
                    select(Camera.code).where(
                        Camera.code.is_not(None),
                        or_(Camera.name.ilike(like), Camera.location_desc.ilike(like)),
                    )
                ).all()
            }
            codes = zone_codes if codes is None else (codes & zone_codes)
        return sorted(codes) if codes is not None else None


class TrafficAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    def _event_conds(self, f: TrafficFilters, *, since: datetime, until: datetime):
        conds = [VehicleEvent.timestamp >= since, VehicleEvent.timestamp < until]
        codes = f.resolve_camera_codes(self.db)
        if codes is not None:
            conds.append(VehicleEvent.camera_code.in_(codes or ["\x00none"]))
        if f.vehicle_type:
            conds.append(func.lower(VehicleEvent.vehicle_type) == f.vehicle_type.lower())
        return conds

    @staticmethod
    def _window(f: TrafficFilters, default_hours: int) -> tuple[datetime, datetime, int]:
        until = f.date_to or datetime.utcnow()
        since = f.date_from or (until - timedelta(hours=default_hours))
        hours = max(1, int((until - since).total_seconds() // 3600))
        return since, until, hours

    # ------------------------------------------------------------------ #
    def overview(self, f: TrafficFilters, *, default_hours: int = 24) -> dict:
        since, until, hours = self._window(f, default_hours)
        conds = self._event_conds(f, since=since, until=until)

        total = int(self.db.execute(
            select(func.count(VehicleEvent.id)).where(*conds)
        ).scalar() or 0)
        readable = int(self.db.execute(
            select(func.count(VehicleEvent.id)).where(
                *conds, VehicleEvent.plate_number_normalized != _UNKNOWN
            )
        ).scalar() or 0)
        distinct_plates = int(self.db.execute(
            select(func.count(func.distinct(VehicleEvent.plate_number_normalized))).where(
                *conds, VehicleEvent.plate_number_normalized != _UNKNOWN
            )
        ).scalar() or 0)
        active_cameras = int(self.db.execute(
            select(func.count(func.distinct(VehicleEvent.camera_code))).where(*conds)
        ).scalar() or 0)

        # hourly buckets -> peak hour + trend
        _hour = func.date_trunc("hour", VehicleEvent.timestamp)
        buckets = self.db.execute(
            select(_hour, func.count(VehicleEvent.id)).where(*conds)
            .group_by(_hour).order_by(_hour)
        ).all()
        peak = max(buckets, key=lambda r: r[1]) if buckets else None
        per_hour_avg = round(total / hours, 2)

        # trend vs the immediately preceding equal window
        prev_since = since - (until - since)
        prev_total = int(self.db.execute(
            select(func.count(VehicleEvent.id)).where(
                *self._event_conds(f, since=prev_since, until=since)
            )
        ).scalar() or 0)
        if prev_total == 0:
            trend, trend_pct = ("up" if total else "flat"), None
        else:
            change = (total - prev_total) / prev_total
            trend_pct = round(change * 100, 1)
            trend = "up" if change > 0.1 else "down" if change < -0.1 else "flat"

        # type distribution
        by_type = [
            {"label": vt or "unclassified", "count": int(c)}
            for vt, c in self.db.execute(
                select(VehicleEvent.vehicle_type, func.count(VehicleEvent.id))
                .where(*conds).group_by(VehicleEvent.vehicle_type)
                .order_by(func.count(VehicleEvent.id).desc())
            ).all()
        ]

        # top cameras
        top_cam_rows = self.db.execute(
            select(VehicleEvent.camera_code, func.count(VehicleEvent.id))
            .where(*conds).group_by(VehicleEvent.camera_code)
            .order_by(func.count(VehicleEvent.id).desc()).limit(settings.TRAFFIC_TOPN)
        ).all()
        codes = [c for c, _ in top_cam_rows if c]
        names = dict(self.db.execute(
            select(Camera.code, Camera.name).where(Camera.code.in_(codes or ["-"]))
        ).all())
        top_cameras = [
            {"label": c or "unknown", "count": int(n), "detail": names.get(c),
             "per_hour": round(int(n) / hours, 2)}
            for c, n in top_cam_rows
        ]

        # congestion: busiest-camera hourly rate vs thresholds
        busiest_rate = max((tc["per_hour"] for tc in top_cameras), default=0.0)
        if busiest_rate >= settings.TRAFFIC_CONGESTION_HIGH_PER_HOUR:
            congestion = "HIGH"
        elif busiest_rate >= settings.TRAFFIC_CONGESTION_MODERATE_PER_HOUR:
            congestion = "MODERATE"
        elif busiest_rate > 0:
            congestion = "LOW"
        else:
            congestion = "NONE"

        return {
            "generated_at": datetime.now(timezone.utc),
            "window_start": since,
            "window_end": until,
            "window_hours": hours,
            "total_vehicles": total,
            "readable_plates": readable,
            "unknown_plates": total - readable,
            "distinct_plates": distinct_plates,
            "active_cameras": active_cameras,
            "vehicles_per_hour": per_hour_avg,
            "peak_hour": (
                {"hour": _iso_hour(peak[0]), "count": int(peak[1])} if peak else None
            ),
            "trend": trend,
            "trend_pct": trend_pct,
            "prev_window_total": prev_total,
            "congestion": congestion,
            "vehicle_type_distribution": by_type,
            "top_cameras": top_cameras,
            "filters_applied": _filters_echo(f),
        }

    # ------------------------------------------------------------------ #
    def by_camera(self, f: TrafficFilters, *, default_hours: int = 24) -> dict:
        since, until, hours = self._window(f, default_hours)
        conds = self._event_conds(f, since=since, until=until)

        rows = self.db.execute(
            select(
                VehicleEvent.camera_id,
                VehicleEvent.camera_code,
                func.count(VehicleEvent.id),
                func.count(VehicleEvent.id).filter(
                    VehicleEvent.plate_number_normalized != _UNKNOWN
                ),
            )
            .where(*conds)
            .group_by(VehicleEvent.camera_id, VehicleEvent.camera_code)
            .order_by(func.count(VehicleEvent.id).desc())
        ).all()

        cam_ids = [r[0] for r in rows]
        meta = {
            cid: (name, ld)
            for cid, name, ld in self.db.execute(
                select(Camera.id, Camera.name, Camera.location_desc).where(
                    Camera.id.in_(cam_ids or ["-"])
                )
            ).all()
        }

        # busiest hour per camera (one grouped pass)
        _hour = func.date_trunc("hour", VehicleEvent.timestamp)
        peak_rows = self.db.execute(
            select(VehicleEvent.camera_id, _hour, func.count(VehicleEvent.id))
            .where(*conds).group_by(VehicleEvent.camera_id, _hour)
        ).all()
        peak_by_cam: dict[str, tuple[str, int]] = {}
        for cid, h, c in peak_rows:
            if cid not in peak_by_cam or c > peak_by_cam[cid][1]:
                peak_by_cam[cid] = (_iso_hour(h), int(c))

        out = []
        for cid, code, cnt, readable in rows:
            rate = round(int(cnt) / hours, 2)
            out.append({
                "camera_id": cid,
                "camera_code": code,
                "camera_name": meta.get(cid, (None, None))[0],
                "location_desc": meta.get(cid, (None, None))[1],
                "total_vehicles": int(cnt),
                "readable_plates": int(readable or 0),
                "vehicles_per_hour": rate,
                "busiest_hour": (
                    {"hour": peak_by_cam[cid][0], "count": peak_by_cam[cid][1]}
                    if cid in peak_by_cam else None
                ),
                "congestion": (
                    "HIGH" if rate >= settings.TRAFFIC_CONGESTION_HIGH_PER_HOUR
                    else "MODERATE" if rate >= settings.TRAFFIC_CONGESTION_MODERATE_PER_HOUR
                    else "LOW" if rate > 0 else "NONE"
                ),
            })
        return {
            "generated_at": datetime.now(timezone.utc),
            "window_start": since, "window_end": until, "window_hours": hours,
            "cameras": out, "filters_applied": _filters_echo(f),
        }

    # ------------------------------------------------------------------ #
    def trends(self, f: TrafficFilters, *, bucket: str = "hour", default_hours: int = 24) -> dict:
        bucket = bucket if bucket in ("hour", "day") else "hour"
        since, until, hours = self._window(f, default_hours)
        conds = self._event_conds(f, since=since, until=until)

        _b = func.date_trunc(bucket, VehicleEvent.timestamp)
        rows = self.db.execute(
            select(_b, func.count(VehicleEvent.id),
                   func.count(VehicleEvent.id).filter(
                       VehicleEvent.plate_number_normalized != _UNKNOWN))
            .where(*conds).group_by(_b).order_by(_b)
        ).all()
        series = [
            {"bucket": _iso_hour(b) if bucket == "hour" else b.date().isoformat(),
             "total": int(c), "readable": int(r or 0)}
            for b, c, r in rows
        ]
        counts = [s["total"] for s in series]
        return {
            "generated_at": datetime.now(timezone.utc),
            "bucket": bucket,
            "window_start": since, "window_end": until, "window_hours": hours,
            "series": series,
            "total": sum(counts),
            "mean_per_bucket": round(sum(counts) / len(counts), 2) if counts else 0.0,
            "max_bucket": max(series, key=lambda s: s["total"]) if series else None,
            "filters_applied": _filters_echo(f),
        }

    # ------------------------------------------------------------------ #
    def heatmap(self, f: TrafficFilters, *, kind: str = "vehicle_density",
                default_hours: int = 24) -> dict:
        if kind not in _HEATMAP_KINDS:
            kind = "vehicle_density"
        since, until, hours = self._window(f, default_hours)

        # geolocated cameras only -- NO fabricated coordinates
        cam_rows = self.db.execute(
            select(Camera.id, Camera.code, Camera.name,
                   ST_Y(Camera.location), ST_X(Camera.location))
            .where(Camera.location.is_not(None))
        ).all()
        codes_filter = f.resolve_camera_codes(self.db)
        cams = {
            cid: {"code": code, "name": name, "lat": lat, "lon": lon}
            for cid, code, name, lat, lon in cam_rows
            if lat is not None and lon is not None
            and (codes_filter is None or code in codes_filter)
        }

        if kind == "vehicle_density":
            model, tcol, ccol = VehicleEvent, VehicleEvent.timestamp, VehicleEvent.camera_id
            extra = []
            if f.vehicle_type:
                extra.append(func.lower(VehicleEvent.vehicle_type) == f.vehicle_type.lower())
            rows = self.db.execute(
                select(ccol, func.count(model.id))
                .where(tcol >= since, tcol < until, *extra)
                .group_by(ccol)
            ).all()
        elif kind == "alert_density":
            rows = self.db.execute(
                select(Alert.camera_id, func.count(Alert.id))
                .where(Alert.created_at >= since, Alert.created_at < until)
                .group_by(Alert.camera_id)
            ).all()
        elif kind == "anomaly_density":
            rows = self.db.execute(
                select(AnomalyEvent.camera_id, func.count(AnomalyEvent.id))
                .where(AnomalyEvent.created_at >= since, AnomalyEvent.created_at < until)
                .group_by(AnomalyEvent.camera_id)
            ).all()
        else:  # incident_density
            rows = self.db.execute(
                select(Incident.camera_id, func.count(Incident.id))
                .where(Incident.created_at >= since, Incident.created_at < until,
                       Incident.camera_id.is_not(None))
                .group_by(Incident.camera_id)
            ).all()

        counts = {cid: int(c) for cid, c in rows if cid in cams}
        max_c = max(counts.values(), default=0) or 1
        points = [
            {
                "camera_id": cid,
                "camera_code": cams[cid]["code"],
                "camera_name": cams[cid]["name"],
                "latitude": cams[cid]["lat"],
                "longitude": cams[cid]["lon"],
                "count": counts.get(cid, 0),
                "weight": round(counts.get(cid, 0) / max_c, 3),
            }
            for cid in cams
        ]
        points.sort(key=lambda p: p["count"], reverse=True)
        return {
            "generated_at": datetime.now(timezone.utc),
            "kind": kind,
            "window_start": since, "window_end": until, "window_hours": hours,
            "max_count": max(counts.values(), default=0),
            "geolocated_cameras": len(cams),
            "contributing_cameras": len([p for p in points if p["count"] > 0]),
            "points": points,
            "note": "Only geolocated cameras contribute. No coordinates are fabricated.",
            "filters_applied": _filters_echo(f),
        }


def _iso_hour(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00Z")


def _filters_echo(f: TrafficFilters) -> dict:
    return {
        "date_from": f.date_from, "date_to": f.date_to,
        "camera_codes": f.camera_codes or None,
        "vehicle_type": f.vehicle_type, "zone": f.zone,
    }
