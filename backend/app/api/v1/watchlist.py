"""Watchlist management API — add/list/deactivate blacklisted plate entries."""
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.exceptions import DuplicateWatchlistEntryError, NotFoundError
from app.core.rbac import require_roles
from app.database import get_db
from app.models.base import UserRole
from app.models.watchlist import Watchlist
from app.schemas.alert import WatchlistCreate, WatchlistRead
from app.schemas.auth import CurrentUser
from app.services.audit import record_audit
from app.services.plate_utils import normalize_plate

router = APIRouter()


@router.get("", response_model=list[WatchlistRead])
def list_watchlist(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.execute(select(Watchlist).order_by(Watchlist.created_at.desc())).scalars().all()


@router.post("", response_model=WatchlistRead, status_code=status.HTTP_201_CREATED)
def add_watchlist_entry(
    payload: WatchlistCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER)),
):
    plate_normalized = normalize_plate(payload.plate_number)

    existing = db.execute(
        select(Watchlist).where(Watchlist.plate_number_normalized == plate_normalized)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateWatchlistEntryError(payload.plate_number)

    entry = Watchlist(
        plate_number=payload.plate_number,
        plate_number_normalized=plate_normalized,
        offense_category=payload.offense_category,
        priority_level=payload.priority_level,
        reason=payload.reason,
        expires_at=payload.expires_at,
        added_by_user_id=user.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    record_audit(
        db,
        action="WATCHLIST_CREATED",
        user_id=user.id,
        resource="watchlist",
        resource_id=entry.id,
        detail={
            "plate": plate_normalized,
            "priority_level": payload.priority_level.value,
            "expires_at": payload.expires_at,
        },
    )
    return entry


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_watchlist_entry(
    watchlist_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER)),
):
    entry = db.get(Watchlist, watchlist_id)
    if entry is None:
        raise NotFoundError("Watchlist entry", watchlist_id)
    entry.active = False
    db.add(entry)
    db.commit()
    record_audit(
        db,
        action="WATCHLIST_DEACTIVATED",
        user_id=user.id,
        resource="watchlist",
        resource_id=watchlist_id,
        detail={"plate": entry.plate_number_normalized},
    )
