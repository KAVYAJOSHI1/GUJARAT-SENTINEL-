"""Incident management request/response schemas (phase brief FEATURE 1)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.base import IncidentStatus, PriorityLevel


class IncidentCreate(BaseModel):
    # Promote an existing alert -> incident. When set, title / plate /
    # camera / vehicle_event / priority are filled from the alert unless
    # explicitly overridden below.
    alert_id: Optional[str] = None

    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority_level: Optional[PriorityLevel] = None

    # Standalone incident (no alert) may still reference these directly.
    plate_number: Optional[str] = None
    camera_id: Optional[str] = None
    vehicle_event_id: Optional[str] = None


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority_level: Optional[PriorityLevel] = None
    status: Optional[IncidentStatus] = None


class IncidentAssign(BaseModel):
    user_id: Optional[str] = None  # None -> unassign


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus


class IncidentNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class IncidentNoteRead(BaseModel):
    id: str
    incident_id: str
    author_user_id: Optional[str] = None
    author_username: Optional[str] = None
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


class IncidentEvidenceCreate(BaseModel):
    vehicle_event_id: str
    note: Optional[str] = None


class IncidentEvidenceRead(BaseModel):
    id: str
    incident_id: str
    vehicle_event_id: str
    note: Optional[str] = None
    added_by_user_id: Optional[str] = None
    added_by_username: Optional[str] = None
    created_at: datetime
    # enrichment from the vehicle_event / camera
    plate_number: Optional[str] = None
    camera_id: Optional[str] = None
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    event_timestamp: Optional[datetime] = None
    has_snapshot: bool = False

    class Config:
        from_attributes = True


class IncidentRead(BaseModel):
    id: str
    incident_number: str
    title: str
    description: Optional[str] = None
    category: str
    priority_level: PriorityLevel
    status: IncidentStatus

    alert_id: Optional[str] = None
    vehicle_event_id: Optional[str] = None
    camera_id: Optional[str] = None
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    location_desc: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    plate_number_normalized: Optional[str] = None

    created_by_user_id: Optional[str] = None
    created_by_username: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    assigned_to_username: Optional[str] = None
    acknowledged_by_user_id: Optional[str] = None
    acknowledged_by_username: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by_user_id: Optional[str] = None
    resolved_by_username: Optional[str] = None
    resolved_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    note_count: int = 0
    evidence_count: int = 0

    class Config:
        from_attributes = True


class IncidentDetail(IncidentRead):
    notes: List[IncidentNoteRead] = []
    evidence: List[IncidentEvidenceRead] = []
    case_numbers: List[str] = []
    # count of live camera sightings for the vehicle of interest (derived)
    related_sighting_count: int = 0


class IncidentPage(BaseModel):
    items: List[IncidentRead]
    total: int
    limit: int
    offset: int
