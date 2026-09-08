"""
Phase 14 (1/7) -- Vehicle Visual Re-ID.

Covers: embedding generation (deterministic, unit-norm), similarity
ranking, band thresholding, no-match handling, compare, RBAC, audit, and
the "visual similarity is not identity" guarantee.
"""
import math
from datetime import datetime, timedelta

from app.models.base import ConfidenceLevel
from app.services.ai.reid import (
    AttributeEmbeddingBackend,
    VehicleReIDService,
    cosine_similarity,
    similarity_band,
)
from conftest import bearer


def _norm(v):
    return math.sqrt(sum(x * x for x in v))


# --------------------------------------------------------------------------- #
#  embedding backend (pure unit tests -- no DB)
# --------------------------------------------------------------------------- #
def test_embedding_deterministic_and_unit_norm():
    be = AttributeEmbeddingBackend()
    f = {"vehicle_type": "car", "vehicle_color": "white",
         "plate_number_normalized": "GJ01AB1234", "confidence_score": 0.9}
    a = be.extract(f)
    b = be.extract(dict(f))
    assert a == b                              # deterministic
    assert len(a) == be.dim
    assert abs(_norm(a) - 1.0) < 1e-6          # L2-normalised


def test_same_plate_embeds_identically():
    be = AttributeEmbeddingBackend()
    a = be.extract({"vehicle_type": "car", "vehicle_color": "white",
                    "plate_number_normalized": "GJ18TC0450", "confidence_score": 0.9})
    b = be.extract({"vehicle_type": "car", "vehicle_color": "white",
                    "plate_number_normalized": "GJ18TC0450", "confidence_score": 0.7})
    assert cosine_similarity(a, b) > 0.999


def test_attribute_similarity_ordering():
    be = AttributeEmbeddingBackend()
    q = be.extract({"vehicle_type": "car", "vehicle_color": "white",
                    "plate_number_normalized": "UNKNOWN", "track_id": 1})
    same = be.extract({"vehicle_type": "car", "vehicle_color": "white",
                       "plate_number_normalized": "UNKNOWN", "track_id": 2})
    diff_color = be.extract({"vehicle_type": "car", "vehicle_color": "black",
                             "plate_number_normalized": "UNKNOWN", "track_id": 3})
    diff_type = be.extract({"vehicle_type": "truck", "vehicle_color": "white",
                            "plate_number_normalized": "UNKNOWN", "track_id": 4})
    s_same = cosine_similarity(q, same)
    s_color = cosine_similarity(q, diff_color)
    s_type = cosine_similarity(q, diff_type)
    assert s_same > s_color
    assert s_same > s_type


def test_similarity_band_capped_and_monotonic():
    # visual similarity NEVER yields HIGH confidence
    for score in (0.5, 0.7, 0.85, 0.95, 1.0):
        band, conf = similarity_band(score)
        assert conf != ConfidenceLevel.HIGH
    assert similarity_band(0.99)[0] == "STRONG"
    assert similarity_band(0.85)[0] == "MODERATE"
    assert similarity_band(0.70)[0] == "WEAK"
    assert similarity_band(0.30)[0] == "NONE"


# --------------------------------------------------------------------------- #
#  service (DB)
# --------------------------------------------------------------------------- #
def test_index_event_is_idempotent(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-A")
    ev = make_vehicle_event(cam, plate="GJ01AB0001", vehicle_type="car", vehicle_color="white")
    svc = VehicleReIDService(db_session)
    r1 = svc.index_event(ev)
    r2 = svc.index_event(ev)
    assert r1.id == r2.id
    assert r1.dim == len(r1.embedding)


def test_find_similar_ranks_same_plate_first(db_session, make_camera, make_vehicle_event):
    base = datetime.utcnow() - timedelta(hours=1)
    c1 = make_camera(code="CAM-1")
    c2 = make_camera(code="CAM-2")
    c3 = make_camera(code="CAM-3")
    q = make_vehicle_event(c1, plate="GJ18TC0450", track_id=1, ts=base,
                           vehicle_type="car", vehicle_color="white")
    same = make_vehicle_event(c2, plate="GJ18TC0450", track_id=2, ts=base + timedelta(minutes=5),
                              vehicle_type="car", vehicle_color="white")
    other = make_vehicle_event(c3, plate="GJ99ZZ9999", track_id=3, ts=base + timedelta(minutes=6),
                               vehicle_type="truck", vehicle_color="black")
    svc = VehicleReIDService(db_session)
    for e in (q, same, other):
        svc.index_event(e)

    res = svc.find_similar(event_id=q.id, limit=10)
    assert res["returned"] >= 1
    top = res["candidates"][0]
    assert top["event_id"] == same.id
    assert top["same_plate"] is True
    assert top["verdict"] == "PLATE MATCH"
    # the dissimilar truck should score below the same-plate car
    by_id = {c["event_id"]: c for c in res["candidates"]}
    if other.id in by_id:
        assert by_id[other.id]["similarity"] < top["similarity"]


def test_find_similar_no_candidates(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-SOLO")
    ev = make_vehicle_event(cam, plate="GJ01AB0002", vehicle_type="car", vehicle_color="white")
    res = VehicleReIDService(db_session).find_similar(event_id=ev.id, limit=10)
    assert res["returned"] == 0
    assert res["candidates"] == []
    assert "not identity" in res["disclaimer"]


def test_exclude_same_plate(db_session, make_camera, make_vehicle_event):
    base = datetime.utcnow() - timedelta(hours=1)
    c1 = make_camera(code="CAM-X1")
    c2 = make_camera(code="CAM-X2")
    q = make_vehicle_event(c1, plate="GJ18TC0450", track_id=1, ts=base,
                           vehicle_type="car", vehicle_color="white")
    same = make_vehicle_event(c2, plate="GJ18TC0450", track_id=2, ts=base + timedelta(minutes=5),
                              vehicle_type="car", vehicle_color="white")
    svc = VehicleReIDService(db_session)
    svc.index_event(q)
    svc.index_event(same)
    res = svc.find_similar(event_id=q.id, limit=10, exclude_same_plate=True)
    assert all(not c["same_plate"] for c in res["candidates"])


def test_compare(db_session, make_camera, make_vehicle_event):
    c1 = make_camera(code="CAM-C1")
    c2 = make_camera(code="CAM-C2")
    a = make_vehicle_event(c1, plate="GJ18TC0450", vehicle_type="car", vehicle_color="white")
    b = make_vehicle_event(c2, plate="GJ18TC0450", vehicle_type="car", vehicle_color="white")
    out = VehicleReIDService(db_session).compare(a.id, b.id)
    assert out["same_plate"] is True
    assert out["similarity"] > 0.99
    assert "same vehicle" in out["note"].lower()


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #
def test_search_endpoint_and_audit(client, db_session, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    base = datetime.utcnow() - timedelta(hours=1)
    c1 = make_camera(code="CAM-S1")
    c2 = make_camera(code="CAM-S2")
    make_vehicle_event(c1, plate="GJ18TC0450", track_id=1, ts=base,
                       vehicle_type="car", vehicle_color="white")
    make_vehicle_event(c2, plate="GJ18TC0450", track_id=2, ts=base + timedelta(minutes=4),
                       vehicle_type="car", vehicle_color="white")

    r = client.post("/api/v1/ai/reid/search", json={"plate": "GJ18TC0450", "limit": 5},
                    headers=bearer(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query_plate"] == "GJ18TC0450"
    assert body["returned"] >= 1
    assert "not identity" in body["disclaimer"]

    from app.models.audit_log import AuditLog
    from sqlalchemy import select
    actions = {a for (a,) in db_session.execute(select(AuditLog.action)).all()}
    assert "AI_REID_SEARCH" in actions


def test_search_requires_auth(client):
    r = client.post("/api/v1/ai/reid/search", json={"plate": "GJ18TC0450"})
    assert r.status_code == 401


def test_backfill_rbac(client, db_session, operator_user, officer_user, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-BF")
    make_vehicle_event(cam, plate="GJ01AB0003", vehicle_type="car", vehicle_color="red")

    _, op_tok = operator_user
    assert client.post("/api/v1/ai/reid/backfill", headers=bearer(op_tok)).status_code == 403

    _, off_tok = officer_user
    r = client.post("/api/v1/ai/reid/backfill", headers=bearer(off_tok))
    assert r.status_code == 200, r.text
    assert r.json()["indexed"] >= 1


def test_compare_endpoint_unknown_event(client, officer_user):
    _, tok = officer_user
    r = client.post("/api/v1/ai/reid/compare",
                    json={"event_id_a": "nope-a", "event_id_b": "nope-b"},
                    headers=bearer(tok))
    assert r.status_code == 404
