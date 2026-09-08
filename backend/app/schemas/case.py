"""Case management request/response schemas (phase brief FEATURE 2)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.base import CaseStatus, PriorityLevel
from app.schemas.incident import IncidentRead


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    priority_level: Optional[PriorityLevel] = None
    primary_plate_number: Optional[str] = None


class CaseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority_level: Optional[PriorityLevel] = None
    status: Optional[CaseStatus] = None
    primary_plate_number: Optional[str] = None


class CaseAssign(BaseModel):
    user_id: Optional[str] = None


class CaseNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class CaseNoteRead(BaseModel):
    id: str
    case_id: str
    author_user_id: Optional[str] = None
    author_username: Optional[str] = None
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


class CaseIncidentAttach(BaseModel):
    incident_id: str


class CaseEvidenceCreate(BaseModel):
    vehicle_event_id: str
    note: Optional[str] = None


class CaseEvidenceRead(BaseModel):
    id: str
    case_id: str
    vehicle_event_id: str
    note: Optional[str] = None
    added_by_user_id: Optional[str] = None
    added_by_username: Optional[str] = None
    created_at: datetime
    plate_number: Optional[str] = None
    camera_id: Optional[str] = None
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    event_timestamp: Optional[datetime] = None
    has_snapshot: bool = False

    class Config:
        from_attributes = True


class CaseTimelineEntry(BaseModel):
    """A unified, chronological view row derived from the case's linked
    incidents + evidence + notes -- never stored, always recomputed."""

    timestamp: datetime
    kind: str  # INCIDENT | EVIDENCE | SIGHTING | NOTE | CASE_CREATED
    label: str
    ref_id: Optional[str] = None


class CaseRead(BaseModel):
    id: str
    case_number: str
    title: str
    description: Optional[str] = None
    priority_level: PriorityLevel
    status: CaseStatus
    primary_plate_normalized: Optional[str] = None

    created_by_user_id: Optional[str] = None
    created_by_username: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    assigned_to_username: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    incident_count: int = 0
    evidence_count: int = 0
    note_count: int = 0

    class Config:
        from_attributes = True


class CaseDetail(CaseRead):
    incidents: List[IncidentRead] = []
    evidence: List[CaseEvidenceRead] = []
    notes: List[CaseNoteRead] = []
    timeline: List[CaseTimelineEntry] = []
    # distinct camera sightings for the primary vehicle (derived, live)
    sighting_count: int = 0


class CasePage(BaseModel):
    items: List[CaseRead]
    total: int
    limit: int
    offset: int
