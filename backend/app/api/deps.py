"""Shared FastAPI dependencies: DB session re-export + JWT current-user resolver."""
import hmac
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.config import settings
from app.core.security import decode_access_token, decode_scoped_ticket
from app.database import get_db
from app.models.user import User
from app.schemas.auth import CurrentUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> CurrentUser:
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": str(exc)},
        ) from exc

    user_id = payload.get("sub")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User not found or inactive."},
        )
    return CurrentUser(id=user.id, username=user.username, role=user.role)


def verify_bearer_header_or_query(
    token: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Authorise a media read (evidence image / mock-camera video) that a
    browser ``<img>``/``<video>`` requests.

    Two accepted forms:
      * ``Authorization: Bearer <session JWT>``  -- for a fetch()/XHR caller
        that CAN set headers.
      * ``?token=<media ticket>``  -- for a bare ``<img src>``. This path
        now requires a short-lived, ``purpose="media"`` ticket (issued from
        POST /api/v1/auth/media-ticket), **not** the long-lived session
        JWT. A session JWT passed as ``?token=`` is rejected, so the
        session credential never lands in an access log or browser history.

    No DB lookup. Returns the ``sub`` claim (user id) for audit logging.
    Never returns or logs the raw token/ticket."""
    header_raw = None
    if authorization and authorization.lower().startswith("bearer "):
        header_raw = authorization.split(" ", 1)[1].strip()

    if header_raw:
        try:
            payload = decode_access_token(header_raw)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail={"code": "INVALID_TOKEN"})
        return payload.get("sub") or "ok"

    if token:
        try:
            payload = decode_scoped_ticket(token, "media")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail={"code": "INVALID_MEDIA_TICKET"})
        return payload.get("sub") or "ok"

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                        detail={"code": "NOT_AUTHENTICATED"})


def require_ingest_auth(
    x_ingest_key: Optional[str] = Header(default=None, alias="X-Ingest-Key"),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> str:
    """Auth for the AI event-ingestion endpoint.

    Accepts EITHER:
      * a valid ``X-Ingest-Key`` header matching ``settings.INGEST_API_KEY``
        (the AI pipeline's service credential), OR
      * a normal operator JWT (``Authorization: Bearer ...``).

    If ``INGEST_API_KEY`` is unset, only the JWT path is available.
    Returns a short string describing which path authorised the request.
    """
    key = settings.INGEST_API_KEY
    if key and x_ingest_key and hmac.compare_digest(str(x_ingest_key), str(key)):
        return "ingest-key"

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_TOKEN", "message": "Invalid or expired token."},
            )
        user = db.get(User, payload.get("sub"))
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "USER_NOT_FOUND", "message": "User not found or inactive."},
            )
        return f"jwt:{user.username}"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "NOT_AUTHENTICATED", "message": "Provide X-Ingest-Key or a Bearer token."},
        headers={"WWW-Authenticate": "Bearer"},
    )
