"""Notification center schemas (phase brief FEATURE 12)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.models.base import NotificationSeverity


class NotificationRead(BaseModel):
    id: str
    type: str
    severity: NotificationSeverity
    title: str
    body: Optional[str] = None
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    target_user_id: Optional[str] = None
    read: bool
    read_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationPage(BaseModel):
    items: List[NotificationRead]
    total: int
    unread: int
    limit: int
    offset: int


class UnreadCount(BaseModel):
    unread: int
