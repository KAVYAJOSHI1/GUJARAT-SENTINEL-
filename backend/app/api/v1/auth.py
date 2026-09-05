"""JWT login endpoint. Registration is intentionally admin-only / out of scope here."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlmodel import Session

from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.audit import client_ip, record_audit

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = client_ip(request)
    user = db.execute(
        select(User).where(User.username == payload.username)
    ).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        # Never log the attempted password -- only that a login attempt
        # failed and for which username, so brute-force patterns are at
        # least visible in the audit trail.
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
