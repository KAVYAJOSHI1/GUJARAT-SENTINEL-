"""db scalability: analytics covering indexes + drop duplicate spatial index

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-05

Phase 6 -- indexes chosen from an actual EXPLAIN/timing benchmark of the
queries /analytics/overview and the retention sweep issue against a 1M-row
synthetic vehicle_events table (see scripts/db_benchmark.py, README.md
"Database Scalability"):

  * ix_ve_ts_plate (timestamp, plate_number_normalized)
      -> "top plates in window" 105ms -> 26ms, "distinct plates in window"
         180ms -> 107ms (index-only scan, no heap fetch for the plate value)
  * ix_ve_ts_camera_code (timestamp, camera_code)
      -> "detections by camera in window" 101ms -> ~20ms once analytics.py
         aggregates-then-joins (index-only scan)
  * ix_ve_vehicle_type (vehicle_type)
      -> all-time "detections by type" GROUP BY 70ms -> 42ms
         (parallel index-only scan instead of a heap seq scan)
  * ix_alerts_vehicle_event_id (alerts.vehicle_event_id)
      -> the retention anti-join + the FK reference check; the model always
         declared this index but migration 0001 never created it.

Also drops the DUPLICATE GiST spatial index on the two `location` columns:
GeoAlchemy2 auto-creates `idx_<table>_location` on CREATE TABLE, and
migration 0001 additionally created `ix_<table>_location_gist` -- two
identical GiST indexes, doubling spatial-index maintenance on every
vehicle_events insert for an index nothing currently queries. One is kept
(roadmap: proximity search); the redundant auto-created one is removed.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_ve_ts_plate",
        "vehicle_events",
        ["timestamp", "plate_number_normalized"],
    )
    op.create_index(
        "ix_ve_ts_camera_code",
        "vehicle_events",
        ["timestamp", "camera_code"],
    )
    op.create_index("ix_ve_vehicle_type", "vehicle_events", ["vehicle_type"])
    op.create_index("ix_alerts_vehicle_event_id", "alerts", ["vehicle_event_id"])

    # Drop the redundant GeoAlchemy2 auto-created spatial index (keep the
    # explicitly-named ix_*_location_gist from migration 0001).
    op.execute("DROP INDEX IF EXISTS idx_vehicle_events_location")
    op.execute("DROP INDEX IF EXISTS idx_cameras_location")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cameras_location "
        "ON cameras USING gist (location)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicle_events_location "
        "ON vehicle_events USING gist (location)"
    )
    op.drop_index("ix_alerts_vehicle_event_id", table_name="alerts")
    op.drop_index("ix_ve_vehicle_type", table_name="vehicle_events")
    op.drop_index("ix_ve_ts_camera_code", table_name="vehicle_events")
    op.drop_index("ix_ve_ts_plate", table_name="vehicle_events")
