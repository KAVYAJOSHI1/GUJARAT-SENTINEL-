"""
Reusable audit-logging helper — writes to the existing `audit_logs` table
(`app.models.audit_log.AuditLog`), which until this pass had a migrated
schema and zero writers (SENTINEL_System_Audit_Report.md §10/§15).

This does NOT introduce a second/parallel audit mechanism: it is a thin,
shared wrapper around the one `AuditLog` model + table that already existed.

Design rule (per the audit): audit logging must be reliable but must NEVER
be able to crash or block the caller's real work (login, a vehicle
detection, an alert ack, ...). Every write here is therefore best-effort —
any failure is logged and swallowed, never re-raised.

DO NOT ever pass secrets into `detail`: passwords, JWTs, RTSP credentials,
the ingest API key, or any other credential. Callers are responsible for
only passing safe, already-non-secret fields (plate numbers, resource ids,
counts, usernames, status values, etc.) — this module does not attempt to
scrub arbitrary input, it just never logs anything of that shape itself.
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Union

from sqlmodel import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger("sentinel.audit")

_MAX_DETAIL_CHARS = 4000


def record_audit(
    db: Session,
    *,
    action: str,
    user_id: Optional[str] = None,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    detail: Optional[Union[dict, str]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Best-effort audit write.

    Commits its own row in the given session. Never raises — a failure here
    is logged and the session is rolled back to a clean state, but the
    caller's own already-committed work is untouched (this is always called
    after the primary action's own commit, never instead of it).
    """
    try:
        safe_detail: Optional[str]
        if isinstance(detail, dict):
            safe_detail = json.dumps(detail, default=str)[:_MAX_DETAIL_CHARS]
        elif isinstance(detail, str):
            safe_detail = detail[:_MAX_DETAIL_CHARS]
        else:
            safe_detail = None

        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            detail=safe_detail,
            ip_address=ip_address,
        )
        db.add(entry)
        db.commit()
    except Exception:  # noqa: BLE001 — audit logging must never break the caller
        logger.exception("audit log write failed (action=%s, resource=%s)", action, resource)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def client_ip(request) -> Optional[str]:
    """Best-effort client IP extraction from a FastAPI/Starlette Request.
    Never raises -- returns None if it can't be determined."""
    try:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else None
    except Exception:  # noqa: BLE001
        return None
