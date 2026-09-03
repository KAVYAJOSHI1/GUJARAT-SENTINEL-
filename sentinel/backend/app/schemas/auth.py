"""Auth request/response schemas for JWT login flow."""
from pydantic import BaseModel

from app.models.base import UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    id: str
    username: str
    role: UserRole
