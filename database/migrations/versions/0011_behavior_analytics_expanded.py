"""phase 14 (4/7): expanded behaviour analytics -- wrong-way + restricted-zone

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-08

Phase 14 "Advanced Video Intelligence", commit 4 -- two additional
behaviour detectors that reuse the EXISTING anomaly_events -> alerts ->
notifications -> incidents workflow. Additive only.

  * anomalykind enum gains WRONG_WAY, RESTRICTED_ZONE.
  * anomaly_events gains zone_name / direction_deg / expected_direction_deg
    (NULL for STOPPED_VEHICLE).
  * the dedup unique index gains `kind` so one track can be both a
    STOPPED_VEHICLE and a WRONG_WAY without colliding.
  * cameras gains permitted_direction_deg (wrong-way reference bearing) and
    restricted_zones (JSON polygons). Both NULL by default -> the new
    detectors are inert until a camera is configured.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. enum values (PG 12+ allows ADD VALUE inside a tx as long as the new
    #    value is not used in the same tx -- it isn't here).
    op.execute("ALTER TYPE anomalykind ADD VALUE IF NOT EXISTS 'WRONG_WAY'")
    op.execute("ALTER TYPE anomalykind ADD VALUE IF NOT EXISTS 'RESTRICTED_ZONE'")

    # 2. anomaly_events extra columns
    op.add_column("anomaly_events", sa.Column("zone_name", sa.String(), nullable=True))
    op.add_column("anomaly_events", sa.Column("direction_deg", sa.Float(), nullable=True))
    op.add_column("anomaly_events", sa.Column("expected_direction_deg", sa.Float(), nullable=True))

    # 3. dedup index now keyed on kind too
    op.drop_index("ux_anomaly_camera_track_start", table_name="anomaly_events")
    op.create_index(
        "ux_anomaly_camera_track_start_kind",
        "anomaly_events",
        ["camera_id", "track_id", "first_seen", "kind"],
        unique=True,
    )

    # 4. cameras behaviour config
    op.add_column("cameras", sa.Column("permitted_direction_deg", sa.Float(), nullable=True))
    op.add_column("cameras", sa.Column("restricted_zones", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "restricted_zones")
    op.drop_column("cameras", "permitted_direction_deg")

    op.drop_index("ux_anomaly_camera_track_start_kind", table_name="anomaly_events")
    op.create_index(
        "ux_anomaly_camera_track_start",
        "anomaly_events",
        ["camera_id", "track_id", "first_seen"],
        unique=True,
    )
    op.drop_column("anomaly_events", "expected_direction_deg")
    op.drop_column("anomaly_events", "direction_deg")
    op.drop_column("anomaly_events", "zone_name")
    # enum values WRONG_WAY / RESTRICTED_ZONE are left in place -- PostgreSQL
    # cannot drop an enum value without rebuilding the type; they are inert
    # once the rows / detectors are gone.
