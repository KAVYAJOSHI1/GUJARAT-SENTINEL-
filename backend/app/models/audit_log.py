"""audit_logs: append-only record of system access / sensitive actions."""
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import TimestampMixin, gen_uuid


class AuditLog(TimestampMixin, table=True):
    __tablename__ = "audit_logs"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)
    user_id: Optional[str] = Field(default=None, foreign_key="users.id", nullable=True)
    action: str = Field(nullable=False, index=True)
    resource: Optional[str] = Field(default=None, nullable=True)
    resource_id: Optional[str] = Field(default=None, nullable=True)
    ip_address: Optional[str] = Field(default=None, nullable=True)
    detail: Optional[str] = Field(default=None, nullable=True)

    __table_args__ = (Index("ix_audit_logs_action_btree", "action"),)
