"""cameras.stream_fps / frame_drop_count / reconnect_count / health_updated_at

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-05

Adds the columns POST /api/v1/cameras/health writes to, so the ingestion
side's HealthRegistry (real FPS / frame-drop / reconnect telemetry) can
actually reach the `cameras` row the dashboard reads instead of stopping at
an in-memory-only registry (SENTINEL_System_Audit_Report.md §11/§15).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("stream_fps", sa.Float(), nullable=True))
    op.add_column("cameras", sa.Column("frame_drop_count", sa.Integer(), nullable=True))
    op.add_column("cameras", sa.Column("reconnect_count", sa.Integer(), nullable=True))
    op.add_column("cameras", sa.Column("health_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "health_updated_at")
    op.drop_column("cameras", "reconnect_count")
    op.drop_column("cameras", "frame_drop_count")
    op.drop_column("cameras", "stream_fps")
