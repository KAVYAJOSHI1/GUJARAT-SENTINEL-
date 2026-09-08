"""
Notification center API (phase brief FEATURE 12).

Read + acknowledge only -- notifications are produced by real backend
events (see app/services/notifications.py), never by this router.

The list returns broadcast notifications (target_user_id IS NULL) plus the
caller's own directed ones.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.notification import Notification
from app.schemas.auth import CurrentUser
from app.schemas.notification import NotificationPage, NotificationRead, UnreadCount

router = APIRouter()


def _visible(user: CurrentUser):
    return or_(Notification.target_user_id.is_(None), Notification.target_user_id == user.id)


@router.get("", response_model=NotificationPage)
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    base = _visible(user)
    conds = [base]
    if unread_only:
        conds.append(Notification.read.is_(False))

    total = db.execute(select(func.count(Notification.id)).where(*conds)).scalar() or 0
    unread = db.execute(
        select(func.count(Notification.id)).where(base, Notification.read.is_(False))
    ).scalar() or 0
    rows = db.execute(
        select(Notification).where(*conds)
        .order_by(Notification.created_at.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    return NotificationPage(
        items=[NotificationRead.model_validate(r) for r in rows],
        total=int(total), unread=int(unread), limit=limit, offset=offset,
    )


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    n = db.execute(
        select(func.count(Notification.id)).where(_visible(user), Notification.read.is_(False))
    ).scalar() or 0
    return UnreadCount(unread=int(n))


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    n = db.get(Notification, notification_id)
    if n is None or (n.target_user_id is not None and n.target_user_id != user.id):
        raise NotFoundError("Notification", notification_id)
    if not n.read:
        n.read = True
        n.read_at = datetime.utcnow()
        db.add(n)
        db.commit()
        db.refresh(n)
    return NotificationRead.model_validate(n)


@router.post("/read-all", response_model=UnreadCount)
def mark_all_read(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    rows = db.execute(
        select(Notification).where(_visible(user), Notification.read.is_(False))
    ).scalars().all()
    now = datetime.utcnow()
    for n in rows:
        n.read = True
        n.read_at = now
        db.add(n)
    if rows:
        db.commit()
    return UnreadCount(unread=0)
