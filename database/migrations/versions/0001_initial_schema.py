"""initial SENTINEL schema — cameras, vehicle_events, watchlist, alerts, users, audit_logs

Revision ID: 0001
Revises:
Create Date: 2026-09-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False, unique=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("ADMIN", "OFFICER", "OPERATOR", name="userrole"),
            nullable=False,
            server_default="OPERATOR",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_role_btree", "users", ["role"])

    # --- cameras ---
    op.create_table(
        "cameras",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("rtsp_url", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ONLINE", "OFFLINE", "DEGRADED", name="camerastatus"),
            nullable=False,
            server_default="OFFLINE",
        ),
        sa.Column("location_desc", sa.String(), nullable=True),
        sa.Column("location", geoalchemy2.Geometry(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_cameras_name", "cameras", ["name"])
    op.create_index("ix_cameras_status_btree", "cameras", ["status"])
    op.create_index(
        "ix_cameras_location_gist", "cameras", ["location"], postgresql_using="gist"
    )

    # --- watchlist ---
    op.create_table(
        "watchlist",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("plate_number", sa.String(), nullable=False),
        sa.Column("plate_number_normalized", sa.String(), nullable=False, unique=True),
        sa.Column("offense_category", sa.String(), nullable=False),
        sa.Column(
            "priority_level",
            sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="prioritylevel"),
            nullable=False,
            server_default="MEDIUM",
        ),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("added_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_watchlist_plate_btree", "watchlist", ["plate_number_normalized"], unique=True
    )
    op.create_index("ix_watchlist_priority_btree", "watchlist", ["priority_level"])
    op.create_index("ix_watchlist_active", "watchlist", ["active"])

    # --- vehicle_events ---
    op.create_table(
        "vehicle_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("plate_number", sa.String(), nullable=False),
        sa.Column("plate_number_normalized", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("vehicle_type", sa.String(), nullable=True),
        sa.Column("vehicle_color", sa.String(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("snapshot_url", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("location", geoalchemy2.Geometry(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_vehicle_events_plate_btree", "vehicle_events", ["plate_number_normalized"])
    op.create_index("ix_vehicle_events_timestamp_btree", "vehicle_events", ["timestamp"])
    op.create_index("ix_vehicle_events_camera_id", "vehicle_events", ["camera_id"])
    op.create_index(
        "ix_vehicle_events_plate_ts_composite",
        "vehicle_events",
        ["plate_number_normalized", "timestamp"],
    )
    op.create_index(
        "ix_vehicle_events_location_gist", "vehicle_events", ["location"], postgresql_using="gist"
    )

    # --- alerts ---
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("plate_number", sa.String(), nullable=False),
        sa.Column("plate_number_normalized", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("vehicle_event_id", sa.String(), sa.ForeignKey("vehicle_events.id"), nullable=False),
        sa.Column("watchlist_id", sa.String(), sa.ForeignKey("watchlist.id"), nullable=False),
        sa.Column(
            "priority_level",
            sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="prioritylevel"),
            nullable=False,
            server_default="MEDIUM",
        ),
        sa.Column(
            "status",
            sa.Enum("NEW", "ACKNOWLEDGED", "RESOLVED", name="alertstatus"),
            nullable=False,
            server_default="NEW",
        ),
        sa.Column("acknowledged_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("snapshot_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_alerts_plate_camera_created_composite",
        "alerts",
        ["plate_number_normalized", "camera_id", "created_at"],
    )
    op.create_index("ix_alerts_status_btree", "alerts", ["status"])

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=True),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_logs_action_btree", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("alerts")
    op.drop_table("vehicle_events")
    op.drop_table("watchlist")
    op.drop_table("cameras")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS alertstatus")
    op.execute("DROP TYPE IF EXISTS prioritylevel")
    op.execute("DROP TYPE IF EXISTS camerastatus")
    op.execute("DROP TYPE IF EXISTS userrole")
