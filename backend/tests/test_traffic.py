"""
Phase 14 (3/7) -- Traffic Intelligence + heatmap.

Covers: aggregation correctness, time windows, camera / vehicle-type /
zone filters, peak hour, trend, congestion, trend buckets, heatmap
(geolocated-only + weights), auth.
"""
from datetime import datetime, timedelta

from app.services.ai.traffic import TrafficAnalyticsService, TrafficFilters
from conftest import bearer


def _seed(mk, cam, n, plate_prefix, start, step_minutes=2, vtype="car"):
    for i in range(n):
        mk(cam, plate=f"{plate_prefix}{1000 + i}", track_id=i + 1,
           ts=start + timedelta(minutes=i * step_minutes), vehicle_type=vtype)


def test_overview_counts_and_window(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-T", lat=23.0, lon=72.5)
    now = datetime.utcnow()
    _seed(make_vehicle_event, cam, 10, "GJ01AA", now - timedelta(hours=2))
    # older than the 3h window -> excluded
    _seed(make_vehicle_event, cam, 5, "GJ09ZZ", now - timedelta(hours=30))

    svc = TrafficAnalyticsService(db_session)
    ov = svc.overview(TrafficFilters(), default_hours=3)
    assert ov["total_vehicles"] == 10
    assert ov["active_cameras"] == 1
    assert ov["vehicles_per_hour"] > 0
    assert ov["peak_hour"] is not None
    assert ov["congestion"] in ("NONE", "LOW", "MODERATE", "HIGH")


def test_overview_camera_and_type_filter(db_session, make_camera, make_vehicle_event):
    a = make_camera(code="CAM-F1", lat=23.0, lon=72.5)
    b = make_camera(code="CAM-F2", lat=23.1, lon=72.6)
    now = datetime.utcnow()
    _seed(make_vehicle_event, a, 6, "GJ01CA", now - timedelta(hours=1), vtype="car")
    _seed(make_vehicle_event, a, 4, "GJ01TR", now - timedelta(hours=1), vtype="truck")
    _seed(make_vehicle_event, b, 8, "GJ02CA", now - timedelta(hours=1), vtype="car")

    svc = TrafficAnalyticsService(db_session)
    only_a = svc.overview(TrafficFilters(camera_codes=["CAM-F1"]), default_hours=6)
    assert only_a["total_vehicles"] == 10

    cars_only = svc.overview(TrafficFilters(vehicle_type="car"), default_hours=6)
    assert cars_only["total_vehicles"] == 14

    a_trucks = svc.overview(
        TrafficFilters(camera_codes=["CAM-F1"], vehicle_type="truck"), default_hours=6
    )
    assert a_trucks["total_vehicles"] == 4


def test_zone_filter(db_session, make_camera, make_vehicle_event):
    a = make_camera(code="CAM-Z1", name="Paldi Circle", lat=23.0, lon=72.5)
    b = make_camera(code="CAM-Z2", name="Ranip Cross", lat=23.1, lon=72.6)
    now = datetime.utcnow()
    _seed(make_vehicle_event, a, 5, "GJ0P", now - timedelta(hours=1))
    _seed(make_vehicle_event, b, 9, "GJ0R", now - timedelta(hours=1))
    ov = TrafficAnalyticsService(db_session).overview(TrafficFilters(zone="paldi"), default_hours=6)
    assert ov["total_vehicles"] == 5


def test_trend_up_vs_prev_window(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-TR", lat=23.0, lon=72.5)
    now = datetime.utcnow()
    _seed(make_vehicle_event, cam, 3, "GJ0OLD", now - timedelta(hours=5), step_minutes=1)
    _seed(make_vehicle_event, cam, 12, "GJ0NEW", now - timedelta(hours=1), step_minutes=1)
    ov = TrafficAnalyticsService(db_session).overview(TrafficFilters(), default_hours=3)
    assert ov["trend"] == "up"
    assert ov["prev_window_total"] == 3


def test_by_camera_breakdown(db_session, make_camera, make_vehicle_event):
    a = make_camera(code="CAM-B1", lat=23.0, lon=72.5)
    b = make_camera(code="CAM-B2", lat=23.1, lon=72.6)
    now = datetime.utcnow()
    _seed(make_vehicle_event, a, 9, "GJ0A", now - timedelta(hours=1))
    _seed(make_vehicle_event, b, 3, "GJ0B", now - timedelta(hours=1))
    res = TrafficAnalyticsService(db_session).by_camera(TrafficFilters(), default_hours=6)
    codes = [c["camera_code"] for c in res["cameras"]]
    assert codes[0] == "CAM-B1"                     # busiest first
    assert res["cameras"][0]["total_vehicles"] == 9
    assert res["cameras"][0]["busiest_hour"] is not None


def test_trends_buckets(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-TS", lat=23.0, lon=72.5)
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    for h in range(4):
        _seed(make_vehicle_event, cam, h + 1, f"GJ{h}H", now - timedelta(hours=h), step_minutes=1)
    res = TrafficAnalyticsService(db_session).trends(TrafficFilters(), bucket="hour", default_hours=6)
    assert res["bucket"] == "hour"
    assert len(res["series"]) >= 3
    assert res["max_bucket"]["total"] >= 1


def test_heatmap_geolocated_only_and_weights(db_session, make_camera, make_vehicle_event):
    geo = make_camera(code="CAM-G", lat=23.03, lon=72.58)
    nogeo = make_camera(code="CAM-NG", lat=None, lon=None)
    now = datetime.utcnow()
    _seed(make_vehicle_event, geo, 10, "GJ0G", now - timedelta(hours=1))
    _seed(make_vehicle_event, nogeo, 5, "GJ0N", now - timedelta(hours=1))

    res = TrafficAnalyticsService(db_session).heatmap(
        TrafficFilters(), kind="vehicle_density", default_hours=6
    )
    codes = {p["camera_code"] for p in res["points"]}
    assert "CAM-G" in codes
    assert "CAM-NG" not in codes                    # no geometry -> excluded
    top = res["points"][0]
    assert top["count"] == 10
    assert top["weight"] == 1.0
    assert "fabricated" in res["note"]


def test_heatmap_kinds(db_session, make_camera, make_vehicle_event):
    cam = make_camera(code="CAM-HK", lat=23.03, lon=72.58)
    make_vehicle_event(cam, plate="GJ18TC0450", track_id=1)
    for kind in ("vehicle_density", "alert_density", "anomaly_density", "incident_density"):
        res = TrafficAnalyticsService(db_session).heatmap(TrafficFilters(), kind=kind)
        assert res["kind"] == kind
        assert isinstance(res["points"], list)


# ---- API ---------------------------------------------------------------- #
def test_traffic_endpoints(client, officer_user, make_camera, make_vehicle_event):
    _, tok = officer_user
    cam = make_camera(code="CAM-API", lat=23.03, lon=72.58)
    _seed(make_vehicle_event, cam, 8, "GJ0API", datetime.utcnow() - timedelta(hours=1))

    for path in ("overview", "cameras", "trends"):
        r = client.get(f"/api/v1/analytics/traffic/{path}", headers=bearer(tok))
        assert r.status_code == 200, (path, r.text)

    r = client.get("/api/v1/analytics/traffic/heatmap?kind=vehicle_density", headers=bearer(tok))
    assert r.status_code == 200
    assert r.json()["kind"] == "vehicle_density"


def test_traffic_requires_auth(client):
    assert client.get("/api/v1/analytics/traffic/overview").status_code == 401
