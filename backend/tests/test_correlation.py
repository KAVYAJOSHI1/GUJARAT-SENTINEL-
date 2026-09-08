"""
Phase 14 (2/7) -- Advanced Cross-Camera Correlation + Camera Transition
Intelligence.

Covers: transition-stat recompute + classification, distance-model
fallback, the six correlation sub-scores, CONFIRMED-vs-INFERRED verdict,
impossible-time never CONFIRMED, fuzzy plate, endpoints + RBAC + audit,
and journey-transition classification wiring.
"""
from datetime import datetime, timedelta

from app.models.base import ConfidenceLevel
from app.services.ai.camera_transitions import CameraTransitionService
from app.services.ai.correlation import VehicleCorrelationService
from conftest import bearer

PLATE = "GJ18TC0450"


def _ev(mk, cam, plate, ts, **kw):
    kw.setdefault("vehicle_type", "car")
    kw.setdefault("vehicle_color", "white")
    return mk(cam, plate=plate, ts=ts, **kw)


# --------------------------------------------------------------------------- #
#  camera transition stats
# --------------------------------------------------------------------------- #
def test_recompute_and_classify(db_session, make_camera, make_vehicle_event):
    a = make_camera(code="CAM-A", lat=23.00, lon=72.55)
    b = make_camera(code="CAM-B", lat=23.02, lon=72.57)
    base = datetime.utcnow() - timedelta(days=1)
    # three DIFFERENT vehicles each pass A -> B, ~300 s (so no B -> A loopback)
    for k in range(3):
        t0 = base + timedelta(hours=k)
        p = f"GJ01AB{1000 + k}"
        _ev(make_vehicle_event, a, p, t0, track_id=10 + k)
        _ev(make_vehicle_event, b, p, t0 + timedelta(seconds=300), track_id=10 + k)

    svc = CameraTransitionService(db_session)
    res = svc.recompute()
    assert res["pairs_upserted"] == 1

    band = svc.expected_travel(a.id, b.id)
    assert band["source"] == "historical"
    assert band["sample_count"] == 3
    assert 250 <= band["median_seconds"] <= 350

    assert svc.classify(a.id, b.id, 290)["classification"] == "PLAUSIBLE"
    assert svc.classify(a.id, b.id, 5)["classification"] == "IMPOSSIBLE"
    assert svc.classify(a.id, b.id, 6000)["classification"] == "SLOW"


def test_expected_travel_distance_model_fallback(db_session, make_camera):
    a = make_camera(code="CAM-D1", lat=23.00, lon=72.55)
    b = make_camera(code="CAM-D2", lat=23.05, lon=72.60)   # ~7 km
    band = CameraTransitionService(db_session).expected_travel(a.id, b.id)
    assert band["source"] == "distance-model"
    assert band["typical_min_seconds"] < band["typical_max_seconds"]
    assert band["distance_meters"] > 5000


def test_expected_travel_unknown_without_geometry(db_session, make_camera):
    a = make_camera(code="CAM-U1", lat=None, lon=None)
    b = make_camera(code="CAM-U2", lat=None, lon=None)
    band = CameraTransitionService(db_session).expected_travel(a.id, b.id)
    assert band["source"] == "unknown"
    assert band["typical_min_seconds"] is None


def test_likely_next_cameras(db_session, make_camera, make_vehicle_event):
    a = make_camera(code="CAM-N0", lat=23.00, lon=72.55)
    b = make_camera(code="CAM-N1", lat=23.01, lon=72.56)
    c = make_camera(code="CAM-N2", lat=23.02, lon=72.57)
    base = datetime.utcnow() - timedelta(days=1)
    for k in range(3):
        t0 = base + timedelta(hours=k)
        _ev(make_vehicle_event, a, PLATE, t0, track_id=20 + k)
        _ev(make_vehicle_event, b, PLATE, t0 + timedelta(seconds=200), track_id=20 + k)
    for k in range(2):
        t0 = base + timedelta(hours=10 + k)
        _ev(make_vehicle_event, a, "GJ01AA1111", t0, track_id=40 + k)
        _ev(make_vehicle_event, c, "GJ01AA1111", t0 + timedelta(seconds=200), track_id=40 + k)

    svc = CameraTransitionService(db_session)
    svc.recompute()
    nxt = svc.likely_next_cameras(a.id)
    assert nxt and nxt[0]["camera_code"] == "CAM-N1"       # most frequent hop
    assert nxt[0]["observed_hops"] == 3


# --------------------------------------------------------------------------- #
#  correlation
# --------------------------------------------------------------------------- #
def test_exact_plate_feasible_is_confirmed(db_session, make_camera, make_vehicle_event):
    a = make_camera(code="CAM-C1", lat=23.00, lon=72.55)
    b = make_camera(code="CAM-C2", lat=23.006, lon=72.556)  # ~800 m
    base = datetime.utcnow() - timedelta(hours=2)
    e1 = _ev(make_vehicle_event, a, PLATE, base, track_id=1)
    e2 = _ev(make_vehicle_event, b, PLATE, base + timedelta(seconds=180), track_id=2)

    out = VehicleCorrelationService(db_session).analyze_pair(e1.id, e2.id)
    assert out["scores"]["plate_score"] == 1.0
    assert out["verdict"] == "CONFIRMED"
    assert out["confidence_level"] == ConfidenceLevel.HIGH.value
    assert out["transition_classification"] in ("PLAUSIBLE", "SLOW", "UNKNOWN")


def test_impossible_time_never_confirmed(db_session, make_camera, make_vehicle_event):
    a = make_camera(code="CAM-F1", lat=23.00, lon=72.55)
    b = make_camera(code="CAM-F2", lat=23.60, lon=73.20)   # ~90 km
    base = datetime.utcnow() - timedelta(hours=2)
    e1 = _ev(make_vehicle_event, a, PLATE, base, track_id=1)
    e2 = _ev(make_vehicle_event, b, PLATE, base + timedelta(seconds=5), track_id=2)

    out = VehicleCorrelationService(db_session).analyze_pair(e1.id, e2.id)
    assert out["scores"]["plate_score"] == 1.0        # plate still matches
    assert out["transition_classification"] == "IMPOSSIBLE"
    assert out["verdict"] == "INFERRED"               # NOT confirmed
    assert out["confidence_level"] != ConfidenceLevel.HIGH.value


def test_different_plate_is_inferred(db_session, make_camera, make_vehicle_event):
    a = make_camera(code="CAM-G1", lat=23.00, lon=72.55)
    b = make_camera(code="CAM-G2", lat=23.005, lon=72.555)
    base = datetime.utcnow() - timedelta(hours=2)
    e1 = _ev(make_vehicle_event, a, "GJ18TC0450", base, track_id=1)
    e2 = _ev(make_vehicle_event, b, "GJ99ZZ9999", base + timedelta(seconds=200), track_id=2)

    out = VehicleCorrelationService(db_session).analyze_pair(e1.id, e2.id)
    assert out["scores"]["plate_score"] == 0.0
    assert out["verdict"] == "INFERRED"
    assert out["confidence_level"] != ConfidenceLevel.HIGH.value


def test_fuzzy_plate_one_char(db_session, make_camera, make_vehicle_event):
    a = make_camera(code="CAM-H1", lat=23.00, lon=72.55)
    b = make_camera(code="CAM-H2", lat=23.005, lon=72.555)
    base = datetime.utcnow() - timedelta(hours=2)
    e1 = _ev(make_vehicle_event, a, "GJ18TC0450", base, track_id=1)
    e2 = _ev(make_vehicle_event, b, "GJ18TC0458", base + timedelta(seconds=200), track_id=2)
    out = VehicleCorrelationService(db_session).analyze_pair(e1.id, e2.id)
    assert 0.7 < out["scores"]["plate_score"] < 1.0


def test_analyze_plate_journey(db_session, make_camera, make_vehicle_event):
    cams = [make_camera(code=f"CAM-J{i}", lat=23.0 + i * 0.005, lon=72.55 + i * 0.005)
            for i in range(4)]
    base = datetime.utcnow() - timedelta(hours=1)
    for i, cam in enumerate(cams):
        _ev(make_vehicle_event, cam, PLATE, base + timedelta(minutes=6 * i), track_id=i + 1)
    out = VehicleCorrelationService(db_session).analyze_plate_journey(PLATE)
    assert out["sightings"] == 4
    assert out["hops_analyzed"] == 3
    assert out["confirmed"] + out["inferred"] == 3


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #
def test_analyze_endpoint_and_audit(client, db_session, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    a = make_camera(code="CAM-E1", lat=23.00, lon=72.55)
    b = make_camera(code="CAM-E2", lat=23.005, lon=72.555)
    base = datetime.utcnow() - timedelta(hours=1)
    e1 = _ev(make_vehicle_event, a, PLATE, base, track_id=1)
    e2 = _ev(make_vehicle_event, b, PLATE, base + timedelta(seconds=200), track_id=2)

    r = client.post("/api/v1/ai/correlation/analyze",
                    json={"event_id_a": e1.id, "event_id_b": e2.id}, headers=bearer(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["scores"]) == {
        "plate_score", "appearance_score", "type_score", "color_score",
        "temporal_score", "geographic_score",
    }
    assert body["verdict"] in ("CONFIRMED", "INFERRED")

    from sqlalchemy import select
    from app.models.audit_log import AuditLog
    actions = {a for (a,) in db_session.execute(select(AuditLog.action)).all()}
    assert "AI_CORRELATION_ANALYZE" in actions


def test_analyze_endpoint_by_plate(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cams = [make_camera(code=f"CAM-P{i}", lat=23.0 + i * 0.01, lon=72.55) for i in range(3)]
    base = datetime.utcnow() - timedelta(hours=1)
    for i, cam in enumerate(cams):
        _ev(make_vehicle_event, cam, PLATE, base + timedelta(minutes=7 * i), track_id=i + 1)
    r = client.post("/api/v1/ai/correlation/analyze", json={"plate": PLATE}, headers=bearer(tok))
    assert r.status_code == 200, r.text
    assert r.json()["hops_analyzed"] == 2


def test_analyze_requires_auth(client):
    assert client.post("/api/v1/ai/correlation/analyze", json={"plate": PLATE}).status_code == 401


def test_recompute_rbac(client, operator_user, officer_user):
    _, op_tok = operator_user
    assert client.post("/api/v1/ai/correlation/transitions/recompute",
                       headers=bearer(op_tok)).status_code == 403
    _, off_tok = officer_user
    assert client.post("/api/v1/ai/correlation/transitions/recompute",
                       headers=bearer(off_tok)).status_code == 200


def test_journey_transition_carries_classification(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    a = make_camera(code="CAM-T1", lat=23.00, lon=72.55)
    b = make_camera(code="CAM-T2", lat=23.60, lon=73.20)
    base = datetime.utcnow() - timedelta(hours=1)
    _ev(make_vehicle_event, a, PLATE, base, track_id=1)
    _ev(make_vehicle_event, b, PLATE, base + timedelta(seconds=5), track_id=2)  # 90 km in 5 s
    j = client.get("/api/v1/vehicles/search", params={"plate": PLATE}, headers=bearer(tok)).json()
    tr = j["journey"]["transitions"]
    assert len(tr) == 1
    assert tr[0]["transition_classification"] == "IMPOSSIBLE"
    assert tr[0]["expected_travel_band"]
