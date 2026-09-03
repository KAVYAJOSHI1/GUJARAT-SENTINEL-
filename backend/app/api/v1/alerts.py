"""Alerts API — list recent alerts and acknowledge/resolve them."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertAcknowledge, AlertRead
from app.schemas.auth import CurrentUser

router = APIRouter()


@router.get("", response_model=list[AlertRead])
def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
    return db.execute(stmt).scalars().all()


@router.patch("/{alert_id}", response_model=AlertRead)
def acknowledge_alert(
    alert_id: str,
    payload: AlertAcknowledge,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert", alert_id)
    alert.status = payload.status
    alert.acknowledged_by_user_id = user.id
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert
