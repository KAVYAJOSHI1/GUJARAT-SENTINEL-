"""
watchlist: blacklisted / stolen vehicle registration entries.
Unique B-Tree index on the normalized plate enforces O(log n) exact-match
lookups for the watchlist engine and blocks duplicate entries (HTTP 409).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import TimestampMixin, PriorityLevel, gen_uuid


class Watchlist(TimestampMixin, table=True):
    __tablename__ = "watchlist"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)
    plate_number: str = Field(nullable=False)
    plate_number_normalized: str = Field(nullable=False, unique=True, index=True)

    offense_category: str = Field(nullable=False)
    priority_level: PriorityLevel = Field(default=PriorityLevel.MEDIUM, nullable=False)

    reason: Optional[str] = Field(default=None, nullable=True)
    added_by_user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    active: bool = Field(default=True, nullable=False, index=True)
    expires_at: Optional[datetime] = Field(default=None, nullable=True)

    __table_args__ = (
        Index("ix_watchlist_plate_btree", "plate_number_normalized", unique=True),
        Index("ix_watchlist_priority_btree", "priority_level"),
    )
