"""
Camera effective-status transition recorder (FEATURE 5 + FEATURE 13
camera offline/recovered notifications).

A row + a notification are written ONLY on a real change in a camera's
*effective* status. Called from:
  * cameras.push_camera_health  (a real ingestion health push)
  * app.main._camera_staleness_watcher_loop  (a camera that went silent)

Dedup: the last camera_health_history row for the camera is compared to
the new effective status -- an unchanged status writes nothing, so
repeated pushes / repeated watcher ticks never spam.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlmodel import Session

from app.models.base import CameraStatus, NotificationSeverity
from app.models.camera import Camera
from app.models.camera_health_history import CameraHealthHistory
from app.services.notifications import push_notification

logger = logging.getLogger("sentinel.camera_health")


def _last_recorded_status(db: Session, camera_id: str) -> Optional[CameraStatus]:
    row = db.execute(
        select(CameraHealthHistory.status)
        .where(CameraHealthHistory.camera_id == camera_id)
        .order_by(CameraHealthHistory.detected_at.desc())
        .limit(1)
    ).first()
    return row[0] if row else None


def record_transition_if_changed(
    db: Session,
    camera: Camera,
    new_effective: CameraStatus,
    *,
    source: str,
    stream_fps: float | None = None,
    reconnect_count: int | None = None,
    last_frame_age_seconds: float | None = None,
    commit: bool = True,
) -> Optional[CameraHealthHistory]:
    """Write a transition row + notification iff the effective status differs
    from the last recorded one. Best-effort: never raises."""
    try:
        prev = _last_recorded_status(db, camera.id)
        if prev == new_effective:
            return None
        # First-ever observation of an ONLINE camera isn't a noteworthy
        # "transition" -- only record it once something changes later.
        if prev is None and new_effective == CameraStatus.ONLINE:
            row = CameraHealthHistory(
                camera_id=camera.id, status=new_effective, previous_status=None,
                stream_fps=stream_fps, reconnect_count=reconnect_count,
                last_frame_age_seconds=last_frame_age_seconds, source=source,
                detected_at=datetime.utcnow(),
            )
            db.add(row)
            if commit:
                db.commit()
            return row

        row = CameraHealthHistory(
            camera_id=camera.id, status=new_effective, previous_status=prev,
            stream_fps=stream_fps, reconnect_count=reconnect_count,
            last_frame_age_seconds=last_frame_age_seconds, source=source,
            detected_at=datetime.utcnow(),
        )
        db.add(row)

        # notification only for the operationally-significant edges
        code = camera.code or camera.name
        if new_effective == CameraStatus.OFFLINE and prev in (
            CameraStatus.ONLINE, CameraStatus.DEGRADED, None
        ):
            push_notification(
                db, type="CAMERA_OFFLINE", title=f"Camera offline — {code}",
                body=camera.location_desc or camera.name,
                severity=NotificationSeverity.WARNING,
                resource="camera", resource_id=camera.id, commit=False,
            )
        elif new_effective == CameraStatus.ONLINE and prev == CameraStatus.OFFLINE:
            push_notification(
                db, type="CAMERA_RECOVERED", title=f"Camera recovered — {code}",
                body=camera.location_desc or camera.name,
                severity=NotificationSeverity.INFO,
                resource="camera", resource_id=camera.id, commit=False,
            )

        if commit:
            db.commit()
        return row
    except Exception:  # noqa: BLE001 -- health history must never break a push
        logger.exception("camera health transition record failed (camera=%s)", camera.id)
        if commit:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        return None
