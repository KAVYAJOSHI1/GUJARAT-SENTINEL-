"""Password hashing and JWT issuance / verification.

Password hashing uses the maintained ``bcrypt`` package directly. The old
``passlib`` 1.7.x + ``bcrypt`` >= 4.1 combination raised
``AttributeError: module 'bcrypt' has no attribute '__about__'`` at import;
calling bcrypt directly avoids that entirely and needs no version pin.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt, JWTError

from app.config import settings

# bcrypt hashes at most 72 bytes of the password.
_BCRYPT_MAX_BYTES = 72


def _to_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(_to_bytes(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, role: str, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
    # A session token must not carry a `purpose` claim -- that marks it as a
    # short-lived single-purpose ticket (WS handshake / media src), which
    # must never be usable as a full API session credential.
    if payload.get("purpose"):
        raise ValueError("Not a session token")
    return payload


# --- short-lived, single-purpose tickets -------------------------------- #
# These exist so the long-lived session JWT never has to appear in a URL
# query string (<img>/<video> src) or a WebSocket subprotocol, where it
# would land in access logs / browser history. A ticket is a normal HS256
# JWT with a very short `exp` and an explicit `purpose` claim; it is issued
# only from a JWT-authenticated POST and is accepted only by the one
# transport it names.

def create_scoped_ticket(subject: str, purpose: str, ttl_seconds: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "purpose": purpose,
        "iat": now,
        "exp": now + timedelta(seconds=max(1, ttl_seconds)),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_scoped_ticket(token: str, expected_purpose: str) -> dict:
    """Validate a short-lived ticket: signature, expiry, and that its
    `purpose` claim matches exactly. Raises ValueError on any mismatch --
    including being handed a normal session JWT (no `purpose` claim)."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError as exc:
        raise ValueError("Invalid or expired ticket") from exc
    if payload.get("purpose") != expected_purpose:
        raise ValueError("Ticket purpose mismatch")
    if not payload.get("sub"):
        raise ValueError("Ticket missing subject")
    return payload
