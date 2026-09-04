"""camera.code + vehicle_events.camera_code / track_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-04

Adds the stable external camera identifier (``cameras.code``, e.g. "cam04")
that the AI pipeline references, plus ``vehicle_events.camera_code`` (raw id
kept for traceability) and ``vehicle_events.track_id`` (persistent ByteTrack
id for the sighting).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("code", sa.String(), nullable=True))
    op.create_index("ix_cameras_code", "cameras", ["code"], unique=True)

    op.add_column("vehicle_events", sa.Column("camera_code", sa.String(), nullable=True))
    op.add_column("vehicle_events", sa.Column("track_id", sa.Integer(), nullable=True))
    op.create_index("ix_vehicle_events_camera_code", "vehicle_events", ["camera_code"])
    op.create_index("ix_vehicle_events_track_id", "vehicle_events", ["track_id"])


def downgrade() -> None:
    op.drop_index("ix_vehicle_events_track_id", table_name="vehicle_events")
    op.drop_index("ix_vehicle_events_camera_code", table_name="vehicle_events")
    op.drop_column("vehicle_events", "track_id")
    op.drop_column("vehicle_events", "camera_code")

    op.drop_index("ix_cameras_code", table_name="cameras")
    op.drop_column("cameras", "code")
