"""JWT login endpoint. Registration is intentionally admin-only / out of scope here."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlmodel import Session

from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.execute(
        select(User).where(User.username == payload.username)
    ).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password."},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "USER_DISABLED", "message": "This account is disabled."},
        )

    token = create_access_token(subject=user.id, role=user.role.value)
    return TokenResponse(access_token=token)
