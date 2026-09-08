"""
Unified Advanced Search (FEATURE 1) + Global Quick Search (FEATURE 14).

Both build strictly on the existing entities -- vehicle_events joined to
cameras, with watchlist / alert / incident / case relationships resolved by
foreign key. No new denormalised store; the backend stays the source of
truth. Every query is bounded (WHERE + LIMIT/OFFSET) and paginated; the
partial-plate path uses the pg_trgm GIN index from migration 0007.
"""
import re
import time

from fastapi import APIRouter, Depends, Query, Request
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import cast, func, or_, select, tuple_
from sqlalchemy.types import Time
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.case import Case, CaseEvidence
from app.models.incident import Incident
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.schemas.auth import CurrentUser
from app.schemas.search import (
    GlobalHit,
    GlobalSearchResponse,
    VehicleSearchQuery,
    VehicleSearchResponse,
    VehicleSearchRow,
)
from app.services.audit import client_ip, record_audit
from app.services.plate_utils import normalize_plate
from app.services.watchlist_engine import active_watchlist_clause

router = APIRouter()

_MOCK_RE = re.compile(r"^mock[_-]?cam", re.IGNORECASE)


def _is_mock(code: str | None) -> bool:
    return bool(code and _MOCK_RE.match(code))


def _mock_sql_clause(is_mock: bool):
    like = VehicleEvent.camera_code.op("~*")(r"^mock[-_]?cam")
    return like if is_mock else ~like


def _build_conditions(q: VehicleSearchQuery):
    conds = []
    if q.plate:
        conds.append(VehicleEvent.plate_number_normalized == normalize_plate(q.plate))
    if q.plate_contains:
        frag = normalize_plate(q.plate_contains)
        if frag:
            conds.append(VehicleEvent.plate_number_normalized.ilike(f"%{frag}%"))
    if q.vehicle_type:
        conds.append(VehicleEvent.vehicle_type == q.vehicle_type)
    if q.vehicle_color:
        conds.append(func.lower(VehicleEvent.vehicle_color) == q.vehicle_color.strip().lower())
    if q.unknown_only:
        conds.append(VehicleEvent.plate_number_normalized == "UNKNOWN")
    if q.camera_code:
        conds.append(VehicleEvent.camera_code == q.camera_code)
    if q.date_from:
        conds.append(VehicleEvent.timestamp >= q.date_from)
    if q.date_to:
        conds.append(VehicleEvent.timestamp <= q.date_to)
    if q.time_from:
        conds.append(cast(VehicleEvent.timestamp, Time) >= q.time_from)
    if q.time_to:
        conds.append(cast(VehicleEvent.timestamp, Time) <= q.time_to)
    if q.min_confidence is not None:
        conds.append(VehicleEvent.confidence_score >= q.min_confidence)
    if q.source:
        src = q.source.strip().upper()
        if src in ("REAL", "MOCK"):
            conds.append(_mock_sql_clause(src == "MOCK"))
    if q.watchlist_only:
        conds.append(
            VehicleEvent.plate_number_normalized.in_(
                select(Watchlist.plate_number_normalized).where(active_watchlist_clause())
            )
        )
    if q.has_alert is not None:
        sub = select(Alert.id).where(Alert.vehicle_event_id == VehicleEvent.id).exists()
        conds.append(sub if q.has_alert else ~sub)
    if q.has_incident is not None:
        sub = select(Incident.id).where(Incident.vehicle_event_id == VehicleEvent.id).exists()
        conds.append(sub if q.has_incident else ~sub)
    if q.has_case is not None:
        sub = (
            select(CaseEvidence.id)
            .where(CaseEvidence.vehicle_event_id == VehicleEvent.id)
            .exists()
        )
        conds.append(sub if q.has_case else ~sub)
    if q.min_duration_seconds:
        # per-(camera, track) dwell time -- bounded by the same date range
        span_conds = [VehicleEvent.track_id.is_not(None)]
        if q.date_from:
            span_conds.append(VehicleEvent.timestamp >= q.date_from)
        if q.date_to:
            span_conds.append(VehicleEvent.timestamp <= q.date_to)
        long_tracks = (
            select(VehicleEvent.camera_code, VehicleEvent.track_id)
            .where(*span_conds)
            .group_by(VehicleEvent.camera_code, VehicleEvent.track_id)
            .having(
                func.extract(
                    "epoch",
                    func.max(VehicleEvent.timestamp) - func.min(VehicleEvent.timestamp),
                )
                >= q.min_duration_seconds
            )
        ).subquery()
        conds.append(
            tuple_(VehicleEvent.camera_code, VehicleEvent.track_id).in_(
                select(long_tracks.c.camera_code, long_tracks.c.track_id)
            )
        )
    return conds


def _order_by(sort: str):
    if sort == "earliest":
        return [VehicleEvent.timestamp.asc()]
    if sort == "confidence":
        return [VehicleEvent.confidence_score.desc().nullslast(), VehicleEvent.timestamp.desc()]
    if sort == "camera":
        return [VehicleEvent.camera_code.asc(), VehicleEvent.timestamp.desc()]
    return [VehicleEvent.timestamp.desc()]  # latest (default) / relevance


def execute_vehicle_search(db: Session, q: VehicleSearchQuery) -> VehicleSearchResponse:
    """Run the Advanced Search and build the enriched, relationship-linked
    result page. Shared by `POST /search/vehicles` and the Phase 12 AI NL
    search so there is exactly ONE search engine. Does NOT audit -- the
    caller does (with the right action name)."""
    t0 = time.perf_counter()
    conds = _build_conditions(q)

    # location filter needs the camera join in the WHERE clause
    need_cam_filter = bool(q.location_contains)
    base = select(VehicleEvent.id)
    if need_cam_filter:
        base = base.join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        like = f"%{q.location_contains.strip()}%"
        conds.append(or_(Camera.name.ilike(like), Camera.location_desc.ilike(like)))
    base = base.where(*conds)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0

    page_stmt = (
        select(
            VehicleEvent,
            Camera.code,
            Camera.name,
            Camera.location_desc,
            ST_Y(Camera.location),
            ST_X(Camera.location),
        )
        .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
        .where(*conds)
        .order_by(*_order_by(q.sort))
        .limit(q.limit)
        .offset(q.offset)
    )
    rows = db.execute(page_stmt).all()
    events = [r[0] for r in rows]
    event_ids = [e.id for e in events]
    plates = {e.plate_number_normalized for e in events}

    # --- bulk relationship resolution (no N+1) ---
    alerts_by_ev: dict[str, Alert] = {}
    inc_by_ev: dict[str, Incident] = {}
    case_by_ev: dict[str, tuple[str, str]] = {}
    wl_by_plate: dict[str, str] = {}
    if event_ids:
        for a in db.execute(select(Alert).where(Alert.vehicle_event_id.in_(event_ids))).scalars():
            alerts_by_ev.setdefault(a.vehicle_event_id, a)
        for i in db.execute(
            select(Incident).where(Incident.vehicle_event_id.in_(event_ids))
        ).scalars():
            inc_by_ev.setdefault(i.vehicle_event_id, i)
        for ev_id, c_id, c_num in db.execute(
            select(CaseEvidence.vehicle_event_id, Case.id, Case.case_number)
            .join(Case, Case.id == CaseEvidence.case_id)
            .where(CaseEvidence.vehicle_event_id.in_(event_ids))
        ).all():
            case_by_ev.setdefault(ev_id, (c_id, c_num))
    if plates:
        for plate, cat in db.execute(
            select(Watchlist.plate_number_normalized, Watchlist.offense_category)
            .where(Watchlist.plate_number_normalized.in_(plates))
            .where(active_watchlist_clause())
        ).all():
            wl_by_plate[plate] = cat

    items = []
    for ev, code, name, loc, lat, lon in rows:
        a = alerts_by_ev.get(ev.id)
        i = inc_by_ev.get(ev.id)
        c = case_by_ev.get(ev.id)
        items.append(
            VehicleSearchRow(
                event_id=ev.id,
                plate_number=ev.plate_number,
                plate_number_normalized=ev.plate_number_normalized,
                vehicle_type=ev.vehicle_type,
                vehicle_color=ev.vehicle_color,
                confidence_score=ev.confidence_score,
                timestamp=ev.timestamp,
                camera_id=ev.camera_id,
                camera_code=code,
                camera_name=name,
                location_desc=loc,
                latitude=ev.latitude if ev.latitude is not None else lat,
                longitude=ev.longitude if ev.longitude is not None else lon,
                is_mock_camera=_is_mock(code or ev.camera_code),
                has_snapshot=bool(ev.snapshot_url),
                is_watchlisted=ev.plate_number_normalized in wl_by_plate,
                watchlist_category=wl_by_plate.get(ev.plate_number_normalized),
                alert_id=a.id if a else None,
                alert_status=a.status.value if a else None,
                incident_id=i.id if i else None,
                incident_number=i.incident_number if i else None,
                case_id=c[0] if c else None,
                case_number=c[1] if c else None,
            )
        )

    return VehicleSearchResponse(
        items=items, total=int(total), limit=q.limit, offset=q.offset, sort=q.sort,
        took_ms=round((time.perf_counter() - t0) * 1000, 1),
    )


@router.post("/vehicles", response_model=VehicleSearchResponse)
def search_vehicles(
    q: VehicleSearchQuery,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    resp = execute_vehicle_search(db, q)
    record_audit(
        db, action="ADVANCED_SEARCH", user_id=user.id, resource="vehicle_events",
        ip_address=client_ip(request),
        detail={"total": resp.total, "returned": len(resp.items), "sort": q.sort,
                "filters": q.model_dump(exclude_none=True, exclude_defaults=True)},
    )
    return resp


# --------------------------------------------------------------------------- #
#  Global quick search (FEATURE 14)                                           #
# --------------------------------------------------------------------------- #
@router.get("/global", response_model=GlobalSearchResponse)
def global_search(
    q: str = Query(..., min_length=1, max_length=120),
    limit_per_group: int = Query(default=5, ge=1, le=15),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    raw = q.strip()
    plate = normalize_plate(raw)
    like = f"%{raw}%"
    groups: dict[str, list[GlobalHit]] = {
        "VEHICLES": [], "CAMERAS": [], "INCIDENTS": [], "CASES": [], "ALERTS": [], "EVIDENCE": []
    }

    # vehicles: distinct plates matching (exact or partial)
    if plate:
        rows = db.execute(
            select(
                VehicleEvent.plate_number_normalized,
                func.count(VehicleEvent.id),
                func.max(VehicleEvent.timestamp),
            )
            .where(VehicleEvent.plate_number_normalized.ilike(f"%{plate}%"))
            .where(VehicleEvent.plate_number_normalized != "UNKNOWN")
            .group_by(VehicleEvent.plate_number_normalized)
            .order_by(func.max(VehicleEvent.timestamp).desc())
            .limit(limit_per_group)
        ).all()
        for p, cnt, last in rows:
            groups["VEHICLES"].append(GlobalHit(
                kind="VEHICLE", id=p, label=p,
                sublabel=f"{cnt} sighting(s) · last {last:%d %b %H:%M}",
                href=f"/workspace?plate={p}",
            ))

    # cameras: code or name
    for cam in db.execute(
        select(Camera).where(or_(Camera.code.ilike(like), Camera.name.ilike(like)))
        .limit(limit_per_group)
    ).scalars():
        groups["CAMERAS"].append(GlobalHit(
            kind="CAMERA", id=cam.id, label=cam.code or cam.name,
            sublabel=cam.location_desc or cam.name, href=f"/cameras?focus={cam.id}",
        ))

    # incidents
    for inc in db.execute(
        select(Incident).where(
            or_(Incident.incident_number.ilike(like), Incident.title.ilike(like),
                Incident.plate_number_normalized.ilike(f"%{plate}%") if plate else Incident.id.is_(None))
        ).order_by(Incident.created_at.desc()).limit(limit_per_group)
    ).scalars():
        groups["INCIDENTS"].append(GlobalHit(
            kind="INCIDENT", id=inc.id, label=inc.incident_number,
            sublabel=inc.title, href=f"/incidents/{inc.id}",
        ))

    # cases
    for c in db.execute(
        select(Case).where(
            or_(Case.case_number.ilike(like), Case.title.ilike(like),
                Case.primary_plate_normalized.ilike(f"%{plate}%") if plate else Case.id.is_(None))
        ).order_by(Case.created_at.desc()).limit(limit_per_group)
    ).scalars():
        groups["CASES"].append(GlobalHit(
            kind="CASE", id=c.id, label=c.case_number, sublabel=c.title,
            href=f"/cases/{c.id}",
        ))

    # alerts: by id prefix or plate
    alert_conds = [Alert.plate_number_normalized.ilike(f"%{plate}%")] if plate else []
    if len(raw) >= 6:
        alert_conds.append(Alert.id.ilike(f"{raw}%"))
    if alert_conds:
        for a in db.execute(
            select(Alert).where(or_(*alert_conds)).order_by(Alert.created_at.desc())
            .limit(limit_per_group)
        ).scalars():
            groups["ALERTS"].append(GlobalHit(
                kind="ALERT", id=a.id, label=f"{a.plate_number_normalized} · {a.status.value}",
                sublabel=f"{a.priority_level.value} · {a.created_at:%d %b %H:%M}",
                href=f"/alerts?focus={a.id}",
            ))

    # evidence: a vehicle_event id prefix
    if len(raw) >= 6:
        for ev in db.execute(
            select(VehicleEvent).where(VehicleEvent.id.ilike(f"{raw}%"))
            .limit(limit_per_group)
        ).scalars():
            groups["EVIDENCE"].append(GlobalHit(
                kind="EVIDENCE", id=ev.id,
                label=f"{ev.plate_number_normalized} @ {ev.camera_code or '?'}",
                sublabel=f"{ev.timestamp:%d %b %H:%M}",
                href=f"/workspace?plate={ev.plate_number_normalized}",
            ))

    total = sum(len(v) for v in groups.values())
    return GlobalSearchResponse(query=raw, groups=groups, total=total)
