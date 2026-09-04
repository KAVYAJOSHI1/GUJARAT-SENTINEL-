"""
Camera identity resolution.

The AI pipeline tags every event with an external camera identifier (the
Sentinel catalogue id, e.g. ``"cam04"``). The database keys cameras by a UUID
(`cameras.id`). This module maps one to the other, using the `cameras.code`
column, and can auto-onboard a camera the first time it is seen so a live feed
is never dropped just because someone forgot to pre-register it.

No UUIDs are invented and no mapping is hard-coded: the external ``code`` *is*
the camera's identity, and a freshly onboarded row stores exactly that.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlmodel import Session

from app.models.base import CameraStatus
from app.models.camera import Camera


def _point_wkt(lat: Optional[float], lon: Optional[float]) -> Optional[str]:
    if lat is None or lon is None:
        return None
    return f"SRID=4326;POINT({lon} {lat})"


def find_camera(db: Session, camera_ref: str) -> Optional[Camera]:
    """Look a camera up by UUID (`cameras.id`) or external code (`cameras.code`)."""
    if not camera_ref:
        return None
    cam = db.get(Camera, camera_ref)
    if cam is not None:
        return cam
    return db.execute(
        select(Camera).where(Camera.code == camera_ref)
    ).scalar_one_or_none()


def resolve_camera(
    db: Session,
    camera_ref: str,
    *,
    name: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    rtsp_url: Optional[str] = None,
    auto_create: bool = True,
) -> Optional[Camera]:
    """Return the `Camera` for ``camera_ref``.

    If it does not exist and ``auto_create`` is True, onboard it: a new row
    with ``code = camera_ref`` (and name / location if supplied). Returns
    ``None`` only when the camera is unknown and ``auto_create`` is False.
    """
    cam = find_camera(db, camera_ref)
    if cam is not None:
        # opportunistically backfill a missing location from the event
        updated = False
        if cam.location is None and latitude is not None and longitude is not None:
            cam.location = _point_wkt(latitude, longitude)
            updated = True
        if not cam.rtsp_url and rtsp_url:
            cam.rtsp_url = rtsp_url
            updated = True
        if updated:
            db.add(cam)
            db.commit()
            db.refresh(cam)
        return cam

    if not auto_create:
        return None

    cam = Camera(
        code=camera_ref,
        name=name or camera_ref,
        status=CameraStatus.ONLINE,
        rtsp_url=rtsp_url,
        location=_point_wkt(latitude, longitude),
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)
    return cam


def upsert_camera_from_registry(db: Session, entry: dict) -> Camera:
    """Upsert one camera-catalogue entry (keyed by its external code)."""
    code = str(
        entry.get("code")
        or entry.get("camera_id")
        or entry.get("id")
        or ""
    ).strip()
    if not code:
        raise ValueError("registry entry has no code / camera_id / id")

    lat = entry.get("latitude")
    lon = entry.get("longitude")
    loc = entry.get("location") or {}
    if lat is None:
        lat = loc.get("latitude") or loc.get("lat")
    if lon is None:
        lon = loc.get("longitude") or loc.get("lng") or loc.get("lon")

    name = entry.get("name") or code
    rtsp_url = entry.get("rtsp_url") or entry.get("stream_url")

    cam = find_camera(db, code)
    if cam is None:
        cam = Camera(code=code)

    cam.name = name
    if rtsp_url:
        cam.rtsp_url = rtsp_url
    if lat is not None and lon is not None:
        cam.location = _point_wkt(float(lat), float(lon))
    if entry.get("location_desc") or entry.get("resolved_address"):
        cam.location_desc = entry.get("location_desc") or entry.get("resolved_address")
    if entry.get("status") in ("ONLINE", "OFFLINE", "DEGRADED"):
        cam.status = CameraStatus(entry["status"])

    db.add(cam)
    db.commit()
    db.refresh(cam)
    return cam
