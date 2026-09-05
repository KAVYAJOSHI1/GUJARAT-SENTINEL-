"""
Real HealthRegistry -> cameras.status wiring (SENTINEL_System_Audit_Report.md
§11/§15 — "dashboard camera status not wired to live health... the
health-push endpoint it targets doesn't exist in the real API").
"""
from datetime import datetime, timedelta

from app.config import settings
from app.core.security import create_access_token, hash_password
from app.database import SessionLocal
from app.models.base import CameraStatus, UserRole
from app.models.camera import Camera
from app.models.user import User


def _push(client, entries):
    return client.post(
        "/api/v1/cameras/health",
        json={"streams": entries},
        headers={"X-Ingest-Key": settings.INGEST_API_KEY},
    )


def test_online_health_update_reflected_in_status(client, make_camera):
    camera = make_camera(code="cam-health-01")
    resp = _push(client, [{"camera_id": camera.code, "status": "ONLINE", "fps": 24.5}])
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1

    got = client_get_camera(client, camera.id)
    assert got["status"] == "ONLINE"
    assert got["fps"] == 24.5


def test_offline_health_update_reflected_in_status(client, make_camera):
    camera = make_camera(code="cam-health-02", status=CameraStatus.ONLINE)
    resp = _push(client, [{"camera_id": camera.code, "status": "OFFLINE"}])
    assert resp.status_code == 200

    got = client_get_camera(client, camera.id)
    assert got["status"] == "OFFLINE"


def test_stale_health_forces_offline_even_if_last_status_was_online(client, make_camera, db_session):
    camera = make_camera(code="cam-health-03")
    _push(client, [{"camera_id": camera.code, "status": "ONLINE", "fps": 30.0}])

    # Simulate the ingestion worker having gone silent a while ago: back-date
    # health_updated_at well past the staleness window (the push endpoint
    # always stamps "now", so this is the only way to simulate a stalled
    # worker without actually sleeping in the test). Done through the SAME
    # session `client` reads through (not a second SessionLocal()) --
    # SQLAlchemy's identity map does not auto-refresh an already-loaded
    # object from a commit made on a different session/connection.
    cam = db_session.get(Camera, camera.id)
    cam.health_updated_at = datetime.utcnow() - timedelta(minutes=5)
    db_session.add(cam)
    db_session.commit()

    got = client_get_camera(client, camera.id)
    assert got["status"] == "OFFLINE"


def test_reconnect_to_online_transition(client, make_camera):
    camera = make_camera(code="cam-health-04")
    _push(client, [{"camera_id": camera.code, "status": "RECONNECTING"}])
    assert client_get_camera(client, camera.id)["status"] == "DEGRADED"

    _push(client, [{"camera_id": camera.code, "status": "ONLINE", "fps": 25.0}])
    assert client_get_camera(client, camera.id)["status"] == "ONLINE"


def test_camera_isolation_one_push_does_not_affect_another(client, make_camera):
    cam_a = make_camera(code="cam-health-05a")
    cam_b = make_camera(code="cam-health-05b")

    resp = _push(client, [{"camera_id": cam_a.code, "status": "ONLINE", "fps": 20.0}])
    assert resp.json()["updated"] == 1

    a = client_get_camera(client, cam_a.id)
    b = client_get_camera(client, cam_b.id)
    assert a["status"] == "ONLINE"
    assert b["status"] == "OFFLINE"  # untouched default, never overwritten by cam_a's push
    assert b["fps"] is None


def test_unknown_camera_code_is_skipped_not_fatal(client, make_camera):
    known = make_camera(code="cam-health-06")
    resp = _push(
        client,
        [
            {"camera_id": "cam-does-not-exist", "status": "ONLINE"},
            {"camera_id": known.code, "status": "ONLINE", "fps": 15.0},
        ],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == 1
    assert "cam-does-not-exist" in body["skipped"]
    assert client_get_camera(client, known.id)["status"] == "ONLINE"


def client_get_camera(client, camera_id):
    # GET /cameras/{id} requires a normal user JWT (health push instead uses
    # ingest-key auth -- deliberately different, see cameras.py), so read
    # results back through a throwaway operator user created on first use.
    from sqlalchemy import select

    with SessionLocal() as s:
        user = s.execute(select(User).where(User.username == "_camera_health_reader")).scalar_one_or_none()
        if user is None:
            user = User(
                username="_camera_health_reader",
                email="_camera_health_reader@example.test",
                hashed_password=hash_password("Password123!"),
                role=UserRole.OPERATOR,
            )
            s.add(user)
            s.commit()
            s.refresh(user)
        token = create_access_token(subject=user.id, role=user.role.value)

    resp = client.get(f"/api/v1/cameras/{camera_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    return resp.json()
