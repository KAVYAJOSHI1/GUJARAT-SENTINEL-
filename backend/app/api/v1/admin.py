"""Admin-only operational endpoints (data retention, ...)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.config import settings
from app.core.rbac import require_roles
from app.database import get_db
from app.models.base import UserRole
from app.schemas.auth import CurrentUser
from app.services.audit import record_audit
from app.services.retention import purge_old_vehicle_events

router = APIRouter()


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
