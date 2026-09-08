"""Shared timeline entry schema for Incident / Case detail (FEATURE 7 / 8).

A timeline is DERIVED at read time from existing rows (audit_logs, notes,
evidence links, vehicle_events, the entity's own timestamps). No new
event table is introduced.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class TimelineEntry(BaseModel):
    timestamp: datetime
    category: str        # ALERT | INCIDENT | CASE | EVIDENCE | NOTE | VEHICLE | ACTIVITY | STATUS
    action: str          # short verb phrase
    actor: Optional[str] = None       # username, or None for system/AI
    detail: Optional[str] = None
    ref_kind: Optional[str] = None    # incident | case | alert | vehicle_event | note
    ref_id: Optional[str] = None


class Timeline(BaseModel):
    entries: List[TimelineEntry]
    categories: List[str]  # distinct categories present, for the filter UI
