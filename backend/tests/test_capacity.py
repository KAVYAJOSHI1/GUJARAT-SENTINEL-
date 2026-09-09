"""
Phase 17 Step 11 -- GET /api/v1/system/capacity.
"""
from datetime import datetime
from unittest import mock

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
    assert isinstance(b["capacity_model"]["measured"]["source"], str) and b["capacity_model"]["measured"]["source"]


def test_capacity_falls_back_honestly_when_no_benchmark_file_committed(client, officer_user):
    """Never present the no-benchmark-file fallback as if it were measured."""
    _, tok = officer_user
    with mock.patch("app.services.capacity._load_benchmark_summary", return_value=None):
        b = client.get("/api/v1/system/capacity", headers=bearer(tok)).json()
    source = b["capacity_model"]["measured"]["source"]
    assert "NOT measured" in source or "fallback" in source.lower()


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
    # cpu_percent is psutil's raw MULTI-CORE cumulative percent (can exceed
    # 100 -- see capacity.py's normalization comment), so push a value that
    # is >90% of this HOST's total capacity after normalization, not a bare
    # "95" (which would be well under 90% of an 8-core host and wrongly
    # stay HEALTHY -- exactly the calibration bug this normalization fixes).
    import multiprocessing
    _, tok = officer_user
    from app.models.pipeline_status import PipelineStatus
    full_capacity_pct = 100.0 * (multiprocessing.cpu_count() or 1)
    db_session.add(PipelineStatus(
        service_id="default", reported_at=datetime.utcnow(),
        num_workers=1, cpu_percent=0.95 * full_capacity_pct,
    ))
    db_session.commit()
    b = client.get("/api/v1/system/capacity", headers=bearer(tok)).json()
    assert b["degradation"]["state"] == "OVERLOADED"
    assert any("CPU" in r for r in b["degradation"]["reasons"])


def test_capacity_normalizes_multicore_cpu_not_falsely_overloaded(client, db_session, officer_user):
    """A single fully-busy core on an idle multi-core host (e.g. ~100% raw
    on an 8-core machine = 12.5% of total capacity) must NOT be reported as
    OVERLOADED -- this is the exact bug an early Phase 17 benchmark run
    surfaced (see docs/PHASE17_BENCHMARK.md)."""
    import multiprocessing
    if (multiprocessing.cpu_count() or 1) < 2:
        return  # normalization is a no-op on a single-core host; nothing to assert
    _, tok = officer_user
    from app.models.pipeline_status import PipelineStatus
    db_session.add(PipelineStatus(
        service_id="default", reported_at=datetime.utcnow(),
        num_workers=1, cpu_percent=100.0,
    ))
    db_session.commit()
    b = client.get("/api/v1/system/capacity", headers=bearer(tok)).json()
    assert b["degradation"]["state"] == "HEALTHY"


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
