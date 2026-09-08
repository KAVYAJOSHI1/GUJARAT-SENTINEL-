"""phase 14 (2/7): camera_transition_stats -- travel-time baselines

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-08

Phase 14 "Advanced Video Intelligence", commit 2 -- Advanced Cross-Camera
Correlation + Camera Transition Intelligence. Additive only. One new table.

  * camera_transition_stats -- one row per ORDERED camera pair (A -> B)
    ever seen as a consecutive same-plate hop, with travel-time statistics
    (min / median / p90 / max / mean seconds) + straight-line distance.
    Recomputed idempotently from existing vehicle_events; unique on
    (from_camera_id, to_camera_id).

The correlation layer itself (VehicleCorrelationService) is pure read logic
over existing rows + vehicle_embeddings + this table -- no schema of its own.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "camera_transition_stats",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("from_camera_id", sa.String(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("to_camera_id", sa.String(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("from_camera_code", sa.String(), nullable=True),
        sa.Column("to_camera_code", sa.String(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("min_seconds", sa.Integer(), nullable=True),
        sa.Column("median_seconds", sa.Integer(), nullable=True),
        sa.Column("p90_seconds", sa.Integer(), nullable=True),
        sa.Column("max_seconds", sa.Integer(), nullable=True),
        sa.Column("mean_seconds", sa.Integer(), nullable=True),
        sa.Column("distance_meters", sa.Float(), nullable=True),
        sa.Column("last_computed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_camera_transition_stats_id", "camera_transition_stats", ["id"])
    op.create_index(
        "ix_camera_transition_stats_from_camera_id", "camera_transition_stats", ["from_camera_id"]
    )
    op.create_index(
        "ix_camera_transition_stats_to_camera_id", "camera_transition_stats", ["to_camera_id"]
    )
    op.create_index(
        "ix_camera_transition_stats_from_camera_code", "camera_transition_stats", ["from_camera_code"]
    )
    op.create_index(
        "ix_camera_transition_stats_to_camera_code", "camera_transition_stats", ["to_camera_code"]
    )
    op.create_index(
        "ux_camera_transition_pair",
        "camera_transition_stats",
        ["from_camera_id", "to_camera_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("camera_transition_stats")
