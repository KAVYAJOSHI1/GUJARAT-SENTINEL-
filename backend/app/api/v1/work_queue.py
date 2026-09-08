"""
Officer Work Queue -- "My Work" (FEATURE 12).

Role-aware:
  * ADMIN   -> sees ALL open work (scope="all")
  * OFFICER -> sees work assigned to them + unassigned NEW/ESCALATED alerts
  * OPERATOR-> read-only: assigned-to-them only (usually empty; they can't
              be assigned), so effectively a personal dashboard of nothing
              pending -- still a valid, honest view.

All bounded queries; nothing here mutates state.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.api.v1._enrich import resolve_usernames
from app.database import get_db
from app.models.alert import Alert
from app.models.base import AlertStatus, CaseStatus, IncidentStatus, UserRole
from app.models.case import Case
from app.models.incident import Incident
from app.schemas.auth import CurrentUser
from app.schemas.work_queue import WorkItem, WorkQueueResponse

router = APIRouter()

_OPEN_INCIDENT = Incident.status.notin_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED])
_OPEN_CASE = Case.status.notin_([CaseStatus.RESOLVED, CaseStatus.CLOSED])
_OPEN_ALERT = Alert.status.notin_([AlertStatus.RESOLVED])

_PRIORITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


@router.get("", response_model=WorkQueueResponse)
def my_work(
    sort: str = Query(default="priority", description="priority|newest|oldest"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    is_admin = user.role == UserRole.ADMIN
    scope = "all" if is_admin else "assigned"

    inc_stmt = select(Incident).where(_OPEN_INCIDENT)
    case_stmt = select(Case).where(_OPEN_CASE)
    alert_stmt = select(Alert).where(_OPEN_ALERT)
    if not is_admin:
        inc_stmt = inc_stmt.where(Incident.assigned_to_user_id == user.id)
        case_stmt = case_stmt.where(Case.assigned_to_user_id == user.id)
        alert_stmt = alert_stmt.where(
            or_(
                Alert.assigned_to_user_id == user.id,
                Alert.status.in_([AlertStatus.NEW, AlertStatus.ESCALATED]),
            )
        )

    incidents = db.execute(inc_stmt.limit(limit)).scalars().all()
    cases = db.execute(case_stmt.limit(limit)).scalars().all()
    alerts = db.execute(alert_stmt.order_by(Alert.created_at.desc()).limit(limit)).scalars().all()

    usernames = resolve_usernames(
        db,
        [i.assigned_to_user_id for i in incidents]
        + [c.assigned_to_user_id for c in cases]
        + [a.assigned_to_user_id for a in alerts],
    )

    def _inc_item(i: Incident) -> WorkItem:
        return WorkItem(
            kind="INCIDENT", id=i.id, ref=i.incident_number, title=i.title,
            status=i.status.value, priority=i.priority_level.value,
            created_at=i.created_at, updated_at=i.updated_at,
            assigned_to_username=usernames.get(i.assigned_to_user_id or ""),
            plate=i.plate_number_normalized, href=f"/incidents/{i.id}",
        )

    def _case_item(c: Case) -> WorkItem:
        return WorkItem(
            kind="CASE", id=c.id, ref=c.case_number, title=c.title,
            status=c.status.value, priority=c.priority_level.value,
            created_at=c.created_at, updated_at=c.updated_at,
            assigned_to_username=usernames.get(c.assigned_to_user_id or ""),
            plate=c.primary_plate_normalized, href=f"/cases/{c.id}",
        )

    def _alert_item(a: Alert) -> WorkItem:
        return WorkItem(
            kind="ALERT", id=a.id, ref=a.plate_number_normalized,
            title=f"Watchlist match — {a.plate_number_normalized}",
            status=a.status.value, priority=a.priority_level.value,
            created_at=a.created_at, updated_at=None,
            assigned_to_username=usernames.get(a.assigned_to_user_id or ""),
            plate=a.plate_number_normalized, href=f"/alerts?focus={a.id}",
        )

    inc_items = [_inc_item(i) for i in incidents]
    case_items = [_case_item(c) for c in cases]
    alert_items = [_alert_item(a) for a in alerts]

    def _key(w: WorkItem):
        if sort == "newest":
            return (-w.created_at.timestamp(),)
        if sort == "oldest":
            return (w.created_at.timestamp(),)
        return (_PRIORITY_RANK.get(w.priority, 9), -w.created_at.timestamp())

    inc_items.sort(key=_key)
    case_items.sort(key=_key)
    alert_items.sort(key=_key)

    counts = {
        "incidents": len(inc_items),
        "cases": len(case_items),
        "alerts": len(alert_items),
        "unacknowledged_alerts": sum(1 for a in alerts if a.status == AlertStatus.NEW),
        "escalated_alerts": sum(1 for a in alerts if a.status == AlertStatus.ESCALATED),
        "total": len(inc_items) + len(case_items) + len(alert_items),
    }
    return WorkQueueResponse(
        scope=scope, counts=counts,
        incidents=inc_items, cases=case_items, alerts=alert_items,
    )
