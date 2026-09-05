"""JWT login endpoint + short-lived transport tickets.

Registration is intentionally admin-only / out of scope here.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel import Session

from app.config import settings
from app.core.security import (
    create_access_token,
    create_scoped_ticket,
    decode_access_token,
    verify_password,
)
from app.database import get_db
from app.models.user import User
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse
from app.services.audit import client_ip, record_audit
from app.services.rate_limit import login_rate_limiter

router = APIRouter()


class TicketResponse(BaseModel):
    ticket: str
    expires_in: int
    purpose: str


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = client_ip(request)
    rl_key = login_rate_limiter.make_key(ip, payload.username)

    retry_after = login_rate_limiter.check(rl_key)
    if retry_after is not None:
        # Do NOT reveal whether the username exists or how close the
        # password was -- only that too many attempts have been made.
        record_audit(
            db,
            action="LOGIN_RATE_LIMITED",
            resource="auth",
            detail={"username": payload.username, "retry_after_seconds": retry_after},
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "TOO_MANY_ATTEMPTS",
                "message": "Too many login attempts. Try again later.",
            },
            headers={"Retry-After": str(retry_after)},
        )

    user = db.execute(
        select(User).where(User.username == payload.username)
    ).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        # Never log the attempted password -- only that a login attempt
        # failed and for which username, so brute-force patterns are at
        # least visible in the audit trail.
        login_rate_limiter.record_failure(rl_key)
        record_audit(
            db,
            action="LOGIN_FAILED",
            user_id=user.id if user else None,
            resource="auth",
            detail={"username": payload.username, "reason": "invalid_credentials"},
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password."},
        )
    if not user.is_active:
        login_rate_limiter.record_failure(rl_key)
        record_audit(
            db,
            action="LOGIN_FAILED",
            user_id=user.id,
            resource="auth",
            detail={"username": payload.username, "reason": "account_disabled"},
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "USER_DISABLED", "message": "This account is disabled."},
        )

    login_rate_limiter.reset(rl_key)
    token = create_access_token(subject=user.id, role=user.role.value)
    record_audit(
        db,
        action="LOGIN_SUCCESS",
        user_id=user.id,
        resource="auth",
        detail={"username": user.username},
        ip_address=ip,
    )
    return TokenResponse(access_token=token)


def _current_user(request: Request, db: Session) -> CurrentUser:
    """Resolve the session JWT from the Authorization header (same checks as
    app.api.deps.get_current_user). Kept local so the ticket routes don't
    add an import edge from this module to app.api.deps at import time."""
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "NOT_AUTHENTICATED"})
    raw = auth.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": str(exc)},
        ) from exc
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User not found or inactive."},
        )
    return CurrentUser(id=user.id, username=user.username, role=user.role)


@router.post("/ws-ticket", response_model=TicketResponse)
def issue_ws_ticket(request: Request, db: Session = Depends(get_db)) -> TicketResponse:
    """Exchange a valid session JWT for a single-purpose, ~60s WebSocket
    handshake ticket. The dashboard fetches one immediately before opening
    /ws/alerts, so the long-lived session JWT never travels as a WS
    subprotocol value (where a header-logging proxy could capture it)."""
    user = _current_user(request, db)
    ttl = settings.WS_TICKET_TTL_SECONDS
    ticket = create_scoped_ticket(subject=user.id, purpose="ws", ttl_seconds=ttl)
    return TicketResponse(ticket=ticket, expires_in=ttl, purpose="ws")


@router.post("/media-ticket", response_model=TicketResponse)
def issue_media_ticket(request: Request, db: Session = Depends(get_db)) -> TicketResponse:
    """Exchange a valid session JWT for a short-lived ``purpose="media"``
    ticket used as ``?token=`` on evidence-image / mock-video ``<img>``/
    ``<video>`` requests, so the session JWT never appears in a URL."""
    user = _current_user(request, db)
    ttl = settings.MEDIA_TICKET_TTL_SECONDS
    ticket = create_scoped_ticket(subject=user.id, purpose="media", ttl_seconds=ttl)
    return TicketResponse(ticket=ticket, expires_in=ttl, purpose="media")
