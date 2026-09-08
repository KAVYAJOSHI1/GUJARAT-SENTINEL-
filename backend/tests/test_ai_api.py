"""Phase 12 — AI API surface: status, suggestions, RBAC, offline (no-LLM) guarantee."""
from conftest import bearer


def test_status_reports_deterministic_by_default(client, officer_user):
    _, tok = officer_user
    b = client.get("/api/v1/ai/status", headers=bearer(tok)).json()
    assert b["provider"] == "deterministic"
    assert b["llm_available"] is False
    assert b["deterministic_always_on"] is True
    assert "min_seconds" in b["anomaly_thresholds"]


def test_suggestions_present(client, operator_user):
    b = client.get("/api/v1/ai/suggestions", headers=bearer(operator_user[1])).json()
    assert isinstance(b, list) and len(b) >= 8
    assert any("GJ18TC0450" in q for q in b)


def test_all_ai_endpoints_require_auth(client):
    assert client.post("/api/v1/ai/investigate", json={"query": "x"}).status_code == 401
    assert client.post("/api/v1/ai/search", json={"query": "x"}).status_code == 401
    assert client.get("/api/v1/ai/anomalies").status_code == 401
    assert client.post("/api/v1/ai/anomalies/scan", json={}).status_code == 401
    assert client.get("/api/v1/ai/status").status_code == 401


def test_read_endpoints_allow_operator_but_scan_does_not(client, operator_user):
    tok = operator_user[1]
    assert client.post("/api/v1/ai/investigate", json={"query": "where was GJ18TC0450 seen"},
                       headers=bearer(tok)).status_code == 200
    assert client.get("/api/v1/ai/anomalies", headers=bearer(tok)).status_code == 200
    assert client.post("/api/v1/ai/anomalies/scan", json={}, headers=bearer(tok)).status_code == 403


def test_offline_no_llm_full_flow(client, officer_user, make_camera, make_vehicle_event):
    """The whole AI layer works with the default deterministic provider and
    no OPENAI_API_KEY -- this is the offline demo guarantee (§7)."""
    _, tok = officer_user
    cam = make_camera(code="CAM-04", lat=23.02, lon=72.57)
    make_vehicle_event(cam, plate="GJ18TC0450", track_id=1)

    inv = client.post("/api/v1/ai/investigate", json={"query": "Where was GJ18TC0450 seen?"},
                      headers=bearer(tok)).json()
    assert inv["provider"] == "deterministic" and inv["result_count"] == 1

    srch = client.post("/api/v1/ai/search", json={"query": "show all vehicles detected today"},
                       headers=bearer(tok)).json()
    assert srch["search"]["total"] >= 1

    inc = client.post("/api/v1/incidents", json={"title": "t", "plate_number": "GJ18TC0450"},
                      headers=bearer(tok)).json()
    summ = client.post(f"/api/v1/ai/incidents/{inc['id']}/summary", headers=bearer(tok)).json()
    assert summ["provider"] == "deterministic"
