"""
Phase 17 Step 11 -- GET /api/v1/system/capacity.
"""
from datetime import datetime

from conftest import bearer


def test_capacity_requires_auth(client):
    assert client.get("/api/v1/system/capacity").status_code == 401


def test_capacity_shape_empty_db(client, officer_user):
    _, tok = officer_user
    r = client.get("/api/v1/system/capacity", headers=bearer(tok))
    assert r.status_code == 200, r.text
    b = r.json()
    for k in ("current", "health", "degradation", "scaling", "capacity_model", "note"):
        assert k in b
    assert b["current"]["pipeline_reported"] is False
    assert b["current"]["workers"] is None
    assert b["degradation"]["state"] == "HEALTHY"
    # never claims 80,000 is achieved -- only ever a calculated target
    assert b["scaling"]["target_capacity"] == 80_000
    assert b["scaling"]["required_workers_for_target"] > 0
    assert "NOT" in b["capacity_model"]["measured"]["source"] or "fallback" in b["capacity_model"]["measured"]["source"]


def test_capacity_reflects_pipeline_status(client, db_session, officer_user):
    _, tok = officer_user
    from app.models.pipeline_status import PipelineStatus
    db_session.add(PipelineStatus(
        service_id="default", reported_at=datetime.utcnow(),
        num_workers=1, processed_frames=500, processed_fps=1.1,
        cameras_processing=5, cpu_percent=65.0,
        event_queue_depth=10, event_queue_max_depth=20,
    ))
    db_session.commit()

    b = client.get("/api/v1/system/capacity", headers=bearer(tok)).json()
    assert b["current"]["pipeline_reported"] is True
    assert b["current"]["workers"] == 1
    assert b["current"]["cameras_processing"] == 5
    assert b["health"]["cpu_percent"] == 65.0


def test_capacity_degrades_on_high_cpu(client, db_session, officer_user):
    _, tok = officer_user
    from app.models.pipeline_status import PipelineStatus
    db_session.add(PipelineStatus(
        service_id="default", reported_at=datetime.utcnow(),
        num_workers=1, cpu_percent=95.0,
    ))
    db_session.commit()
    b = client.get("/api/v1/system/capacity", headers=bearer(tok)).json()
    assert b["degradation"]["state"] == "OVERLOADED"
    assert any("CPU" in r for r in b["degradation"]["reasons"])


def test_capacity_reflects_camera_counts(client, db_session, officer_user, make_camera):
    _, tok = officer_user
    from app.models.base import CameraStatus
    c1 = make_camera(code="CAP-ON1")
    c1.status = CameraStatus.ONLINE
    c2 = make_camera(code="CAP-OFF1")
    c2.status = CameraStatus.OFFLINE
    db_session.add(c1)
    db_session.add(c2)
    db_session.commit()

    b = client.get("/api/v1/system/capacity", headers=bearer(tok)).json()
    assert b["current"]["cameras_total"] >= 2
    assert b["current"]["cameras_active"] >= 1


def test_capacity_target_cameras_query_param(client, officer_user):
    _, tok = officer_user
    b = client.get("/api/v1/system/capacity?target_cameras=1000", headers=bearer(tok)).json()
    assert b["scaling"]["target_capacity"] == 1000
