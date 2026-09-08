"""operational layer: incidents, cases, evidence links, notifications

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-08

Phase brief "OPERATIONAL PLATFORM ENHANCEMENT" -- FEATURE 1 (Incident
Management), FEATURE 2 (Case Management), FEATURE 4 (evidence linking),
FEATURE 12 (Notification Center).

New tables only -- nothing in the existing CCTV / ANPR / watchlist / alert
pipeline is altered. Every operational row links back to the source rows
(alerts, vehicle_events, cameras, users) by foreign key; no mutable state
is denormalised. Indexes match the list-endpoint filter/sort patterns
(status boards, plate lookups, per-parent child fetches) so none of the
new endpoints fan out into N+1 or unbounded scans.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# All enum types are created explicitly in upgrade() with checkfirst=True and
# create_type=False, so CREATE TABLE never re-emits a CREATE TYPE.
# prioritylevel already exists (migration 0001).
_priority = postgresql.ENUM(
    "LOW", "MEDIUM", "HIGH", "CRITICAL", name="prioritylevel", create_type=False
)
_incident_status = postgresql.ENUM(
    "NEW", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "CLOSED",
    name="incidentstatus", create_type=False,
)
_case_status = postgresql.ENUM(
    "OPEN", "INVESTIGATING", "ON_HOLD", "RESOLVED", "CLOSED",
    name="casestatus", create_type=False,
)
_notif_severity = postgresql.ENUM(
    "INFO", "WARNING", "CRITICAL", name="notificationseverity", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _incident_status.create(bind, checkfirst=True)
    _case_status.create(bind, checkfirst=True)
    _notif_severity.create(bind, checkfirst=True)

    # --- incidents ---
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("incident_number", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=False, server_default="WATCHLIST_HIT"),
        sa.Column("priority_level", _priority, nullable=False, server_default="MEDIUM"),
        sa.Column("status", _incident_status, nullable=False, server_default="NEW"),
        sa.Column("alert_id", sa.String(), sa.ForeignKey("alerts.id"), nullable=True),
        sa.Column("vehicle_event_id", sa.String(), sa.ForeignKey("vehicle_events.id"), nullable=True),
        sa.Column("camera_id", sa.String(), sa.ForeignKey("cameras.id"), nullable=True),
        sa.Column("plate_number_normalized", sa.String(), nullable=True),
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_to_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # Single-column index names follow SQLModel's field-level `index=True`
    # convention (ix_<table>_<column>) so a create_all() dev DB and a
    # migrated DB carry the same names.
    op.create_index("ix_incidents_incident_number", "incidents", ["incident_number"], unique=True)
    op.create_index("ix_incidents_id", "incidents", ["id"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_priority_level", "incidents", ["priority_level"])
    op.create_index("ix_incidents_category", "incidents", ["category"])
    op.create_index("ix_incidents_alert_id", "incidents", ["alert_id"])
    op.create_index("ix_incidents_vehicle_event_id", "incidents", ["vehicle_event_id"])
    op.create_index("ix_incidents_camera_id", "incidents", ["camera_id"])
    op.create_index("ix_incidents_assigned_to_user_id", "incidents", ["assigned_to_user_id"])
    op.create_index("ix_incidents_plate_number_normalized", "incidents", ["plate_number_normalized"])
    op.create_index("ix_incidents_status_created", "incidents", ["status", "created_at"])

    # --- incident_notes ---
    op.create_table(
        "incident_notes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("incident_id", sa.String(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("author_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_incident_notes_id", "incident_notes", ["id"])
    op.create_index("ix_incident_notes_incident_id", "incident_notes", ["incident_id"])
    op.create_index(
        "ix_incident_notes_incident_created", "incident_notes", ["incident_id", "created_at"]
    )

    # --- incident_evidence ---
    op.create_table(
        "incident_evidence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("incident_id", sa.String(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("vehicle_event_id", sa.String(), sa.ForeignKey("vehicle_events.id"), nullable=False),
        sa.Column("added_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_incident_evidence_id", "incident_evidence", ["id"])
    op.create_index("ix_incident_evidence_incident_id", "incident_evidence", ["incident_id"])
    op.create_index(
        "ix_incident_evidence_vehicle_event_id", "incident_evidence", ["vehicle_event_id"]
    )
    op.create_index(
        "ux_incident_evidence_pair",
        "incident_evidence",
        ["incident_id", "vehicle_event_id"],
        unique=True,
    )

    # --- cases ---
    op.create_table(
        "cases",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_number", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("priority_level", _priority, nullable=False, server_default="MEDIUM"),
        sa.Column("status", _case_status, nullable=False, server_default="OPEN"),
        sa.Column("primary_plate_normalized", sa.String(), nullable=True),
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_to_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_cases_case_number", "cases", ["case_number"], unique=True)
    op.create_index("ix_cases_id", "cases", ["id"])
    op.create_index("ix_cases_status", "cases", ["status"])
    op.create_index("ix_cases_priority_level", "cases", ["priority_level"])
    op.create_index("ix_cases_assigned_to_user_id", "cases", ["assigned_to_user_id"])
    op.create_index("ix_cases_primary_plate_normalized", "cases", ["primary_plate_normalized"])
    op.create_index("ix_cases_status_created", "cases", ["status", "created_at"])

    # --- case_notes ---
    op.create_table(
        "case_notes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("author_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_case_notes_id", "case_notes", ["id"])
    op.create_index("ix_case_notes_case_id", "case_notes", ["case_id"])
    op.create_index("ix_case_notes_case_created", "case_notes", ["case_id", "created_at"])

    # --- case_incidents ---
    op.create_table(
        "case_incidents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("incident_id", sa.String(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("added_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_case_incidents_id", "case_incidents", ["id"])
    op.create_index("ix_case_incidents_case_id", "case_incidents", ["case_id"])
    op.create_index("ix_case_incidents_incident_id", "case_incidents", ["incident_id"])
    op.create_index(
        "ux_case_incidents_pair", "case_incidents", ["case_id", "incident_id"], unique=True
    )

    # --- case_evidence ---
    op.create_table(
        "case_evidence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("vehicle_event_id", sa.String(), sa.ForeignKey("vehicle_events.id"), nullable=False),
        sa.Column("added_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_case_evidence_id", "case_evidence", ["id"])
    op.create_index("ix_case_evidence_case_id", "case_evidence", ["case_id"])
    op.create_index("ix_case_evidence_vehicle_event_id", "case_evidence", ["vehicle_event_id"])
    op.create_index(
        "ux_case_evidence_pair", "case_evidence", ["case_id", "vehicle_event_id"], unique=True
    )

    # --- notifications ---
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("severity", _notif_severity, nullable=False, server_default="INFO"),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=True),
        sa.Column("resource", sa.String(), nullable=True),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("target_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_notifications_id", "notifications", ["id"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_target_user_id", "notifications", ["target_user_id"])
    op.create_index("ix_notifications_read", "notifications", ["read"])
    op.create_index("ix_notifications_read_created", "notifications", ["read", "created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("case_evidence")
    op.drop_table("case_incidents")
    op.drop_table("case_notes")
    op.drop_table("cases")
    op.drop_table("incident_evidence")
    op.drop_table("incident_notes")
    op.drop_table("incidents")
    bind = op.get_bind()
    _notif_severity.drop(bind, checkfirst=True)
    _case_status.drop(bind, checkfirst=True)
    _incident_status.drop(bind, checkfirst=True)
