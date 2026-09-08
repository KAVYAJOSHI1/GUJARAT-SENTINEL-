"""
Saved Investigations API (FEATURE 2).

Stores only the Advanced-Search criteria (a small JSON blob), never a
result set -- opening a saved search re-runs it live. A user sees and
manages their own saved searches; ADMIN sees all.
"""
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.api.v1._enrich import resolve_usernames
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.base import UserRole
from app.models.saved_search import SavedSearch
from app.schemas.auth import CurrentUser
from app.schemas.saved_search import (
    SavedSearchCreate,
    SavedSearchList,
    SavedSearchRead,
    SavedSearchUpdate,
)
from app.services.audit import client_ip, record_audit

router = APIRouter()


def _read(s: SavedSearch, usernames: dict) -> SavedSearchRead:
    return SavedSearchRead(
        id=s.id, title=s.title, description=s.description, params=s.params or {},
        created_by_user_id=s.created_by_user_id,
        created_by_username=usernames.get(s.created_by_user_id or ""),
        created_at=s.created_at, updated_at=s.updated_at,
    )


def _owned_or_404(db: Session, sid: str, user: CurrentUser) -> SavedSearch:
    s = db.get(SavedSearch, sid)
    if s is None:
        raise NotFoundError("Saved search", sid)
    if s.created_by_user_id != user.id and user.role != UserRole.ADMIN:
        raise NotFoundError("Saved search", sid)  # don't leak existence
    return s


@router.get("", response_model=SavedSearchList)
def list_saved_searches(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    stmt = select(SavedSearch).order_by(SavedSearch.created_at.desc())
    if user.role != UserRole.ADMIN:
        stmt = stmt.where(SavedSearch.created_by_user_id == user.id)
    rows = db.execute(stmt.limit(200)).scalars().all()
    usernames = resolve_usernames(db, [r.created_by_user_id for r in rows])
    return SavedSearchList(items=[_read(r, usernames) for r in rows], total=len(rows))


@router.post("", response_model=SavedSearchRead, status_code=status.HTTP_201_CREATED)
def create_saved_search(
    payload: SavedSearchCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    s = SavedSearch(
        title=payload.title.strip(), description=payload.description,
        params=payload.params or {}, created_by_user_id=user.id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    record_audit(
        db, action="SAVED_SEARCH_CREATE", user_id=user.id, resource="saved_search",
        resource_id=s.id, ip_address=client_ip(request), detail={"title": s.title},
    )
    return _read(s, {user.id: user.username})


@router.get("/{sid}", response_model=SavedSearchRead)
def get_saved_search(
    sid: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    s = _owned_or_404(db, sid, user)
    return _read(s, resolve_usernames(db, [s.created_by_user_id]))


@router.patch("/{sid}", response_model=SavedSearchRead)
def update_saved_search(
    sid: str,
    payload: SavedSearchUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    s = _owned_or_404(db, sid, user)
    if payload.title is not None:
        s.title = payload.title.strip()
    if payload.description is not None:
        s.description = payload.description
    if payload.params is not None:
        s.params = payload.params
    db.add(s)
    db.commit()
    db.refresh(s)
    record_audit(
        db, action="SAVED_SEARCH_UPDATE", user_id=user.id, resource="saved_search",
        resource_id=s.id, ip_address=client_ip(request),
    )
    return _read(s, resolve_usernames(db, [s.created_by_user_id]))


@router.delete("/{sid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_search(
    sid: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    s = _owned_or_404(db, sid, user)
    db.delete(s)
    db.commit()
    record_audit(
        db, action="SAVED_SEARCH_DELETE", user_id=user.id, resource="saved_search",
        resource_id=sid, ip_address=client_ip(request),
    )
