"""
Phase 6 -- retention purge is now batched. Assert the batching does not
change the semantics from Phase 4: same rows deleted, alert-referenced rows
always kept, count returned is the total across batches.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.models.alert import Alert
from app.models.base import PriorityLevel
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.services.retention import purge_old_vehicle_events


def test_batched_purge_deletes_all_matching_rows(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="cam-batch-1")
    old = datetime.utcnow() - timedelta(days=45)
    for i in range(25):
        make_vehicle_event(cam, plate=f"GJ0BATCH{i:02d}", track_id=i, ts=old)
    make_vehicle_event(cam, plate="GJ0RECENT1", track_id=99,
                       ts=datetime.utcnow() - timedelta(days=1))

    # batch_size=10 -> 3 batches (10, 10, 5)
    deleted = purge_old_vehicle_events(db_session, retention_days=30, batch_size=10)
    assert deleted == 25

    remaining = db_session.execute(select(func.count()).select_from(VehicleEvent)).scalar_one()
    assert remaining == 1  # only the recent one


def test_batched_purge_never_deletes_alert_referenced_rows(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="cam-batch-2")
    old = datetime.utcnow() - timedelta(days=400)
    protected = make_vehicle_event(cam, plate="GJ0WANTED1", track_id=1, ts=old)
    for i in range(15):
        make_vehicle_event(cam, plate=f"GJ0PURGE{i:02d}", track_id=10 + i, ts=old)

    wl = Watchlist(plate_number="GJ0WANTED1", plate_number_normalized="GJ0WANTED1",
                   offense_category="STOLEN", priority_level=PriorityLevel.HIGH)
    db_session.add(wl)
    db_session.commit()
    db_session.refresh(wl)
    db_session.add(Alert(
        plate_number="GJ0WANTED1", plate_number_normalized="GJ0WANTED1",
        camera_id=cam.id, vehicle_event_id=protected.id, watchlist_id=wl.id,
    ))
    db_session.commit()

    deleted = purge_old_vehicle_events(db_session, retention_days=30, batch_size=5)
    assert deleted == 15
    assert db_session.get(VehicleEvent, protected.id) is not None


def test_purge_disabled_when_retention_zero(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="cam-batch-3")
    make_vehicle_event(cam, plate="GJ0OLD999", ts=datetime.utcnow() - timedelta(days=999))
    assert purge_old_vehicle_events(db_session, retention_days=0) == 0
    assert db_session.execute(select(func.count()).select_from(VehicleEvent)).scalar_one() == 1
