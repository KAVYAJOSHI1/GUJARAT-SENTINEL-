"""
Notification helper -- the single writer for the `notifications` table.

Like `services/audit.record_audit`, this is best-effort: a notification
write must NEVER crash or block the caller's real work (an event ingest,
an incident assignment, ...). Any failure is logged and swallowed.

Only call this from a real backend event. Do not synthesise notifications
on a timer or fabricate them for effect.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session

from app.models.base import NotificationSeverity
from app.models.notification import Notification

logger = logging.getLogger("sentinel.notifications")


def push_notification(
    db: Session,
    *,
    type: str,
    title: str,
    body: Optional[str] = None,
    severity: NotificationSeverity = NotificationSeverity.INFO,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    target_user_id: Optional[str] = None,
    commit: bool = True,
) -> Optional[Notification]:
    """Create one notification row. Returns the row on success, None on
    failure. When ``commit`` is False the caller is responsible for the
    commit (used when it is already inside its own transaction)."""
    try:
        n = Notification(
            type=type,
            title=title,
            body=body,
            severity=severity,
            resource=resource,
            resource_id=resource_id,
            target_user_id=target_user_id,
        )
        db.add(n)
        if commit:
            db.commit()
            db.refresh(n)
        return n
    except Exception:  # noqa: BLE001 -- notifications must never break the caller
        logger.exception("notification write failed (type=%s)", type)
        if commit:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        return None
