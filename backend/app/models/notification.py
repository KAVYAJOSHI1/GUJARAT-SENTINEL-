"""
notifications: operational events surfaced to the control room.

Every row is produced by a REAL backend event (an alert was created, an
incident/case was assigned, ...). Nothing here is synthesised on a timer
or fabricated for effect -- if there is no event, there is no row.

`target_user_id`:
  * NULL  -> a broadcast operational event every operator should see
            (watchlist match, high alert, ...).
  * set   -> directed at one officer ("incident INC-2026-0007 assigned to
            you"). The list endpoint returns broadcasts + the caller's own.

Read state (`read` / `read_at`) is per-row and shared -- appropriate for a
shared control-room board. A per-user read ledger is a future refinement.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import NotificationSeverity, TimestampMixin, gen_uuid


class Notification(TimestampMixin, table=True):
    __tablename__ = "notifications"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)

    # Machine type, e.g. WATCHLIST_MATCH / HIGH_ALERT / INCIDENT_ASSIGNED /
    # CASE_ASSIGNED / INCIDENT_CREATED. String (not a DB enum) so new event
    # types don't need a migration.
    type: str = Field(nullable=False, index=True)
    severity: NotificationSeverity = Field(default=NotificationSeverity.INFO, nullable=False)

    title: str = Field(nullable=False)
    body: Optional[str] = Field(default=None, nullable=True)

    # Optional pointer to the resource this is about, so the UI can deep-link.
    resource: Optional[str] = Field(default=None, nullable=True)
    resource_id: Optional[str] = Field(default=None, nullable=True)

    target_user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", nullable=True, index=True
    )

    read: bool = Field(default=False, nullable=False, index=True)
    read_at: Optional[datetime] = Field(default=None, nullable=True)

    __table_args__ = (Index("ix_notifications_read_created", "read", "created_at"),)
