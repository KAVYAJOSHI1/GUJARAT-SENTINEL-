"""Advanced Watchlist Management + CSV import/export (Phase 11 FEATURE 3)."""
import io
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.watchlist import Watchlist
from app.services.watchlist_engine import find_watchlist_match
from conftest import bearer


def test_list_filters_sort_pagination(client, admin_user):
    _, tok = admin_user
    for i in range(6):
        client.post("/api/v1/watchlist", json={
            "plate_number": f"GJ01AB{1000+i}", "offense_category": "STOLEN" if i % 2 else "WANTED",
            "priority_level": "CRITICAL" if i == 0 else "LOW",
        }, headers=bearer(tok))
    page = client.get("/api/v1/watchlist", params={"limit": 2}, headers=bearer(tok)).json()
    assert page["total"] == 6 and len(page["items"]) == 2
    stolen = client.get("/api/v1/watchlist", params={"category": "STOLEN"}, headers=bearer(tok)).json()
    assert stolen["total"] == 3
    crit = client.get("/api/v1/watchlist", params={"priority": "CRITICAL"}, headers=bearer(tok)).json()
    assert crit["total"] == 1


def test_edit_activate_deactivate_and_audit(client, admin_user):
    _, tok = admin_user
    e = client.post("/api/v1/watchlist", json={"plate_number": "GJ05CD9090", "offense_category": "SUSPICIOUS"},
                    headers=bearer(tok)).json()
    wid = e["id"]

    upd = client.patch(f"/api/v1/watchlist/{wid}",
                       json={"priority_level": "HIGH", "description": "seen near bank"},
                       headers=bearer(tok))
    assert upd.status_code == 200
    assert upd.json()["priority_level"] == "HIGH" and upd.json()["description"] == "seen near bank"
    assert upd.json()["updated_by_username"] == "test_admin"

    d = client.delete(f"/api/v1/watchlist/{wid}", headers=bearer(tok))
    assert d.status_code == 204
    assert client.get("/api/v1/watchlist", params={"status": "inactive"}, headers=bearer(tok)).json()["total"] == 1

    a = client.post(f"/api/v1/watchlist/{wid}/activate", headers=bearer(tok))
    assert a.status_code == 200 and a.json()["active"] is True

    with SessionLocal() as db:
        acts = {r.action for r in db.execute(select(AuditLog)).scalars()}
    assert {"WATCHLIST_CREATED", "WATCHLIST_UPDATED", "WATCHLIST_DEACTIVATED", "WATCHLIST_ACTIVATED"} <= acts


def test_effective_from_enforced_by_engine(client, admin_user, db_session):
    _, tok = admin_user
    future = (datetime.utcnow() + timedelta(days=2)).isoformat()
    r = client.post("/api/v1/watchlist", json={
        "plate_number": "GJ07EF2020", "offense_category": "INVESTIGATION", "effective_from": future,
    }, headers=bearer(tok))
    assert r.status_code == 201 and r.json()["is_pending"] is True
    # not yet effective -> engine must not match
    assert find_watchlist_match(db_session, "GJ07EF2020") is None


def test_expiry_and_effective_indicators(client, admin_user, db_session):
    _, tok = admin_user
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    client.post("/api/v1/watchlist", json={
        "plate_number": "GJ08GH3030", "offense_category": "MISSING", "expires_at": past,
    }, headers=bearer(tok))
    exp = client.get("/api/v1/watchlist", params={"status": "expired"}, headers=bearer(tok)).json()
    assert exp["total"] == 1 and exp["items"][0]["is_expired"] is True
    assert exp["items"][0]["is_currently_effective"] is False


def test_csv_export_then_import_roundtrip_and_validation(client, admin_user):
    _, tok = admin_user
    # existing demo-style entry to be UPDATED by the import
    client.post("/api/v1/watchlist", json={"plate_number": "GJ18TC0450", "offense_category": "WANTED"},
                headers=bearer(tok))

    csv_body = (
        "plate_number,offense_category,priority_level,reason,description,effective_from,expires_at,active\n"
        "GJ18TC0450,STOLEN,CRITICAL,updated,,,,true\n"           # update existing
        "GJ22AB0001,WANTED,HIGH,new one,,,,true\n"              # create
        "BADPLATE,STOLEN,HIGH,,,,,true\n"                        # invalid format
        "GJ22AB0002,NOTACATEGORY,HIGH,,,,,true\n"               # invalid category
        "GJ22AB0003,STOLEN,HIGH,,,not-a-date,,true\n"           # invalid date
        ",STOLEN,HIGH,,,,,true\n"                                # missing plate
        "GJ22AB0001,STOLEN,LOW,,,,,true\n"                      # dup within file -> skipped
    )
    files = {"file": ("wl.csv", io.BytesIO(csv_body.encode()), "text/csv")}
    res = client.post("/api/v1/watchlist/import.csv", files=files, headers=bearer(tok)).json()
    assert res["created"] == 1
    assert res["updated"] == 1
    assert res["skipped"] == 1
    assert res["invalid"] == 4  # bad format, bad category, bad date, missing plate

    # GJ18TC0450 demo entry still present and now STOLEN/CRITICAL
    got = client.get("/api/v1/watchlist", params={"q": "GJ18TC0450"}, headers=bearer(tok)).json()
    assert got["total"] == 1 and got["items"][0]["offense_category"] == "STOLEN"

    exp = client.get("/api/v1/watchlist/export.csv", headers=bearer(tok))
    assert exp.status_code == 200 and exp.headers["content-type"].startswith("text/csv")
    assert "GJ22AB0001" in exp.text


def test_dry_run_import_writes_nothing(client, admin_user):
    _, tok = admin_user
    csv_body = "plate_number,offense_category,priority_level\nGJ33DR0001,STOLEN,HIGH\n"
    files = {"file": ("wl.csv", io.BytesIO(csv_body.encode()), "text/csv")}
    res = client.post("/api/v1/watchlist/import.csv?dry_run=true", files=files, headers=bearer(tok)).json()
    assert res["created"] == 1
    assert client.get("/api/v1/watchlist", params={"q": "GJ33DR0001"}, headers=bearer(tok)).json()["total"] == 0


def test_watchlist_rbac(client, operator_user):
    tok = operator_user[1]
    assert client.get("/api/v1/watchlist", headers=bearer(tok)).status_code == 200
    assert client.post("/api/v1/watchlist", json={"plate_number": "GJ00NO0000", "offense_category": "OTHER"},
                       headers=bearer(tok)).status_code == 403
