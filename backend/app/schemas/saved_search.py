"""Saved Investigations schemas (FEATURE 2)."""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SavedSearchCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)


class SavedSearchUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    params: Optional[dict[str, Any]] = None


class SavedSearchRead(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    created_by_user_id: Optional[str] = None
    created_by_username: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SavedSearchList(BaseModel):
    items: List[SavedSearchRead]
    total: int
