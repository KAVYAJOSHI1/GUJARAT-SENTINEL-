"""
saved_searches: an officer-saved Advanced-Search / investigation query
(phase brief FEATURE 2 "Saved Investigations").

Only the SEARCH CRITERIA are stored (a small JSON blob) -- never the result
set. Opening a saved search re-runs it against live data, so a saved
investigation always reflects the current database.
"""
from typing import Any, Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field

from app.models.base import TimestampMixin, gen_uuid


class SavedSearch(TimestampMixin, table=True):
    __tablename__ = "saved_searches"

    id: str = Field(default_factory=gen_uuid, primary_key=True, index=True)
    title: str = Field(nullable=False)
    description: Optional[str] = Field(default=None, nullable=True)
    # The Advanced-Search filter payload (plate, vehicle_type, camera, date
    # range, sort, ...). Bounded by the search schema -- never a result set.
    params: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_by_user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", nullable=True, index=True
    )

    __table_args__ = (Index("ix_saved_searches_owner_created", "created_by_user_id", "created_at"),)
