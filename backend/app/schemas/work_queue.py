"""Officer Work Queue schema (FEATURE 12)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class WorkItem(BaseModel):
    kind: str          # INCIDENT | CASE | ALERT
    id: str
    ref: str           # INC-.. / CASE-.. / alert id
    title: str
    status: str
    priority: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    assigned_to_username: Optional[str] = None
    plate: Optional[str] = None
    href: str


class WorkQueueResponse(BaseModel):
    scope: str         # "assigned" (OFFICER/OPERATOR) | "all" (ADMIN)
    counts: dict[str, int]
    incidents: List[WorkItem]
    cases: List[WorkItem]
    alerts: List[WorkItem]
