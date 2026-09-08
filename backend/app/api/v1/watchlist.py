"""
Watchlist management console (phase brief FEATURE 3).

Builds on the existing watchlist table + matching engine. The engine's
`active_watchlist_clause()` (active + effective + non-expired) stays the
single source of truth for "currently matching" -- every read here derives
its is_expired / is_pending flags the same way, so the console can never
disagree with what actually raises alerts.

Preserved: the GJ18TC0450 demo entry (no effective_from / no expiry ->
always effective) is untouched by any of the new columns or logic.
"""
import csv
import io
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.api.v1._enrich import resolve_usernames
from app.core.exceptions import DuplicateWatchlistEntryError, NotFoundError, SentinelException
from app.core.rbac import require_roles
from app.database import get_db
from app.models.base import WATCHLIST_CATEGORIES, PriorityLevel, UserRole
from app.models.watchlist import Watchlist
from app.schemas.alert import (
    WatchlistCreate,
    WatchlistImportResult,
    WatchlistImportRow,
    WatchlistPage,
    WatchlistRead,
    WatchlistUpdate,
)
from app.schemas.auth import CurrentUser
from app.services.audit import client_ip, record_audit
from app.services.plate_utils import normalize_plate

router = APIRouter()

_MANAGE = require_roles(UserRole.ADMIN, UserRole.OFFICER)
_PLATE_RE = re.compile(r"^GJ\d{2}[A-Z]{1,2}\d{4}$")


def _read(w: Watchlist, usernames: dict, now: datetime | None = None) -> WatchlistRead:
    now = now or datetime.utcnow()
    is_expired = w.expires_at is not None and w.expires_at <= now
    is_pending = w.effective_from is not None and w.effective_from > now
    return WatchlistRead(
        id=w.id,
        plate_number=w.plate_number,
        plate_number_normalized=w.plate_number_normalized,
        offense_category=w.offense_category,
        priority_level=w.priority_level,
        reason=w.reason,
        description=w.description,
        active=w.active,
        effective_from=w.effective_from,
        expires_at=w.expires_at,
        is_expired=is_expired,
        is_pending=is_pending,
        is_currently_effective=(w.active and not is_expired and not is_pending),
        added_by_user_id=w.added_by_user_id,
        added_by_username=usernames.get(w.added_by_user_id or ""),
        updated_by_user_id=w.updated_by_user_id,
        updated_by_username=usernames.get(w.updated_by_user_id or ""),
        created_at=w.created_at,
        updated_at=w.updated_at,
    )


@router.get("/categories", response_model=list[str])
def watchlist_categories(_: CurrentUser = Depends(get_current_user)):
    return list(WATCHLIST_CATEGORIES)


@router.get("", response_model=WatchlistPage)
def list_watchlist(
    q: str | None = Query(default=None, description="substring on plate"),
    category: str | None = Query(default=None),
    priority: PriorityLevel | None = Query(default=None),
    active: bool | None = Query(default=None),
    status_filter: str | None = Query(
        default=None, alias="status",
        description="effective | pending | expired | inactive",
    ),
    sort: str = Query(default="recent", description="recent|plate|priority|expiry"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    now = datetime.utcnow()
    conds = []
    if q:
        conds.append(Watchlist.plate_number_normalized.ilike(f"%{normalize_plate(q)}%"))
    if category:
        conds.append(Watchlist.offense_category == category)
    if priority:
        conds.append(Watchlist.priority_level == priority)
    if active is not None:
        conds.append(Watchlist.active.is_(active))
    if status_filter == "inactive":
        conds.append(Watchlist.active.is_(False))
    elif status_filter == "expired":
        conds.append(Watchlist.expires_at.is_not(None))
        conds.append(Watchlist.expires_at <= now)
    elif status_filter == "pending":
        conds.append(Watchlist.effective_from.is_not(None))
        conds.append(Watchlist.effective_from > now)
    elif status_filter == "effective":
        conds.append(Watchlist.active.is_(True))
        conds.append((Watchlist.effective_from.is_(None)) | (Watchlist.effective_from <= now))
        conds.append((Watchlist.expires_at.is_(None)) | (Watchlist.expires_at > now))

    order = {
        "plate": Watchlist.plate_number_normalized.asc(),
        "priority": Watchlist.priority_level.desc(),
        "expiry": Watchlist.expires_at.asc().nullslast(),
    }.get(sort, Watchlist.created_at.desc())

    total = db.execute(select(func.count(Watchlist.id)).where(*conds)).scalar() or 0
    rows = db.execute(
        select(Watchlist).where(*conds).order_by(order).limit(limit).offset(offset)
    ).scalars().all()
    usernames = resolve_usernames(
        db, [r.added_by_user_id for r in rows] + [r.updated_by_user_id for r in rows]
    )
    return WatchlistPage(
        items=[_read(r, usernames, now) for r in rows],
        total=int(total), limit=limit, offset=offset,
    )


@router.post("", response_model=WatchlistRead, status_code=status.HTTP_201_CREATED)
def add_watchlist_entry(
    payload: WatchlistCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    plate_normalized = normalize_plate(payload.plate_number)
    if db.execute(
        select(Watchlist).where(Watchlist.plate_number_normalized == plate_normalized)
    ).scalar_one_or_none() is not None:
        raise DuplicateWatchlistEntryError(payload.plate_number)

    entry = Watchlist(
        plate_number=payload.plate_number,
        plate_number_normalized=plate_normalized,
        offense_category=payload.offense_category,
        priority_level=payload.priority_level,
        reason=payload.reason,
        description=payload.description,
        effective_from=payload.effective_from,
        expires_at=payload.expires_at,
        added_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    record_audit(
        db, action="WATCHLIST_CREATED", user_id=user.id, resource="watchlist",
        resource_id=entry.id, ip_address=client_ip(request),
        detail={"plate": plate_normalized, "priority_level": payload.priority_level.value,
                "category": payload.offense_category, "expires_at": payload.expires_at},
    )
    return _read(entry, {user.id: user.username})


@router.patch("/{watchlist_id}", response_model=WatchlistRead)
def update_watchlist_entry(
    watchlist_id: str,
    payload: WatchlistUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    entry = db.get(Watchlist, watchlist_id)
    if entry is None:
        raise NotFoundError("Watchlist entry", watchlist_id)

    changed: dict = {}
    if payload.plate_number is not None:
        new_norm = normalize_plate(payload.plate_number)
        if new_norm != entry.plate_number_normalized:
            clash = db.execute(
                select(Watchlist.id).where(Watchlist.plate_number_normalized == new_norm)
            ).first()
            if clash:
                raise DuplicateWatchlistEntryError(payload.plate_number)
            entry.plate_number = payload.plate_number
            entry.plate_number_normalized = new_norm
            changed["plate"] = new_norm
    for f in ("offense_category", "reason", "description"):
        v = getattr(payload, f)
        if v is not None and v != getattr(entry, f):
            setattr(entry, f, v)
            changed[f] = v
    if payload.priority_level is not None and payload.priority_level != entry.priority_level:
        entry.priority_level = payload.priority_level
        changed["priority_level"] = payload.priority_level.value
    if payload.effective_from is not None:
        entry.effective_from = payload.effective_from
        changed["effective_from"] = str(payload.effective_from)
    if payload.expires_at is not None:
        entry.expires_at = payload.expires_at
        changed["expires_at"] = str(payload.expires_at)
    if payload.active is not None and payload.active != entry.active:
        entry.active = payload.active
        changed["active"] = payload.active

    if changed:
        entry.updated_by_user_id = user.id
        db.add(entry)
        db.commit()
        db.refresh(entry)
        record_audit(
            db, action="WATCHLIST_UPDATED", user_id=user.id, resource="watchlist",
            resource_id=entry.id, ip_address=client_ip(request),
            detail={"plate": entry.plate_number_normalized, "changed": changed},
        )
    return _read(entry, resolve_usernames(db, [entry.added_by_user_id, entry.updated_by_user_id]))


@router.post("/{watchlist_id}/activate", response_model=WatchlistRead)
def activate_watchlist_entry(
    watchlist_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    entry = db.get(Watchlist, watchlist_id)
    if entry is None:
        raise NotFoundError("Watchlist entry", watchlist_id)
    entry.active = True
    entry.updated_by_user_id = user.id
    db.add(entry)
    db.commit()
    db.refresh(entry)
    record_audit(
        db, action="WATCHLIST_ACTIVATED", user_id=user.id, resource="watchlist",
        resource_id=entry.id, ip_address=client_ip(request),
        detail={"plate": entry.plate_number_normalized},
    )
    return _read(entry, resolve_usernames(db, [entry.added_by_user_id, entry.updated_by_user_id]))


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_watchlist_entry(
    watchlist_id: str,
    request: Request = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    """Deactivate (soft-disable). The row is kept for audit/history; it just
    stops matching. Same behaviour as before Phase 11."""
    entry = db.get(Watchlist, watchlist_id)
    if entry is None:
        raise NotFoundError("Watchlist entry", watchlist_id)
    entry.active = False
    entry.updated_by_user_id = user.id
    db.add(entry)
    db.commit()
    record_audit(
        db, action="WATCHLIST_DEACTIVATED", user_id=user.id, resource="watchlist",
        resource_id=watchlist_id, ip_address=client_ip(request) if request else None,
        detail={"plate": entry.plate_number_normalized},
    )


# --------------------------------------------------------------------------- #
#  CSV export / import                                                        #
# --------------------------------------------------------------------------- #
_CSV_HEADER = [
    "plate_number", "offense_category", "priority_level", "reason", "description",
    "effective_from", "expires_at", "active",
]


@router.get("/export.csv")
def export_watchlist_csv(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    rows = db.execute(select(Watchlist).order_by(Watchlist.created_at.asc())).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_CSV_HEADER)
    for e in rows:
        w.writerow([
            e.plate_number, e.offense_category, e.priority_level.value, e.reason or "",
            e.description or "",
            e.effective_from.isoformat() if e.effective_from else "",
            e.expires_at.isoformat() if e.expires_at else "",
            "true" if e.active else "false",
        ])
    record_audit(
        db, action="WATCHLIST_EXPORT", user_id=user.id, resource="watchlist",
        ip_address=client_ip(request), detail={"rows": len(rows)},
    )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="watchlist_export.csv"'},
    )


def _parse_dt(s: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return "INVALID"


@router.post("/import.csv", response_model=WatchlistImportResult)
async def import_watchlist_csv(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(_MANAGE),
):
    """Bulk CSV import. Validates plate format (Gujarat GJ##XX####), required
    fields, category, and dates. Existing plates are UPDATED (never
    duplicated -- the unique index would 409 anyway). Returns a per-row
    outcome + summary: created / updated / skipped / invalid.

    `dry_run=true` validates only and writes nothing."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    rows_out: list[WatchlistImportRow] = []
    created = updated = skipped = invalid = 0
    seen_in_file: set[str] = set()

    for idx, row in enumerate(reader, start=2):  # header is line 1
        plate_raw = (row.get("plate_number") or "").strip()
        norm = normalize_plate(plate_raw)
        cat = (row.get("offense_category") or "").strip().upper()
        prio_raw = (row.get("priority_level") or "MEDIUM").strip().upper()

        if not plate_raw or not cat:
            invalid += 1
            rows_out.append(WatchlistImportRow(line=idx, plate=norm or None,
                                               outcome="invalid", reason="missing plate or category"))
            continue
        if not _PLATE_RE.match(norm):
            invalid += 1
            rows_out.append(WatchlistImportRow(line=idx, plate=norm, outcome="invalid",
                                               reason="plate not in GJ##XX#### format"))
            continue
        if cat not in WATCHLIST_CATEGORIES:
            invalid += 1
            rows_out.append(WatchlistImportRow(line=idx, plate=norm, outcome="invalid",
                                               reason=f"unknown category '{cat}'"))
            continue
        try:
            prio = PriorityLevel(prio_raw)
        except ValueError:
            invalid += 1
            rows_out.append(WatchlistImportRow(line=idx, plate=norm, outcome="invalid",
                                               reason=f"bad priority '{prio_raw}'"))
            continue
        eff = _parse_dt(row.get("effective_from", ""))
        exp = _parse_dt(row.get("expires_at", ""))
        if eff == "INVALID" or exp == "INVALID":
            invalid += 1
            rows_out.append(WatchlistImportRow(line=idx, plate=norm, outcome="invalid",
                                               reason="unparseable date"))
            continue
        if norm in seen_in_file:
            skipped += 1
            rows_out.append(WatchlistImportRow(line=idx, plate=norm, outcome="skipped",
                                               reason="duplicate plate within file"))
            continue
        seen_in_file.add(norm)

        active_val = (row.get("active") or "true").strip().lower() not in ("false", "0", "no")
        existing = db.execute(
            select(Watchlist).where(Watchlist.plate_number_normalized == norm)
        ).scalar_one_or_none()

        if existing is not None:
            if not dry_run:
                existing.plate_number = plate_raw
                existing.offense_category = cat
                existing.priority_level = prio
                existing.reason = (row.get("reason") or "").strip() or existing.reason
                existing.description = (row.get("description") or "").strip() or existing.description
                existing.effective_from = eff
                existing.expires_at = exp
                existing.active = active_val
                existing.updated_by_user_id = user.id
                db.add(existing)
            updated += 1
            rows_out.append(WatchlistImportRow(line=idx, plate=norm, outcome="updated"))
        else:
            if not dry_run:
                db.add(Watchlist(
                    plate_number=plate_raw, plate_number_normalized=norm,
                    offense_category=cat, priority_level=prio,
                    reason=(row.get("reason") or "").strip() or None,
                    description=(row.get("description") or "").strip() or None,
                    effective_from=eff, expires_at=exp, active=active_val,
                    added_by_user_id=user.id, updated_by_user_id=user.id,
                ))
            created += 1
            rows_out.append(WatchlistImportRow(line=idx, plate=norm, outcome="created"))

    if not dry_run and (created or updated):
        db.commit()

    record_audit(
        db, action="WATCHLIST_IMPORT", user_id=user.id, resource="watchlist",
        ip_address=client_ip(request),
        detail={"dry_run": dry_run, "created": created, "updated": updated,
                "skipped": skipped, "invalid": invalid},
    )
    return WatchlistImportResult(
        created=created, updated=updated, skipped=skipped, invalid=invalid, rows=rows_out,
    )
