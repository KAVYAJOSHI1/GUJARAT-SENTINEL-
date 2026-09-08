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
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import get_current_user, verify_bearer_header_or_query
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.camera import Camera
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.schemas.auth import CurrentUser
from app.schemas.vehicle import (
    JourneyTransition,
    VehicleHistoryResponse,
    VehicleJourneySummary,
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
        )
        .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        .where(VehicleEvent.plate_number_normalized == plate_normalized)
        .order_by(VehicleEvent.timestamp.asc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    sightings = []
    for ev, camera_name, camera_code, location_desc, cam_lat, cam_lon in rows:
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
        )
        .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        .order_by(VehicleEvent.timestamp.desc())
        .limit(limit)
    )
    out = []
    for ev, name, code, location_desc, cam_lat, cam_lon in db.execute(stmt).all():
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
    if ev is None or not ev.snapshot_url:
        raise NotFoundError("Evidence", event_id)
    record_audit(
        db,
        action="EVIDENCE_ACCESSED",
        user_id=requesting_user_id,
        resource="vehicle_event",
        resource_id=event_id,
    )
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
    raise NotFoundError("Evidence file", event_id)
