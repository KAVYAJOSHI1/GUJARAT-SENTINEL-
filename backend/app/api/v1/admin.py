"""Admin-only operational endpoints (data retention, audit/activity center)."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlmodel import Session

from app.api.v1._enrich import resolve_usernames
from app.config import settings
from app.core.rbac import require_roles
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.base import UserRole
from app.models.user import User
from app.schemas.audit import AuditLogPage, AuditLogRead
from app.schemas.auth import CurrentUser
from app.services.audit import record_audit
from app.services.retention import purge_old_vehicle_events

router = APIRouter()


class AssignableUser(BaseModel):
    id: str
    username: str
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/users", response_model=list[AssignableUser])
def list_users(
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.OFFICER)),
) -> list[AssignableUser]:
    """Directory of users for incident / case assignment dropdowns.
    Read-only; no credentials or hashes are exposed. ADMIN + OFFICER only."""
    stmt = select(User).order_by(User.username)
    if active_only:
        stmt = stmt.where(User.is_active.is_(True))
    return [AssignableUser.model_validate(u) for u in db.execute(stmt).scalars().all()]


@router.get("/audit", response_model=AuditLogPage)
def list_audit_logs(
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    resource: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    q: str | None = Query(default=None, description="substring match on detail"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> AuditLogPage:
    """Read-only projection over the existing `audit_logs` table (FEATURE 11).
    ADMIN only. This is NOT a second audit system -- it just renders the one
    that already exists."""
    conds = []
    if action:
        conds.append(AuditLog.action == action)
    if user_id:
        conds.append(AuditLog.user_id == user_id)
    if resource:
        conds.append(AuditLog.resource == resource)
    if resource_id:
        conds.append(AuditLog.resource_id == resource_id)
    if date_from:
        conds.append(AuditLog.created_at >= date_from)
    if date_to:
        conds.append(AuditLog.created_at <= date_to)
    if q:
        conds.append(AuditLog.detail.ilike(f"%{q.strip()}%"))

    total = db.execute(select(func.count(AuditLog.id)).where(*conds)).scalar() or 0
    rows = db.execute(
        select(AuditLog).where(*conds)
        .order_by(AuditLog.created_at.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    usernames = resolve_usernames(db, [r.user_id for r in rows])
    actions = db.execute(
        select(AuditLog.action).distinct().order_by(AuditLog.action)
    ).scalars().all()

    items = [
        AuditLogRead(
            id=r.id, user_id=r.user_id, username=usernames.get(r.user_id or ""),
            action=r.action, resource=r.resource, resource_id=r.resource_id,
            ip_address=r.ip_address, detail=r.detail, created_at=r.created_at,
        )
        for r in rows
    ]
    return AuditLogPage(
        items=items, total=int(total), limit=limit, offset=offset, actions=list(actions),
    )


class RetentionPurgeResult(BaseModel):
    deleted: int
    retention_days: int


@router.post("/retention/purge", response_model=RetentionPurgeResult)
def run_retention_purge(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> RetentionPurgeResult:
    """Manually run the vehicle_events retention purge now. Same operation
    the periodic background sweep performs. Rows referenced by an alert are
    never deleted; watchlist / alerts / audit_logs are untouched."""
    days = settings.VEHICLE_EVENT_RETENTION_DAYS
    deleted = purge_old_vehicle_events(db, retention_days=days)
    record_audit(
        db,
        action="RETENTION_PURGE",
        user_id=user.id,
        resource="vehicle_events",
        detail={"deleted": deleted, "retention_days": days, "trigger": "manual"},
    )
    return RetentionPurgeResult(deleted=deleted, retention_days=days)
