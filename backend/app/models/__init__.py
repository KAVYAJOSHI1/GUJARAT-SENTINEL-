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

__all__ = ["Camera", "VehicleEvent", "Watchlist", "Alert", "User", "AuditLog"]
