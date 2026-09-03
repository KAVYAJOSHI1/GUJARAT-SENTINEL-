"""users: credentials + RBAC role for ADMIN / OFFICER / OPERATOR."""
from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import TimestampMixin, UserRole, gen_uuid


class User(TimestampMixin, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)
    username: str = Field(nullable=False, unique=True, index=True)
    email: str = Field(nullable=False, unique=True, index=True)
    hashed_password: str = Field(nullable=False)
    role: UserRole = Field(default=UserRole.OPERATOR, nullable=False, index=True)
    is_active: bool = Field(default=True, nullable=False)

    __table_args__ = (Index("ix_users_role_btree", "role"),)
