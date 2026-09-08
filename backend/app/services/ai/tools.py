"""
Controlled investigation tools (phase brief §8).

The LLM (when configured) NEVER touches the database or writes SQL -- it
only picks one of these named tools and proposes parameters. The backend
validates the parameters and runs the query with the existing indexed
paths, then hands the LLM back ONLY the structured result.

The deterministic provider calls the very same tools, chosen by intent, so
both paths return identical data.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.v1.search import execute_vehicle_search
from app.config import settings
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.case import Case, CaseEvidence
from app.models.incident import Incident, IncidentEvidence
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.schemas.search import VehicleSearchQuery
from app.services.plate_utils import normalize_plate
from app.services.watchlist_engine import active_watchlist_clause

_MAX = None  # set from settings at call time


def _cap(n: int | None = None) -> int:
    return min(n or settings.AI_MAX_RESULTS, settings.AI_MAX_RESULTS)


def _resolve_camera_codes(db: Session, codes: list[str]) -> list[str]:
    """Map loose camera tokens ('CAM-04', 'cam4') onto real Camera.code
    values, case-insensitively / dash-insensitively."""
    if not codes:
        return []
    all_codes = [c for (c,) in db.execute(select(Camera.code).where(Camera.code.is_not(None))).all()]
    norm = {c.lower().replace("-", "").replace("_", ""): c for c in all_codes}
    out = []
    for token in codes:
        key = token.lower().replace("-", "").replace("_", "")
        if key in norm:
            out.append(norm[key])
    return list(dict.fromkeys(out))


class InvestigationTools:
    """One instance per request. All methods are read-only + bounded."""

    def __init__(self, db: Session):
        self.db = db

    # ---- vehicle ------------------------------------------------------- #
    def search_vehicle(self, plate: str, limit: int | None = None) -> dict:
        norm = normalize_plate(plate)
        rows = self.db.execute(
            select(VehicleEvent, Camera.code, Camera.name, Camera.location_desc,
                   ST_Y(Camera.location), ST_X(Camera.location))
            .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
            .where(VehicleEvent.plate_number_normalized == norm)
            .order_by(VehicleEvent.timestamp.asc())
            .limit(_cap(limit))
        ).all()
        sightings = [self._sighting(*r) for r in rows]
        wl = self.db.execute(
            select(Watchlist).where(Watchlist.plate_number_normalized == norm)
            .where(active_watchlist_clause()).limit(1)
        ).scalar_one_or_none()
        return {
            "plate": norm,
            "total_sightings": len(sightings),
            "is_watchlisted": wl is not None,
            "watchlist_category": wl.offense_category if wl else None,
            "sightings": sightings,
        }

    def get_vehicle_journey(self, plate: str, date_from: datetime | None = None,
                            date_to: datetime | None = None) -> dict:
        norm = normalize_plate(plate)
        conds = [VehicleEvent.plate_number_normalized == norm]
        if date_from:
            conds.append(VehicleEvent.timestamp >= date_from)
        if date_to:
            conds.append(VehicleEvent.timestamp <= date_to)
        rows = self.db.execute(
            select(VehicleEvent, Camera.code, Camera.name, Camera.location_desc,
                   ST_Y(Camera.location), ST_X(Camera.location))
            .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
            .where(*conds).order_by(VehicleEvent.timestamp.asc()).limit(_cap())
        ).all()
        sightings = [self._sighting(*r) for r in rows]
        geo = [s for s in sightings if s["has_location"]]
        distinct_cams = len({s["camera_code"] or s["camera_id"] for s in sightings})
        first = sightings[0]["timestamp"] if sightings else None
        last = sightings[-1]["timestamp"] if sightings else None
        span = int((last - first).total_seconds()) if first and last else 0
        return {
            "plate": norm,
            "sightings": sightings,
            "first_seen": first,
            "last_seen": last,
            "span_seconds": span,
            "distinct_cameras": distinct_cams,
            "geolocated_sightings": len(geo),
            "has_journey": len({(s["camera_code"] or s["camera_id"]) for s in geo}) >= 2,
        }

    def search_detections(self, plate: str | None = None, camera_codes: list[str] | None = None,
                          vehicle_type: str | None = None, vehicle_color: str | None = None,
                          date_from: datetime | None = None, date_to: datetime | None = None,
                          time_from: str | None = None, time_to: str | None = None,
                          unknown_only: bool = False, min_duration_seconds: int | None = None,
                          limit: int | None = None) -> dict:
        q = VehicleSearchQuery(
            plate=plate,
            vehicle_type=vehicle_type,
            vehicle_color=vehicle_color,
            camera_code=(_resolve_camera_codes(self.db, camera_codes or []) or [None])[0],
            date_from=date_from, date_to=date_to, time_from=time_from, time_to=time_to,
            unknown_only=unknown_only, min_duration_seconds=min_duration_seconds,
            sort="latest", limit=_cap(limit), offset=0,
        )
        return self.advanced_vehicle_search(q)

    def advanced_vehicle_search(self, q: VehicleSearchQuery) -> dict:
        q.limit = _cap(q.limit)
        resp = execute_vehicle_search(self.db, q)
        return {
            "total": resp.total,
            "returned": len(resp.items),
            "filters": q.model_dump(exclude_none=True, exclude_defaults=True),
            "items": [i.model_dump() for i in resp.items],
        }

    # ---- cameras ------------------------------------------------------ #
    def search_cameras(self, plate: str | None = None, name_contains: str | None = None,
                       date_from: datetime | None = None) -> dict:
        if plate:
            norm = normalize_plate(plate)
            conds = [VehicleEvent.plate_number_normalized == norm]
            if date_from:
                conds.append(VehicleEvent.timestamp >= date_from)
            rows = self.db.execute(
                select(VehicleEvent.camera_code, Camera.name, Camera.location_desc,
                       ST_Y(Camera.location), ST_X(Camera.location),
                       func.count(VehicleEvent.id), func.min(VehicleEvent.timestamp),
                       func.max(VehicleEvent.timestamp))
                .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
                .where(*conds)
                .group_by(VehicleEvent.camera_code, Camera.name, Camera.location_desc,
                          Camera.location)
                .order_by(func.min(VehicleEvent.timestamp).asc())
            ).all()
            return {"plate": norm, "cameras": [
                {"camera_code": c, "camera_name": n, "location_desc": ld,
                 "latitude": lat, "longitude": lon, "detections": int(cnt),
                 "first_seen": mn, "last_seen": mx}
                for c, n, ld, lat, lon, cnt, mn, mx in rows
            ]}
        conds = []
        if name_contains:
            like = f"%{name_contains}%"
            conds.append(Camera.name.ilike(like) | Camera.location_desc.ilike(like)
                         | Camera.code.ilike(like))
        rows = self.db.execute(
            select(Camera, ST_Y(Camera.location), ST_X(Camera.location))
            .where(*conds).limit(_cap())
        ).all()
        return {"cameras": [
            {"id": cam.id, "camera_code": cam.code, "camera_name": cam.name,
             "location_desc": cam.location_desc, "status": cam.status.value,
             "latitude": lat, "longitude": lon}
            for cam, lat, lon in rows
        ]}

    # ---- alerts / incidents / cases / evidence ---------------------- #
    def search_alerts(self, plate: str | None = None, date_from: datetime | None = None,
                      limit: int | None = None) -> dict:
        conds = []
        if plate:
            conds.append(Alert.plate_number_normalized == normalize_plate(plate))
        if date_from:
            conds.append(Alert.created_at >= date_from)
        rows = self.db.execute(
            select(Alert, Camera.code).join(Camera, Camera.id == Alert.camera_id, isouter=True)
            .where(*conds).order_by(Alert.created_at.desc()).limit(_cap(limit))
        ).all()
        return {"alerts": [
            {"id": a.id, "plate": a.plate_number_normalized, "camera_code": code,
             "priority": a.priority_level.value, "status": a.status.value,
             "source": a.source.value, "created_at": a.created_at}
            for a, code in rows
        ]}

    def search_incidents(self, plate: str | None = None, limit: int | None = None) -> dict:
        conds = []
        if plate:
            conds.append(Incident.plate_number_normalized == normalize_plate(plate))
        rows = self.db.execute(
            select(Incident).where(*conds).order_by(Incident.created_at.desc()).limit(_cap(limit))
        ).scalars().all()
        return {"incidents": [
            {"id": i.id, "incident_number": i.incident_number, "title": i.title,
             "status": i.status.value, "priority": i.priority_level.value,
             "plate": i.plate_number_normalized, "created_at": i.created_at}
            for i in rows
        ]}

    def search_cases(self, plate: str | None = None, limit: int | None = None) -> dict:
        conds = []
        if plate:
            conds.append(Case.primary_plate_normalized == normalize_plate(plate))
        rows = self.db.execute(
            select(Case).where(*conds).order_by(Case.created_at.desc()).limit(_cap(limit))
        ).scalars().all()
        return {"cases": [
            {"id": c.id, "case_number": c.case_number, "title": c.title,
             "status": c.status.value, "priority": c.priority_level.value,
             "plate": c.primary_plate_normalized, "created_at": c.created_at}
            for c in rows
        ]}

    def search_evidence(self, plate: str | None = None, incident_id: str | None = None,
                        case_id: str | None = None, limit: int | None = None) -> dict:
        """Evidence == vehicle_events carrying a snapshot, optionally
        restricted to those explicitly attached to an incident / case."""
        conds = [VehicleEvent.snapshot_url.is_not(None)]
        if plate:
            conds.append(VehicleEvent.plate_number_normalized == normalize_plate(plate))
        if incident_id:
            conds.append(VehicleEvent.id.in_(
                select(IncidentEvidence.vehicle_event_id).where(
                    IncidentEvidence.incident_id == incident_id)))
        if case_id:
            conds.append(VehicleEvent.id.in_(
                select(CaseEvidence.vehicle_event_id).where(CaseEvidence.case_id == case_id)))
        rows = self.db.execute(
            select(VehicleEvent, Camera.code)
            .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
            .where(*conds).order_by(VehicleEvent.timestamp.desc()).limit(_cap(limit))
        ).all()
        return {"evidence": [
            {"event_id": ev.id, "plate": ev.plate_number_normalized, "camera_code": code,
             "timestamp": ev.timestamp, "has_snapshot": bool(ev.snapshot_url)}
            for ev, code in rows
        ]}

    def watchlist_detections(self, date_from: datetime | None = None, limit: int | None = None) -> dict:
        """Watchlist vehicles actually detected (their alerts) in a window."""
        conds = []
        if date_from:
            conds.append(Alert.created_at >= date_from)
        rows = self.db.execute(
            select(Alert, Camera.code, Watchlist.offense_category)
            .join(Camera, Camera.id == Alert.camera_id, isouter=True)
            .join(Watchlist, Watchlist.id == Alert.watchlist_id, isouter=True)
            .where(*conds).order_by(Alert.created_at.desc()).limit(_cap(limit))
        ).all()
        return {"matches": [
            {"alert_id": a.id, "plate": a.plate_number_normalized, "camera_code": code,
             "category": cat, "priority": a.priority_level.value, "created_at": a.created_at}
            for a, code, cat in rows if a.source.value == "WATCHLIST"
        ]}

    # ---- helpers ----------------------------------------------------- #
    @staticmethod
    def _sighting(ev, code, name, loc, lat, lon):
        elat = ev.latitude if ev.latitude is not None else lat
        elon = ev.longitude if ev.longitude is not None else lon
        return {
            "event_id": ev.id, "plate": ev.plate_number_normalized,
            "camera_id": ev.camera_id, "camera_code": code, "camera_name": name,
            "location_desc": loc, "timestamp": ev.timestamp,
            "latitude": elat, "longitude": elon,
            "has_location": elat is not None and elon is not None,
            "vehicle_type": ev.vehicle_type, "vehicle_color": ev.vehicle_color,
            "confidence_score": ev.confidence_score, "track_id": ev.track_id,
            "has_snapshot": bool(ev.snapshot_url),
        }


# The catalogue the LLM sees (name + purpose + params). Purely descriptive;
# the real validation lives in the method signatures above.
TOOL_SPECS = [
    {"name": "search_vehicle", "description": "All recorded sightings of one plate + watchlist status.",
     "parameters": {"plate": "string (registration)"}},
    {"name": "get_vehicle_journey", "description": "Chronological camera-sighting trail of one plate.",
     "parameters": {"plate": "string", "date_from": "iso datetime?", "date_to": "iso datetime?"}},
    {"name": "search_detections", "description": "Filtered vehicle detections (type/colour/camera/time/duration).",
     "parameters": {"plate": "string?", "camera_codes": "string[]?", "vehicle_type": "string?",
                    "vehicle_color": "string?", "date_from": "iso?", "date_to": "iso?",
                    "time_from": "HH:MM?", "time_to": "HH:MM?", "unknown_only": "bool?",
                    "min_duration_seconds": "int?"}},
    {"name": "search_cameras", "description": "Cameras that detected a plate, or cameras by name.",
     "parameters": {"plate": "string?", "name_contains": "string?", "date_from": "iso?"}},
    {"name": "search_alerts", "description": "Alerts, optionally for one plate / since a time.",
     "parameters": {"plate": "string?", "date_from": "iso?"}},
    {"name": "search_incidents", "description": "Incidents, optionally for one plate.",
     "parameters": {"plate": "string?"}},
    {"name": "search_cases", "description": "Cases, optionally for one plate.",
     "parameters": {"plate": "string?"}},
    {"name": "search_evidence", "description": "Evidence snapshots for a plate / incident / case.",
     "parameters": {"plate": "string?", "incident_id": "string?", "case_id": "string?"}},
    {"name": "watchlist_detections", "description": "Watchlist vehicles actually detected in a window.",
     "parameters": {"date_from": "iso?"}},
]
