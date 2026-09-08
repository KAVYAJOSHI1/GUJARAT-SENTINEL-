"""
Phase 15G -- /system/metrics/summary observability snapshot.
"""
from datetime import datetime, timedelta

from conftest import bearer


def test_summary_shape_empty_db(client, officer_user):
    _, tok = officer_user
    r = client.get("/api/v1/system/metrics/summary", headers=bearer(tok))
    assert r.status_code == 200, r.text
    b = r.json()
    for k in ("pipeline", "anpr", "detections", "alerts", "anomalies",
              "incidents", "cases", "cameras", "note"):
        assert k in b
    assert b["pipeline"]["reported"] is False
    assert b["anpr"]["window_total"] == 0
    assert "Prometheus" in b["note"]


def test_summary_reflects_anpr_and_detections(client, db_session, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-M")
    now = datetime.utcnow()
    for i in range(6):
        ev = make_vehicle_event(cam, plate=("GJ01AB000%d" % i if i < 4 else "UNKNOWN"),
                                track_id=i + 1, ts=now - timedelta(minutes=i))
        if i >= 4:
            ev.anpr_status = "UNKNOWN"
            ev.anpr_failure_reason = "BLUR"
        db_session.add(ev)
    db_session.commit()

    b = client.get("/api/v1/system/metrics/summary", headers=bearer(tok)).json()
    assert b["anpr"]["window_total"] == 6
    assert b["anpr"]["readable"] == 4
    assert b["anpr"]["unknown"] == 2
    assert b["anpr"]["failure_reasons"]["BLUR"] == 2
    assert b["detections"]["window_total"] == 6
    assert b["cameras"]["total"] >= 1


def test_summary_includes_pipeline_snapshot(client, db_session, officer_user):
    _, tok = officer_user
    from app.models.pipeline_status import PipelineStatus
    db_session.add(PipelineStatus(
        service_id="default", reported_at=datetime.utcnow(),
        num_workers=2, processed_frames=1000, processed_fps=9.5,
        vehicles_detected=42, events_generated=40, events_delivered=40,
        events_dropped=0, event_queue_depth=1, ocr_p50_ms=180.0,
    ))
    db_session.commit()
    b = client.get("/api/v1/system/metrics/summary", headers=bearer(tok)).json()
    assert b["pipeline"]["reported"] is True
    assert b["pipeline"]["processed_fps"] == 9.5
    assert b["pipeline"]["ocr_p50_ms"] == 180.0
    assert b["pipeline"]["stale"] is False


def test_summary_requires_auth(client):
    assert client.get("/api/v1/system/metrics/summary").status_code == 401
