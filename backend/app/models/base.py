"""Shared model base, mixins and enums used across all SENTINEL tables."""
import enum
import uuid
from datetime import datetime

from sqlmodel import SQLModel, Field


def gen_uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin(SQLModel):
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"onupdate": datetime.utcnow},
    )


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    OFFICER = "OFFICER"
    OPERATOR = "OPERATOR"


class AlertStatus(str, enum.Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    # Phase 11: raised to a supervisor / higher priority. Sits between
    # ACKNOWLEDGED and RESOLVED in the workflow; never auto-set by the
    # watchlist engine (which only ever creates NEW alerts).
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


class PriorityLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CameraStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"


class IncidentStatus(str, enum.Enum):
    """Operational lifecycle of an incident opened from an alert (or standalone)."""

    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class CaseStatus(str, enum.Enum):
    """Lifecycle of a lightweight investigation case grouping incidents/evidence."""

    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    ON_HOLD = "ON_HOLD"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class NotificationSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# Phase 11 -- watchlist categories. Kept as a plain string column (not a DB
# enum) so a control room can extend the taxonomy without a migration; this
# is the canonical set the UI offers and CSV import validates against.
WATCHLIST_CATEGORIES = (
    "STOLEN",
    "WANTED",
    "SUSPICIOUS",
    "MISSING",
    "INVESTIGATION",
    "OTHER",
)


class AlertSource(str, enum.Enum):
    """Phase 12: how an alert row came to exist. The watchlist engine still
    only ever produces WATCHLIST; ANOMALY is written by
    BehaviorAnalyticsService; MANUAL is reserved for operator-created."""

    WATCHLIST = "WATCHLIST"
    ANOMALY = "ANOMALY"
    MANUAL = "MANUAL"


class AnomalyStatus(str, enum.Enum):
    NEW = "NEW"
    REVIEWED = "REVIEWED"
    DISMISSED = "DISMISSED"


class AnomalyKind(str, enum.Enum):
    # One kind only this phase (per the brief). More would be additive.
    STOPPED_VEHICLE = "STOPPED_VEHICLE"


class ConfidenceLevel(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"
