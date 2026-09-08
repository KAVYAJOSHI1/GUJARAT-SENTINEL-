"""
Investigation Gap Detection (Phase 14 §8).

`InvestigationGapService.detect(plate)` inspects one vehicle's recorded
sightings + the camera network + the transition baselines and surfaces
*evidence / coverage warnings*:

  * MISSING_COVERAGE       -- a long spatial hop with no camera in between
  * LONG_TIME_GAP          -- an unusually long unobserved interval
  * INCONSISTENT_TRAVEL    -- observed travel time is IMPOSSIBLE / very SLOW
  * LOW_CONFIDENCE_ANPR    -- a sighting whose plate read confidence is low
  * CAMERA_OFFLINE_WINDOW  -- a camera on the likely path was OFFLINE during
                             the gap
  * SINGLE_SIGHTING        -- only one sighting -> no corroboration

> This is NOT an accusation. It is a statement about what the evidence does
> and does not cover.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlmodel import Session

from app.config import settings
from app.models.base import CameraStatus
from app.models.camera import Camera
from app.models.camera_health_history import CameraHealthHistory
from app.models.vehicle_event import VehicleEvent
from app.services.ai.camera_transitions import CameraTransitionService
from app.services.geo import haversine_m
from app.services.plate_utils import normalize_plate

_LOW_CONF = 0.55


class InvestigationGapService:
    def __init__(self, db: Session):
        self.db = db
        self.transitions = CameraTransitionService(db)

    def detect(self, plate: str) -> dict:
        norm = normalize_plate(plate)
        rows = self.db.execute(
            select(VehicleEvent, Camera.code, Camera.name,
                   ST_Y(Camera.location), ST_X(Camera.location))
            .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
            .where(VehicleEvent.plate_number_normalized == norm)
            .order_by(VehicleEvent.timestamp.asc())
            .limit(settings.AI_MAX_RESULTS)
        ).all()

        gaps: list[dict] = []
        if not rows:
            return {"plate": norm, "sighting_count": 0, "gaps": [], "note": (
                "No sightings on record for this plate -- nothing to assess."
            )}

        sightings = [{
            "event_id": ev.id, "camera_id": ev.camera_id, "camera_code": code,
            "camera_name": name, "timestamp": ev.timestamp,
            "lat": ev.latitude if ev.latitude is not None else lat,
            "lon": ev.longitude if ev.longitude is not None else lon,
            "confidence": ev.confidence_score,
        } for ev, code, name, lat, lon in rows]

        if len(sightings) == 1:
            gaps.append(_gap(
                "SINGLE_SIGHTING", "low",
                f"Only one recorded sighting ({sightings[0]['camera_code']} at "
                f"{_fmt(sightings[0]['timestamp'])}). No cross-camera corroboration.",
                evidence=[sightings[0]["event_id"]],
            ))

        # low-confidence ANPR
        for s in sightings:
            if s["confidence"] is not None and s["confidence"] < _LOW_CONF:
                gaps.append(_gap(
                    "LOW_CONFIDENCE_ANPR", "medium",
                    f"Plate read at {s['camera_code']} ({_fmt(s['timestamp'])}) has low "
                    f"confidence ({s['confidence']:.2f}). This sighting may be a misread.",
                    evidence=[s["event_id"]],
                ))

        # pairwise hop analysis
        for a, b in zip(sightings, sightings[1:]):
            if a["camera_id"] == b["camera_id"]:
                continue
            dt = int((b["timestamp"] - a["timestamp"]).total_seconds())
            dist = None
            if None not in (a["lat"], a["lon"], b["lat"], b["lon"]):
                dist = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])

            # long time gap
            if dt > settings.GAP_LONG_INTERVAL_SECONDS:
                gaps.append(_gap(
                    "LONG_TIME_GAP", "medium" if dt < 2 * settings.GAP_LONG_INTERVAL_SECONDS else "high",
                    f"{dt // 60} min unobserved between {a['camera_code']} ({_fmt(a['timestamp'])}) "
                    f"and {b['camera_code']} ({_fmt(b['timestamp'])}). The vehicle's movements in "
                    f"this interval are not covered by any recorded sighting.",
                    evidence=[a["event_id"], b["event_id"]],
                ))

            # missing coverage: large distance, and no third camera sighting between
            if dist is not None and dist > settings.GAP_MISSING_COVERAGE_METERS:
                mid_cams = self._cameras_between(a, b)
                if mid_cams:
                    gaps.append(_gap(
                        "MISSING_COVERAGE", "medium",
                        f"{dist/1000:.1f} km between {a['camera_code']} and {b['camera_code']} with "
                        f"{len(mid_cams)} camera(s) roughly on the path "
                        f"({', '.join(c['code'] for c in mid_cams[:4])}) that recorded NO sighting "
                        f"of this vehicle in the interval.",
                        evidence=[a["event_id"], b["event_id"]],
                        extra={"cameras_on_path": [c["code"] for c in mid_cams]},
                    ))
                    # was any of those cameras offline during the window?
                    offline = self._offline_during(
                        [c["id"] for c in mid_cams], a["timestamp"], b["timestamp"]
                    )
                    for code in offline:
                        gaps.append(_gap(
                            "CAMERA_OFFLINE_WINDOW", "high",
                            f"Camera {code} lies on the likely path {a['camera_code']} -> "
                            f"{b['camera_code']} and was OFFLINE during this interval -- a sighting "
                            f"there may simply not have been captured.",
                            evidence=[a["event_id"], b["event_id"]],
                        ))

            # inconsistent travel time
            if dt > 0:
                cls = self.transitions.classify(a["camera_id"], b["camera_id"], dt)
                if cls["classification"] in ("IMPOSSIBLE", "SLOW"):
                    sev = "high" if cls["classification"] == "IMPOSSIBLE" else "low"
                    gaps.append(_gap(
                        "INCONSISTENT_TRAVEL", sev,
                        f"Travel {a['camera_code']} -> {b['camera_code']} took {dt // 60} min, "
                        f"which is {cls['classification']} for this camera pair "
                        f"({cls['expected']['source']} baseline). "
                        + ("Possible plate misread, clock skew, or a stop in between."
                           if cls["classification"] == "IMPOSSIBLE"
                           else "The vehicle may have stopped or diverted."),
                        evidence=[a["event_id"], b["event_id"]],
                    ))

        # de-dupe identical descriptions
        seen = set()
        uniq = []
        for g in gaps:
            key = (g["kind"], g["description"])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(g)

        return {
            "plate": norm,
            "sighting_count": len(sightings),
            "gap_count": len(uniq),
            "gaps": uniq,
            "disclaimer": (
                "These are evidence / coverage warnings, not accusations. They "
                "indicate where the recorded data is incomplete or inconsistent."
            ),
        }

    # ------------------------------------------------------------------ #
    def _cameras_between(self, a: dict, b: dict) -> list[dict]:
        """Cameras whose location is roughly on the segment a->b (within a
        corridor) and that are NOT a or b."""
        if None in (a["lat"], a["lon"], b["lat"], b["lon"]):
            return []
        seg_len = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) or 1.0
        corridor = settings.GAP_PATH_CORRIDOR_METERS
        out = []
        for cam, lat, lon in self.db.execute(
            select(Camera, ST_Y(Camera.location), ST_X(Camera.location))
            .where(Camera.location.is_not(None))
        ).all():
            if cam.id in (a["camera_id"], b["camera_id"]) or lat is None:
                continue
            da = haversine_m(a["lat"], a["lon"], lat, lon)
            db_ = haversine_m(b["lat"], b["lon"], lat, lon)
            # on the path if the detour via this camera isn't much longer than direct
            if da + db_ <= seg_len + corridor and da > 1 and db_ > 1:
                out.append({"id": cam.id, "code": cam.code, "name": cam.name})
        return out

    def _offline_during(self, cam_ids: list[str], start, end) -> list[str]:
        if not cam_ids:
            return []
        rows = self.db.execute(
            select(Camera.code, CameraHealthHistory.status, CameraHealthHistory.detected_at)
            .join(Camera, Camera.id == CameraHealthHistory.camera_id)
            .where(
                CameraHealthHistory.camera_id.in_(cam_ids),
                CameraHealthHistory.detected_at <= end,
                CameraHealthHistory.detected_at >= start - timedelta(hours=6),
            )
            .order_by(CameraHealthHistory.detected_at.asc())
        ).all()
        # last known status per camera before/within the window
        state: dict[str, str] = {}
        for code, status, _ in rows:
            state[code] = status.value if hasattr(status, "value") else str(status)
        return [code for code, st in state.items() if st == CameraStatus.OFFLINE.value]


def _gap(kind: str, severity: str, description: str, *, evidence=None, extra=None) -> dict:
    g = {"kind": kind, "severity": severity, "description": description,
         "evidence_event_ids": evidence or []}
    if extra:
        g.update(extra)
    return g


def _fmt(v) -> str:
    return v.strftime("%d %b %H:%M") if v else "unknown time"
