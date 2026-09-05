"""
Phase 6 -- database index regression tests.

Locks in the indexes the analytics / search / retention queries depend on
(so a dropped migration or a model change is caught), and that the
GeoAlchemy2 spatial-index duplicate stays removed.

Query-plan *shape* at scale (index-only scans, etc.) is measured in
scripts/db_benchmark.py / README "Database Scalability", not here -- on a
60-row test table the planner picks seq scans regardless, so a plan
assertion would be noise.
"""
from sqlalchemy import text

# Indexes the hot queries rely on. Present in the test DB via
# SQLModel.metadata.create_all (conftest) and in production via
# migrations 0001 / 0002 / 0004.
REQUIRED_VEHICLE_EVENT_INDEXES = {
    "ix_vehicle_events_plate_ts_composite",   # /vehicles/search (WHERE plate ORDER BY ts)
    "ix_vehicle_events_timestamp_btree",      # /vehicles/events/recent + retention scan
    "ix_ve_ts_plate",                         # analytics: top plates / distinct plates in window
    "ix_ve_ts_camera_code",                   # analytics: detections by camera in window
    "ix_ve_vehicle_type",                     # analytics: detections by type (all-time)
}
REQUIRED_ALERT_INDEXES = {
    "ix_alerts_vehicle_event_id",             # retention anti-join + FK reference check
    "ix_alerts_plate_camera_created_composite",  # watchlist cooldown lookup
    "ix_alerts_status_btree",                  # dashboard "active alerts" count
}


def _indexes(db, table):
    return set(
        db.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": table}
        ).scalars().all()
    )


def test_required_vehicle_event_indexes_exist(db_session):
    missing = REQUIRED_VEHICLE_EVENT_INDEXES - _indexes(db_session, "vehicle_events")
    assert not missing, f"missing vehicle_events indexes: {missing}"


def test_required_alert_indexes_exist(db_session):
    missing = REQUIRED_ALERT_INDEXES - _indexes(db_session, "alerts")
    assert not missing, f"missing alerts indexes: {missing}"


def test_watchlist_and_camera_lookup_indexes_exist(db_session):
    assert "ix_watchlist_plate_btree" in _indexes(db_session, "watchlist")
    assert "ix_cameras_code" in _indexes(db_session, "cameras")


def test_exactly_one_gist_index_per_location_column(db_session):
    """GeoAlchemy2 + migration 0001 created two identical GiST indexes on
    each `location`; migration 0004 + spatial_index=False leaves one."""
    for table in ("vehicle_events", "cameras"):
        gist = [
            ix for ix in _indexes(db_session, table)
            if "location" in ix.lower() or ix.endswith("_gist")
        ]
        assert len(gist) == 1, f"{table} has {len(gist)} location/gist indexes: {sorted(gist)}"


def test_raw_plate_number_has_no_index(db_session):
    """`vehicle_events.plate_number` (raw, pre-normalisation) is never
    filtered on -- every lookup uses plate_number_normalized -- so it must
    not carry an index on the hot insert path."""
    idx = _indexes(db_session, "vehicle_events")
    assert "ix_vehicle_events_plate_number" not in idx
