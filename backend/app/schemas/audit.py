"""Audit / Activity center read schemas (phase brief FEATURE 11).

Read-only projection over the existing `audit_logs` table -- NOT a second
audit system.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    action: str
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogPage(BaseModel):
    items: List[AuditLogRead]
    total: int
    limit: int
    offset: int
    actions: List[str] = []  # distinct action values, for the filter dropdown
