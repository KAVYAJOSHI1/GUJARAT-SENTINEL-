"""phase 12: AI intelligence layer -- anomaly events + alert source

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-08

Phase 12 "AI intelligence layer" -- additive only. The Copilot, NL search
and AI summaries are pure read features and need NO schema change (they run
on the existing vehicle_events / alerts / incidents / cases / evidence).

The only schema change is for the ONE anomaly detector (stopped / loitering
vehicle), so its output can flow through the EXISTING alert workflow:

  * anomaly_events (new table) -- one row per stopped-vehicle detection,
    every figure derived from stored ByteTrack vehicle_events.
  * alerts.source (new enum col, default WATCHLIST) -- the watchlist engine
    still only ever writes WATCHLIST; BehaviorAnalyticsService writes
    ANOMALY.
  * alerts.watchlist_id -> nullable (an ANOMALY alert has no watchlist
    entry). The watchlist -> alert path is untouched and still always sets
    it.
  * alerts.anomaly_event_id (new nullable FK).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_alert_source = postgresql.ENUM(
    "WATCHLIST", "ANOMALY", "MANUAL", name="alertsource", create_type=False
)
_anomaly_status = postgresql.ENUM(
    "NEW", "REVIEWED", "DISMISSED", name="anomalystatus", create_type=False
)
_anomaly_kind = postgresql.ENUM(
    "STOPPED_VEHICLE", name="anomalykind", create_type=False
)
_confidence_level = postgresql.ENUM(
    "HIGH", "MEDIUM", "LOW", "INSUFFICIENT", name="confidencelevel", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    _alert_source.create(bind, checkfirst=True)
    _anomaly_status.create(bind, checkfirst=True)
    _anomaly_kind.create(bind, checkfirst=True)
    _confidence_level.create(bind, checkfirst=True)

    # --- anomaly_events ---
    op.create_table(
        "anomaly_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", _anomaly_kind, nullable=False, server_default="STOPPED_VEHICLE"),
        sa.Column("camera_id", sa.String(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("camera_code", sa.String(), nullable=True),
        sa.Column("plate_number_normalized", sa.String(), nullable=True),
        sa.Column("track_id", sa.Integer(), nullable=True),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("detection_count", sa.Integer(), nullable=False),
        sa.Column("displacement_meters", sa.Float(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("confidence_level", _confidence_level, nullable=False, server_default="LOW"),
        sa.Column("reasoning", sa.String(), nullable=True),
        sa.Column("evidence_event_id", sa.String(), sa.ForeignKey("vehicle_events.id"), nullable=True),
        sa.Column("alert_id", sa.String(), sa.ForeignKey("alerts.id"), nullable=True),
        sa.Column("status", _anomaly_status, nullable=False, server_default="NEW"),
        sa.Column("reviewed_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_anomaly_events_id", "anomaly_events", ["id"])
    op.create_index("ix_anomaly_events_kind", "anomaly_events", ["kind"])
    op.create_index("ix_anomaly_events_camera_id", "anomaly_events", ["camera_id"])
    op.create_index("ix_anomaly_events_camera_code", "anomaly_events", ["camera_code"])
    op.create_index("ix_anomaly_events_plate_number_normalized", "anomaly_events", ["plate_number_normalized"])
    op.create_index("ix_anomaly_events_alert_id", "anomaly_events", ["alert_id"])
    op.create_index("ix_anomaly_events_status", "anomaly_events", ["status"])
    op.create_index("ix_anomaly_events_status_created", "anomaly_events", ["status", "created_at"])
    op.create_index(
        "ux_anomaly_camera_track_start",
        "anomaly_events",
        ["camera_id", "track_id", "first_seen"],
        unique=True,
    )

    # --- alerts: source + anomaly link + nullable watchlist_id ---
    op.add_column(
        "alerts",
        sa.Column("source", _alert_source, nullable=False, server_default="WATCHLIST"),
    )
    op.add_column(
        "alerts",
        sa.Column("anomaly_event_id", sa.String(), sa.ForeignKey("anomaly_events.id"), nullable=True),
    )
    op.create_index("ix_alerts_source", "alerts", ["source"])
    op.create_index("ix_alerts_anomaly_event_id", "alerts", ["anomaly_event_id"])
    op.alter_column("alerts", "watchlist_id", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.alter_column("alerts", "watchlist_id", existing_type=sa.String(), nullable=False)
    op.drop_index("ix_alerts_anomaly_event_id", table_name="alerts")
    op.drop_index("ix_alerts_source", table_name="alerts")
    op.drop_column("alerts", "anomaly_event_id")
    op.drop_column("alerts", "source")

    op.drop_table("anomaly_events")

    bind = op.get_bind()
    _confidence_level.drop(bind, checkfirst=True)
    _anomaly_kind.drop(bind, checkfirst=True)
    _anomaly_status.drop(bind, checkfirst=True)
    _alert_source.drop(bind, checkfirst=True)
