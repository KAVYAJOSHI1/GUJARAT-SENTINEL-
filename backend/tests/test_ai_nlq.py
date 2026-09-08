"""Phase 12 — deterministic NL query parser (no LLM, no DB)."""
from datetime import datetime, timedelta

from app.services.ai.nlq import parse_query

NOW = datetime(2026, 9, 8, 22, 30, 0)


def p(q, **kw):
    return parse_query(q, now=NOW, **kw)


def test_plate_extraction_variants():
    for q in ["Where was GJ18TC0450 seen?", "show gj 18 tc 0450", "trace GJ18-TC-0450"]:
        assert p(q).plate == "GJ18TC0450"
    assert p("show white cars after 9pm").plate is None


def test_this_vehicle_uses_context():
    assert p("show the journey of this vehicle", context_plate="GJ01AB1234").plate == "GJ01AB1234"
    r = p("show the journey of this vehicle")
    assert r.plate is None and any("no plate context" in n for n in r.notes)


def test_camera_extraction():
    r = p("vehicles near CAM-04")
    assert "CAM-04" in r.camera_codes
    r2 = p("show detections at camera 7")
    assert "CAM-07" in r2.camera_codes


def test_relative_windows():
    r = p("where was GJ18TC0450 seen in the last 6 hours")
    assert r.relative_window == "last 6 hour(s)"
    assert r.date_from == NOW - timedelta(hours=6)

    r = p("show watchlist vehicles detected today")
    assert r.relative_window == "today"
    assert r.date_from == NOW.replace(hour=0, minute=0, second=0, microsecond=0)

    r = p("find GJ18TC0450 yesterday")
    assert r.relative_window == "yesterday"
    assert r.date_from == (NOW - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    assert r.date_to == r.date_from + timedelta(days=1)


def test_time_of_day():
    assert p("vehicles detected after 9 PM").time_from == "21:00"
    assert p("show cars before 8am").time_to == "08:00"
    r = p("show unknown vehicles between 8 PM and 10 PM")
    assert (r.time_from, r.time_to) == ("20:00", "22:00")
    assert r.unknown_only is True


def test_duration_extraction():
    assert p("show vehicles detected for more than 5 minutes").min_duration_seconds == 300
    assert p("vehicles present longer than 90 seconds").min_duration_seconds == 90


def test_vehicle_type_and_colour():
    r = p("show white SUVs after 9 PM")
    assert r.vehicle_type == "car" and r.vehicle_color == "white"
    assert p("find a red motorcycle").vehicle_type == "motorcycle"


def test_intent_classification():
    assert p("show the journey of GJ18TC0450").intent == "VEHICLE_JOURNEY"
    assert p("which cameras detected GJ18TC0450").intent == "CAMERA_SEARCH"
    assert p("show all alerts related to GJ18TC0450").intent == "ALERT_SEARCH"
    assert p("which incidents are associated with GJ18TC0450").intent == "INCIDENT_SEARCH"
    assert p("show evidence related to this investigation").intent == "EVIDENCE_SEARCH"
    assert p("show watchlist vehicles detected today").intent == "WATCHLIST_SEARCH"
    assert p("where was GJ18TC0450 seen").intent == "VEHICLE_SEARCH"
    assert p("show vehicles detected near CAM-04 after 9 PM").intent in ("TIME_RANGE_SEARCH", "CAMERA_SEARCH")
