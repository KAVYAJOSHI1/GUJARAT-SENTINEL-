"""
Shared read-side helpers for the operational routers (incidents / cases /
notifications / audit).

These do BULK lookups (one query for a set of ids) so the list endpoints
never fan out into an N+1 pattern -- see the phase brief "Do not introduce
N+1 database queries".
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import func, select
from sqlmodel import Session

from app.models.camera import Camera
from app.models.incident import Incident
from app.models.user import User


def resolve_usernames(db: Session, user_ids: Iterable[str | None]) -> dict[str, str]:
    ids = {u for u in user_ids if u}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.username).where(User.id.in_(ids))).all()
    return {uid: uname for uid, uname in rows}


def resolve_cameras(db: Session, camera_ids: Iterable[str | None]) -> dict[str, dict]:
    """id -> {code, name, location_desc, latitude, longitude}."""
    ids = {c for c in camera_ids if c}
    if not ids:
        return {}
    rows = db.execute(
        select(
            Camera.id,
            Camera.code,
            Camera.name,
            Camera.location_desc,
            ST_Y(Camera.location),
            ST_X(Camera.location),
        ).where(Camera.id.in_(ids))
    ).all()
    return {
        cid: {
            "code": code,
            "name": name,
            "location_desc": desc,
            "latitude": lat,
            "longitude": lon,
        }
        for cid, code, name, desc, lat, lon in rows
    }


def next_sequence_number(db: Session, prefix: str, model, column) -> str:
    """Generate 'PREFIX-YYYY-NNNN' from a per-year running count of `model`.

    Not strictly race-free under heavy concurrent creation, but the column
    is UNIQUE so a collision fails loudly rather than silently duplicating;
    control-room create rates make a real collision vanishingly unlikely.
    """
    year = datetime.utcnow().year
    like = f"{prefix}-{year}-%"
    count = db.execute(
        select(func.count()).select_from(model).where(column.like(like))
    ).scalar() or 0
    return f"{prefix}-{year}-{count + 1:04d}"
