"""phase 11: advanced search, watchlist mgmt, alert escalation, camera health history

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-08

Phase 11 "advanced operational investigation features" -- additive only,
nothing in the existing CCTV / ANPR / watchlist-match / alert-generation
pipeline is redesigned.

  * pg_trgm + GIN indexes on the two normalised-plate columns -> bounded
    partial-plate search (ILIKE '%...%') for the unified Advanced Search
    without a sequential scan.
  * watchlist: description / effective_from / updated_by_user_id columns
    (FEATURE 3). effective_from is enforced read-side by
    watchlist_engine.active_watchlist_clause().
  * alerts: assignment + escalation columns and an ESCALATED enum value
    (FEATURE 6). The watchlist engine still only ever creates NEW alerts.
  * saved_searches (FEATURE 2) -- criteria only, never result sets.
  * camera_health_history (FEATURE 5) -- append-only status-transition log.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_camera_status = postgresql.ENUM(
    "ONLINE", "OFFLINE", "DEGRADED", name="camerastatus", create_type=False
)


def upgrade() -> None:
    # --- trigram partial-plate search -------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ve_plate_trgm "
        "ON vehicle_events USING gin (plate_number_normalized gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_watchlist_plate_trgm "
        "ON watchlist USING gin (plate_number_normalized gin_trgm_ops)"
    )

    # --- watchlist management columns (FEATURE 3) ------------------------
    op.add_column("watchlist", sa.Column("description", sa.String(), nullable=True))
    op.add_column("watchlist", sa.Column("effective_from", sa.DateTime(), nullable=True))
    op.add_column(
        "watchlist",
        sa.Column("updated_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_watchlist_category", "watchlist", ["offense_category"])

    # --- alert escalation workflow (FEATURE 6) --------------------------
    op.execute("ALTER TYPE alertstatus ADD VALUE IF NOT EXISTS 'ESCALATED' BEFORE 'RESOLVED'")
    op.add_column(
        "alerts",
        sa.Column("assigned_to_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "alerts",
        sa.Column("escalated_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column("alerts", sa.Column("escalated_at", sa.DateTime(), nullable=True))
    op.add_column("alerts", sa.Column("escalation_reason", sa.String(), nullable=True))
    op.add_column(
        "alerts",
        sa.Column("resolved_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column("alerts", sa.Column("resolved_at", sa.DateTime(), nullable=True))
    op.create_index("ix_alerts_assigned_to_user_id", "alerts", ["assigned_to_user_id"])

    # --- saved_searches (FEATURE 2) ------------------------------------
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_saved_searches_id", "saved_searches", ["id"])
    op.create_index("ix_saved_searches_created_by_user_id", "saved_searches", ["created_by_user_id"])
    op.create_index(
        "ix_saved_searches_owner_created", "saved_searches", ["created_by_user_id", "created_at"]
    )

    # --- camera_health_history (FEATURE 5) ----------------------------
    op.create_table(
        "camera_health_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("camera_id", sa.String(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("status", _camera_status, nullable=False),
        sa.Column("previous_status", _camera_status, nullable=True),
        sa.Column("stream_fps", sa.Float(), nullable=True),
        sa.Column("reconnect_count", sa.Integer(), nullable=True),
        sa.Column("last_frame_age_seconds", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="health_push"),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_camera_health_history_id", "camera_health_history", ["id"])
    op.create_index("ix_camera_health_history_camera_id", "camera_health_history", ["camera_id"])
    op.create_index(
        "ix_camera_health_history_cam_time", "camera_health_history", ["camera_id", "detected_at"]
    )


def downgrade() -> None:
    op.drop_table("camera_health_history")
    op.drop_table("saved_searches")

    op.drop_index("ix_alerts_assigned_to_user_id", table_name="alerts")
    op.drop_column("alerts", "resolved_at")
    op.drop_column("alerts", "resolved_by_user_id")
    op.drop_column("alerts", "escalation_reason")
    op.drop_column("alerts", "escalated_at")
    op.drop_column("alerts", "escalated_by_user_id")
    op.drop_column("alerts", "assigned_to_user_id")
    # NOTE: a value added to a PG enum cannot be removed without recreating
    # the type. 'ESCALATED' is left in place on downgrade -- harmless (no row
    # is required to use it) and avoids a fragile enum rebuild.

    op.drop_index("ix_watchlist_category", table_name="watchlist")
    op.drop_column("watchlist", "updated_by_user_id")
    op.drop_column("watchlist", "effective_from")
    op.drop_column("watchlist", "description")

    op.execute("DROP INDEX IF EXISTS ix_watchlist_plate_trgm")
    op.execute("DROP INDEX IF EXISTS ix_ve_plate_trgm")
    # pg_trgm extension is left installed (other things may rely on it).
