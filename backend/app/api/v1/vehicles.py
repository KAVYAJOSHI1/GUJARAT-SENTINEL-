"""
Vehicle Search & Trajectory API — GET /api/v1/vehicles/search?plate={plate}
Returns chronologically ordered sightings using the composite B-Tree index
on (plate_number_normalized, timestamp). Target: <50ms for 100k+ rows.
"""
import os
import re

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, RedirectResponse
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.deps import get_current_user, verify_bearer_header_or_query
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.camera import Camera
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.schemas.auth import CurrentUser
from app.schemas.vehicle import (
    CameraSeen,
    JourneyTransition,
    RelatedRecord,
    VehicleHistoryResponse,
    VehicleJourneySummary,
    VehicleProfile,
    VehicleSighting,
)
from app.services.audit import record_audit
from app.services.geo import haversine_m
from app.services.plate_utils import normalize_plate
from app.services.watchlist_engine import active_watchlist_clause

router = APIRouter()

_MOCK_RE = re.compile(r"^mock[_-]?cam", re.IGNORECASE)


def _is_mock_code(code: str | None) -> bool:
    return bool(code and _MOCK_RE.match(code))


def _feed_source(code: str | None, is_demo: bool | None) -> str:
    """Honest provenance label for a sighting's camera: seeded DEMO data,
    a local MOCK stream, or a REAL government feed. Mirrors the same
    precedence the camera stream service uses (DEMO > MOCK > REAL) so the
    investigation UI never implies demo data is real CCTV."""
    if is_demo:
        return "DEMO"
    if _is_mock_code(code):
        return "MOCK"
    return "REAL"

# Where THIS process can see the AI pipeline's local evidence tree
# (evidence/live/, evidence/mock/, ...). The DB stores whatever absolute
# path the pipeline process wrote (host machine, since the pipeline only
# ever runs on bare metal) -- in the dockerized backend that path doesn't
# exist, so it's translated against this mount instead (see the `evidence`
# volume in docker-compose.yml). Defaults to the repo-relative folder for a
# bare-metal (non-docker) backend run, where the literal path already works.
EVIDENCE_ROOT = os.getenv(
    "EVIDENCE_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "evidence"),
)


def _build_journey_summary(sightings: list[VehicleSighting], db=None) -> VehicleJourneySummary:
    """All fields derived from the real sighting rows only. `sightings` is
    already chronological ascending."""
    if not sightings:
        return VehicleJourneySummary()

    first = sightings[0].timestamp
    last = sightings[-1].timestamp
    span = int((last - first).total_seconds()) if last >= first else 0
    distinct_cameras = len({s.camera_id for s in sightings})
    geolocated = sum(1 for s in sightings if s.has_location)
    types = sorted({s.vehicle_type for s in sightings if s.vehicle_type})
    distinct_geo_cameras = len({s.camera_id for s in sightings if s.has_location})

    transitions = _build_transitions(sightings, db)
    return VehicleJourneySummary(
        first_seen=first,
        last_seen=last,
        span_seconds=span,
        distinct_cameras=distinct_cameras,
        geolocated_sightings=geolocated,
        vehicle_types=types,
        is_single_sighting=len(sightings) == 1,
        has_journey=distinct_geo_cameras >= 2,
        transitions=transitions,
        confirmed_sightings=len(sightings),
        inferred_transitions=len(transitions),
    )


def _travel_band_str(band: dict) -> str:
    lo, hi = band.get("typical_min_seconds"), band.get("typical_max_seconds")
    if lo is None:
        return "no travel-time baseline"
    src = band.get("source")
    n = band.get("sample_count") or 0
    tag = f"historical, {n} sample(s)" if src == "historical" else src
    return f"typical {round(lo/60)}–{round(hi/60)} min ({tag})"


def _build_transitions(sightings: list[VehicleSighting], db=None) -> list[JourneyTransition]:
    """One INFERRED transition per consecutive pair of sightings at DIFFERENT
    cameras. Distance / speed only when both cameras are geolocated; never
    fabricated. Confidence drops as the time gap grows (more chance the
    vehicle went elsewhere in between).

    Phase 14 §3: when a db session is available, each transition is also
    labelled PLAUSIBLE / FAST / SLOW / IMPOSSIBLE / UNKNOWN against the
    historical (or distance-model) travel band for that camera pair. This
    is a cheap stats lookup -- the full multi-signal correlation breakdown
    lives on POST /ai/correlation/analyze."""
    transition_svc = None
    if db is not None:
        try:
            from app.services.ai.camera_transitions import CameraTransitionService

            transition_svc = CameraTransitionService(db)
        except Exception:  # noqa: BLE001
            transition_svc = None

    out: list[JourneyTransition] = []
    for a, b in zip(sightings, sightings[1:]):
        if a.camera_id == b.camera_id:
            continue  # same camera -> not a movement
        dt = int((b.timestamp - a.timestamp).total_seconds())
        notes: list[str] = []
        dist = speed = None
        if a.has_location and b.has_location:
            dist = round(haversine_m(a.latitude, a.longitude, b.latitude, b.longitude), 1)
            if dt > 0 and dist >= 50:
                kmh = round((dist / dt) * 3.6, 1)
                if 0 < kmh <= 200:
                    speed = kmh
                elif kmh > 200:
                    notes.append(
                        f"implied speed {kmh} km/h is implausible — likely a plate "
                        f"misread or clock skew; speed not reported"
                    )
            elif dist < 50:
                notes.append("cameras < 50 m apart — speed not meaningful")
        else:
            notes.append("one or both camera coordinates unavailable — distance/speed not computed")

        # confidence in the transition being a real single-vehicle move
        if dt <= 0:
            level = "LOW"
            notes.append("non-increasing timestamps between sightings")
        elif dt <= 20 * 60:
            level = "HIGH" if (speed is not None or dist is not None) else "MEDIUM"
        elif dt <= 60 * 60:
            level = "MEDIUM"
        else:
            level = "LOW"
            notes.append(f"{dt // 60} min gap — the vehicle may have been elsewhere in between")

        classification = None
        band_str = None
        if transition_svc is not None and dt > 0:
            try:
                cls = transition_svc.classify(a.camera_id, b.camera_id, dt)
                classification = cls["classification"]
                band_str = _travel_band_str(cls["expected"])
                if classification == "IMPOSSIBLE":
                    notes.append("travel time is implausibly short for this camera pair")
                elif classification == "SLOW":
                    notes.append("gap is longer than typical for this camera pair")
            except Exception:  # noqa: BLE001 -- classification is best-effort
                classification = None

        out.append(JourneyTransition(
            from_camera_id=a.camera_id, from_camera_code=a.camera_code,
            to_camera_id=b.camera_id, to_camera_code=b.camera_code,
            from_timestamp=a.timestamp, to_timestamp=b.timestamp,
            time_diff_seconds=max(0, dt),
            distance_meters=dist, estimated_speed_kmh=speed,
            confidence_level=level, notes=notes,
            transition_classification=classification,
            expected_travel_band=band_str,
        ))
    return out


def _resolve_local_evidence_path(stored_path: str):
    """Rewrite anything after 'evidence/' in a stored host path onto
    EVIDENCE_ROOT, mirroring cameras.py's _resolve_mock_video_path. Returns
    None (falls back to the literal path) if there's nothing to translate or
    the translated file doesn't exist either."""
    if not stored_path:
        return None
    marker = f"evidence{os.sep}"
    idx = stored_path.rfind(marker)
    if idx == -1:
        return None
    candidate = os.path.join(EVIDENCE_ROOT, stored_path[idx + len(marker):])
    return candidate if os.path.isfile(candidate) else None


@router.get("/search", response_model=VehicleHistoryResponse)
def search_vehicle(
    plate: str = Query(..., min_length=2, description="Registration plate to search, e.g. GJ01AB1234"),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    plate_normalized = normalize_plate(plate)

    stmt = (
        select(
            VehicleEvent,
            Camera.name,
            Camera.code,
            Camera.location_desc,
            ST_Y(Camera.location),
            ST_X(Camera.location),
            Camera.is_demo,
        )
        .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        .where(VehicleEvent.plate_number_normalized == plate_normalized)
        .order_by(VehicleEvent.timestamp.asc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    sightings = []
    for ev, camera_name, camera_code, location_desc, cam_lat, cam_lon, cam_is_demo in rows:
        # prefer the event's own fix; fall back to the camera's location
        lat = ev.latitude if ev.latitude is not None else cam_lat
        lon = ev.longitude if ev.longitude is not None else cam_lon
        sightings.append(
            VehicleSighting(
                event_id=ev.id,
                camera_id=ev.camera_id,
                camera_code=camera_code,
                camera_name=camera_name,
                location_desc=location_desc,
                timestamp=ev.timestamp,
                latitude=lat,
                longitude=lon,
                has_location=lat is not None and lon is not None,
                snapshot_url=ev.snapshot_url,
                confidence_score=ev.confidence_score,
                track_id=ev.track_id,
                vehicle_type=ev.vehicle_type,
                vehicle_color=ev.vehicle_color,
                plate_number=ev.plate_number,
                anpr_status=ev.anpr_status or "OK",
                anpr_failure_reason=ev.anpr_failure_reason,
                anpr_quality_score=ev.anpr_quality_score,
                is_mock=_is_mock_code(camera_code or ev.camera_code),
                feed_source=_feed_source(camera_code or ev.camera_code, cam_is_demo),
            )
        )

    journey = _build_journey_summary(sightings, db)

    is_watchlisted = (
        db.execute(
            select(Watchlist.id)
            .where(Watchlist.plate_number_normalized == plate_normalized)
            .where(active_watchlist_clause())
            .limit(1)
        ).first()
        is not None
    )

    # Investigation / vehicle-search is a sensitive lookup on a real person's
    # movement history -- audit who searched what (SENTINEL_System_Audit_Report.md
    # §10 "Vehicle investigation/search"). Never blocks the response if the
    # audit write itself fails (see services/audit.py).
    record_audit(
        db,
        action="VEHICLE_SEARCH",
        user_id=user.id,
        resource="vehicle",
        resource_id=plate_normalized,
        detail={
            "total_sightings": len(sightings),
            "is_watchlisted": is_watchlisted,
            "distinct_cameras": journey.distinct_cameras,
        },
    )

    return VehicleHistoryResponse(
        plate_number=plate_normalized,
        total_sightings=len(sightings),
        is_watchlisted=is_watchlisted,
        sightings=sightings,
        journey=journey,
    )


@router.get("/profile", response_model=VehicleProfile)
def vehicle_profile(
    plate: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Phase 15D -- the consolidated investigation view opened from a search
    result: first/last seen, cameras, journey, ANPR quality breakdown,
    watchlist status, and linked alerts / incidents / cases / visual
    matches. Everything derived live from persisted rows."""
    from collections import Counter

    from app.models.alert import Alert
    from app.models.anomaly_event import AnomalyEvent
    from app.models.case import Case
    from app.models.incident import Incident
    from app.models.vehicle_embedding import VehicleEmbedding

    norm = normalize_plate(plate)
    rows = db.execute(
        select(VehicleEvent, Camera.name, Camera.code, Camera.location_desc,
               ST_Y(Camera.location), ST_X(Camera.location), Camera.is_demo)
        .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        .where(VehicleEvent.plate_number_normalized == norm)
        .order_by(VehicleEvent.timestamp.asc())
        .limit(500)
    ).all()

    sightings: list[VehicleSighting] = []
    per_cam: dict[str, dict] = {}
    reasons: Counter = Counter()
    readable = unknown = 0
    types: Counter = Counter()
    colors: Counter = Counter()
    for ev, cname, ccode, cloc, clat, clon, cdemo in rows:
        lat = ev.latitude if ev.latitude is not None else clat
        lon = ev.longitude if ev.longitude is not None else clon
        sightings.append(VehicleSighting(
            event_id=ev.id, camera_id=ev.camera_id, camera_code=ccode, camera_name=cname,
            location_desc=cloc, timestamp=ev.timestamp, latitude=lat, longitude=lon,
            has_location=lat is not None and lon is not None, snapshot_url=ev.snapshot_url,
            confidence_score=ev.confidence_score, track_id=ev.track_id,
            vehicle_type=ev.vehicle_type, vehicle_color=ev.vehicle_color,
            plate_number=ev.plate_number, anpr_status=ev.anpr_status or "OK",
            anpr_failure_reason=ev.anpr_failure_reason, anpr_quality_score=ev.anpr_quality_score,
            is_mock=_is_mock_code(ccode or ev.camera_code),
            feed_source=_feed_source(ccode or ev.camera_code, cdemo),
        ))
        if (ev.anpr_status or "OK") == "OK":
            readable += 1
        else:
            unknown += 1
            if ev.anpr_failure_reason:
                reasons[ev.anpr_failure_reason] += 1
        if ev.vehicle_type:
            types[ev.vehicle_type] += 1
        if ev.vehicle_color:
            colors[ev.vehicle_color] += 1
        c = per_cam.setdefault(ev.camera_id, {
            "camera_id": ev.camera_id, "camera_code": ccode, "camera_name": cname,
            "location_desc": cloc, "latitude": lat, "longitude": lon,
            "sightings": 0, "first_seen": ev.timestamp, "last_seen": ev.timestamp,
        })
        c["sightings"] += 1
        c["first_seen"] = min(c["first_seen"], ev.timestamp)
        c["last_seen"] = max(c["last_seen"], ev.timestamp)

    journey = _build_journey_summary(sightings, db)

    wl = db.execute(
        select(Watchlist).where(Watchlist.plate_number_normalized == norm)
        .where(active_watchlist_clause()).limit(1)
    ).scalar_one_or_none()

    alerts = db.execute(
        select(Alert).where(Alert.plate_number_normalized == norm)
        .order_by(Alert.created_at.desc()).limit(25)
    ).scalars().all()
    incidents = db.execute(
        select(Incident).where(Incident.plate_number_normalized == norm)
        .order_by(Incident.created_at.desc()).limit(25)
    ).scalars().all()
    cases = db.execute(
        select(Case).where(Case.primary_plate_normalized == norm)
        .order_by(Case.created_at.desc()).limit(25)
    ).scalars().all()
    anomalies = db.execute(
        select(func.count(AnomalyEvent.id)).where(AnomalyEvent.plate_number_normalized == norm)
    ).scalar() or 0
    evidence = sum(1 for s in sightings if s.snapshot_url)
    vmatch = db.execute(
        select(func.count(VehicleEmbedding.id))
        .where(VehicleEmbedding.plate_number_normalized == norm)
    ).scalar() or 0

    related: list[RelatedRecord] = []
    for a in alerts[:15]:
        related.append(RelatedRecord(kind="ALERT", id=a.id,
                                     label=f"{a.source.value} · {a.priority_level.value}",
                                     status=a.status.value, href=f"/alerts?focus={a.id}"))
    for i in incidents[:15]:
        related.append(RelatedRecord(kind="INCIDENT", id=i.id, label=i.incident_number,
                                     status=i.status.value, href=f"/incidents/{i.id}"))
    for c in cases[:15]:
        related.append(RelatedRecord(kind="CASE", id=c.id, label=c.case_number,
                                     status=c.status.value, href=f"/cases/{c.id}"))

    record_audit(db, action="VEHICLE_SEARCH", user_id=user.id, resource="vehicle",
                 resource_id=norm, detail={"profile": True, "sightings": len(sightings)})

    return VehicleProfile(
        plate=norm,
        total_sightings=len(sightings),
        first_seen=sightings[0].timestamp if sightings else None,
        last_seen=sightings[-1].timestamp if sightings else None,
        distinct_cameras=journey.distinct_cameras,
        geolocated_sightings=journey.geolocated_sightings,
        vehicle_types=[t for t, _ in types.most_common()],
        vehicle_colors=[c for c, _ in colors.most_common()],
        is_watchlisted=wl is not None,
        watchlist_category=wl.offense_category if wl else None,
        cameras=[CameraSeen(**c) for c in sorted(
            per_cam.values(), key=lambda x: x["first_seen"])],
        journey=journey,
        anpr_readable=readable,
        anpr_unknown=unknown,
        anpr_failure_reasons=dict(reasons),
        counts={
            "alerts": len(alerts), "incidents": len(incidents), "cases": len(cases),
            "anomalies": int(anomalies), "evidence": evidence,
        },
        related=related,
        visual_match_count=int(vmatch),
    )


@router.get("/events/recent", response_model=list[VehicleSighting])
def recent_vehicle_events(
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Most recent AI detections across all cameras (dashboard event feed)."""
    stmt = (
        select(
            VehicleEvent,
            Camera.name,
            Camera.code,
            Camera.location_desc,
            ST_Y(Camera.location),
            ST_X(Camera.location),
            Camera.is_demo,
        )
        .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        .order_by(VehicleEvent.timestamp.desc())
        .limit(limit)
    )
    out = []
    for ev, name, code, location_desc, cam_lat, cam_lon, cam_is_demo in db.execute(stmt).all():
        lat = ev.latitude if ev.latitude is not None else cam_lat
        lon = ev.longitude if ev.longitude is not None else cam_lon
        out.append(
            VehicleSighting(
                event_id=ev.id,
                camera_id=ev.camera_id,
                camera_code=code,
                camera_name=name,
                location_desc=location_desc,
                timestamp=ev.timestamp,
                latitude=lat,
                longitude=lon,
                has_location=lat is not None and lon is not None,
                snapshot_url=ev.snapshot_url,
                confidence_score=ev.confidence_score,
                track_id=ev.track_id,
                vehicle_type=ev.vehicle_type,
                vehicle_color=ev.vehicle_color,
                plate_number=ev.plate_number,
                anpr_status=ev.anpr_status or "OK",
                anpr_failure_reason=ev.anpr_failure_reason,
                anpr_quality_score=ev.anpr_quality_score,
                is_mock=_is_mock_code(code or ev.camera_code),
                feed_source=_feed_source(code or ev.camera_code, cam_is_demo),
            )
        )
    return out


@router.get("/evidence/{event_id}")
def get_evidence(
    event_id: str,
    requesting_user_id: str = Depends(verify_bearer_header_or_query),
    db: Session = Depends(get_db),
):
    """Serve (or redirect to) the snapshot image for one vehicle event.

    Accepts a normal Bearer token OR a ``?token=`` query param, because
    ``<img src>`` cannot send an Authorization header. ``event_id`` is an
    opaque UUID, so this is a low-sensitivity read.
    """
    ev = db.get(VehicleEvent, event_id)
    if ev is None:
        raise NotFoundError("Evidence", event_id)
    record_audit(
        db,
        action="EVIDENCE_ACCESSED",
        user_id=requesting_user_id,
        resource="vehicle_event",
        resource_id=event_id,
    )
    if not ev.snapshot_url:
        # The event is real but carries no snapshot (many detections don't).
        # Serve the honest placeholder with 200 so the UI renders cleanly.
        from fastapi.responses import Response

        return Response(content=_EVIDENCE_PLACEHOLDER_SVG, media_type="image/svg+xml",
                        headers={"X-Evidence-Status": "no-snapshot", "Cache-Control": "no-store"})
    url = ev.snapshot_url

    # Proxy the bytes through the backend so it works from any network (browser
    # can't reach the internal MinIO host, file:// paths aren't shared, etc).
    from app.services.minio_service import get_minio_service

    got = get_minio_service().fetch_bytes(url)
    if got is not None:
        from fastapi.responses import Response

        data, ctype = got
        return Response(content=data, media_type=ctype)

    if url.startswith(("http://", "https://")):
        return RedirectResponse(url)
    # ai/pipeline.py writes plain absolute filesystem paths (os.path.abspath),
    # not file:// URIs -- accept both. This is the fallback for a snapshot
    # that was never uploaded to MinIO (SENTINEL_SEND_SNAPSHOT sends it only
    # once per track, per ai/pipeline.py's dedup) -- covers both real
    # cameras' evidence/live/ and mock cameras' evidence/mock/.
    local_path = url[7:] if url.startswith("file://") else url
    local_path = _resolve_local_evidence_path(local_path) or local_path
    if os.path.isabs(local_path) and os.path.isfile(local_path):
        return FileResponse(local_path)

    # Phase 16: the reference exists on the row but the actual image is not
    # resolvable here (a demo/seeded snapshot_url, or a real crop that never
    # reached this host). Serve an explicit, honestly-labelled placeholder
    # with 200 instead of a 404 so the UI shows "evidence pending / not
    # available" cleanly and the browser console stays clean. This is NOT a
    # fabricated photo -- it is visibly a placeholder.
    from fastapi.responses import Response

    return Response(content=_EVIDENCE_PLACEHOLDER_SVG, media_type="image/svg+xml",
                    headers={"X-Evidence-Status": "unavailable", "Cache-Control": "no-store"})


_EVIDENCE_PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200" viewBox="0 0 320 200">'
    '<rect width="320" height="200" fill="#12161C"/>'
    '<rect x="8" y="8" width="304" height="184" fill="none" stroke="#2C333F" stroke-dasharray="4 4"/>'
    '<text x="160" y="96" fill="#8993A1" font-family="monospace" font-size="13" text-anchor="middle">'
    'EVIDENCE IMAGE NOT AVAILABLE</text>'
    '<text x="160" y="116" fill="#3A4250" font-family="monospace" font-size="10" text-anchor="middle">'
    'no crop reached this host</text></svg>'
).encode()
