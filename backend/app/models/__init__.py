"""
Import every SQLModel table here so a single `import app.models` registers
the full metadata — required for Alembic autogenerate and for
`SQLModel.metadata.create_all()` during local/dev bootstrap.
"""
from app.models.camera import Camera
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.models.alert import Alert
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.pipeline_status import PipelineStatus
from app.models.incident import Incident, IncidentNote, IncidentEvidence
from app.models.case import Case, CaseNote, CaseIncident, CaseEvidence
from app.models.notification import Notification
from app.models.saved_search import SavedSearch
from app.models.camera_health_history import CameraHealthHistory
from app.models.anomaly_event import AnomalyEvent

__all__ = [
    "Camera", "VehicleEvent", "Watchlist", "Alert", "User", "AuditLog",
    "PipelineStatus",
    "Incident", "IncidentNote", "IncidentEvidence",
    "Case", "CaseNote", "CaseIncident", "CaseEvidence",
    "Notification",
    "SavedSearch", "CameraHealthHistory",
    "AnomalyEvent",
]
