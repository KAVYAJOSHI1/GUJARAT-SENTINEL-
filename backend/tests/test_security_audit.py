"""
Phase 20 Part I -- security audit tests for the gaps not already covered
by the existing suite.

Already covered elsewhere (not duplicated here):
  - CORS wildcard-dropped-outside-dev, explicit origin list -- test_cors.py
  - scoped-ticket (WS/media) expiry, scope confusion -- test_transport_tickets.py
  - WS authentication (missing/expired/wrong-scope ticket) -- test_ws_auth.py
  - login rate limiting -- test_login_rate_limit.py
  - audit logging coverage across watchlist/alerts/incidents/cases/evidence
    -- test_audit_log.py, test_audit_center.py, test_audit_coverage.py
  - watchlist RBAC / duplicate / expiry edge cases -- test_watchlist_management.py,
    test_watchlist_expiry.py

This file covers: main SESSION-JWT expiry/tampering (distinct from the
short-lived scoped tickets above), RBAC on a real mutating endpoint,
SQL-injection-shaped input treated as an inert literal (never breaks the
parameterized query), malformed JSON, and an oversized request body.
"""
from datetime import timedelta

import pytest
from jose import jwt

from app.config import settings
from app.core.security import create_access_token
from conftest import bearer


# --------------------------------------------------------------------- #
# JWT: expiry / tampering / malformed
# --------------------------------------------------------------------- #
def test_expired_session_jwt_is_rejected(client, officer_user):
    user, _ = officer_user
    expired = create_access_token(subject=user.id, role=user.role.value, expires_minutes=-1)
    r = client.get("/api/v1/cameras", headers=bearer(expired))
    assert r.status_code == 401
    assert r.json()["error"]["code"] in ("INVALID_TOKEN", "TOKEN_EXPIRED")


def test_tampered_signature_is_rejected(client, officer_user):
    user, tok = officer_user
    # Flip the last character of the signature segment -- a byte-for-byte
    # valid JWT shape, invalid signature.
    header, payload, sig = tok.rsplit(".", 2) if tok.count(".") == 2 else (None, None, None)
    assert sig is not None
    bad_char = "A" if sig[-1] != "A" else "B"
    tampered = f"{header}.{payload}.{sig[:-1]}{bad_char}"
    r = client.get("/api/v1/cameras", headers=bearer(tampered))
    assert r.status_code == 401


def test_token_signed_with_a_different_secret_is_rejected(client, officer_user):
    user, _ = officer_user
    forged = jwt.encode(
        {"sub": user.id, "role": user.role.value, "exp": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc) + timedelta(hours=1)},
        "not-the-real-secret", algorithm=settings.JWT_ALGORITHM,
    )
    r = client.get("/api/v1/cameras", headers=bearer(forged))
    assert r.status_code == 401


def test_malformed_bearer_value_is_rejected_not_500(client):
    r = client.get("/api/v1/cameras", headers={"Authorization": "Bearer not-even-a-jwt"})
    assert r.status_code == 401


def test_missing_authorization_header_is_401_not_500(client):
    r = client.get("/api/v1/cameras")
    assert r.status_code == 401


def test_deactivated_users_token_is_rejected(client, db_session, officer_user):
    user, tok = officer_user
    user.is_active = False
    db_session.add(user)
    db_session.commit()
    r = client.get("/api/v1/cameras", headers=bearer(tok))
    assert r.status_code == 401


# --------------------------------------------------------------------- #
# RBAC: a real mutating endpoint, not just presence of a dependency
# --------------------------------------------------------------------- #
def test_operator_cannot_create_a_camera(client, operator_user):
    _, tok = operator_user
    r = client.post("/api/v1/cameras", json={
        "code": "SEC-RBAC-1", "name": "unauthorized camera", "latitude": 23.0, "longitude": 72.5,
    }, headers=bearer(tok))
    assert r.status_code == 403


def test_operator_cannot_write_the_watchlist(client, operator_user):
    _, tok = operator_user
    r = client.post("/api/v1/watchlist", json={
        "plate_number": "GJ99ZZ9999", "offense_category": "STOLEN", "priority_level": "HIGH",
    }, headers=bearer(tok))
    assert r.status_code == 403


def test_officer_can_write_the_watchlist_admin_and_officer_are_not_the_same_gate(client, officer_user):
    """Confirms the 403 above is a real role gate, not just 'anything
    non-admin fails' -- OFFICER is explicitly permitted to write the
    watchlist per SECURITY.md's own RBAC matrix."""
    _, tok = officer_user
    r = client.post("/api/v1/watchlist", json={
        "plate_number": "GJ99YY8888", "offense_category": "STOLEN", "priority_level": "HIGH",
    }, headers=bearer(tok))
    assert r.status_code in (200, 201)


def test_operator_cannot_delete_a_camera(client, operator_user, make_camera):
    _, tok = operator_user
    cam = make_camera(code="SEC-RBAC-DEL")
    r = client.delete(f"/api/v1/cameras/{cam.id}", headers=bearer(tok))
    assert r.status_code == 403


# --------------------------------------------------------------------- #
# Injection-shaped input is inert (SQLAlchemy ORM parameterization)
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("hostile", [
    "GJ01AB1234' OR '1'='1",
    "'; DROP TABLE vehicle_events; --",
    "GJ01AB1234\"; SELECT * FROM users; --",
])
def test_sql_injection_shaped_plate_is_treated_as_an_inert_literal(client, officer_user, hostile):
    _, tok = officer_user
    r = client.get("/api/v1/vehicles/search", params={"plate": hostile}, headers=bearer(tok))
    # Never a 500 (a broken/succeeded injection would show up as a server
    # error or a nonsensical result) -- either a clean empty result or a
    # validation rejection, both are safe outcomes.
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert r.json()["total_sightings"] == 0

    # the table must still exist and be queryable afterward
    still_alive = client.get("/api/v1/vehicles/search", params={"plate": "GJ01AB1234"}, headers=bearer(tok))
    assert still_alive.status_code == 200


def test_path_traversal_shaped_event_id_returns_not_found_never_a_file(client, officer_user):
    _, tok = officer_user
    r = client.get("/api/v1/vehicles/evidence/" + "..%2F..%2F..%2Fetc%2Fpasswd", headers=bearer(tok))
    assert r.status_code in (401, 404, 422)
    assert b"root:" not in r.content


# --------------------------------------------------------------------- #
# Malformed / oversized requests
# --------------------------------------------------------------------- #
def test_malformed_json_body_is_a_clean_422_not_a_crash(client, officer_user):
    _, tok = officer_user
    r = client.post(
        "/api/v1/events/ai-detection",
        data="{not valid json!!",
        headers={**bearer(tok), "Content-Type": "application/json", "X-Ingest-Key": "test-ingest-key"},
    )
    assert r.status_code in (400, 422)
    body = r.json()
    assert body.get("success") is False


def test_wrong_type_field_is_a_validation_error_not_a_crash(client):
    r = client.post(
        "/api/v1/events/ai-detection",
        json={"camera_id": "cam-sec-1", "timestamp": 12345, "vehicle": "not-an-object"},
        headers={"X-Ingest-Key": "test-ingest-key"},
    )
    assert r.status_code == 422


def test_oversized_camera_id_is_a_clean_422_not_a_crash(client):
    """Regression: an unbounded camera_id previously reached Postgres's own
    btree-index row-size limit on insert (camera_id is a unique-indexed
    column, and ingest auto-onboarding writes it straight through) and
    surfaced as an unhandled 500 -- caught cleanly by the generic exception
    handler, but never actually validated at the API boundary where it
    belongs. Fixed with a Field(max_length=...) bound (Phase 20 Part I);
    this test pins the fix, not just documents a pre-existing gap.

    No general max-request-body-size middleware is configured in this PoC
    (see docs/HACKATHON_ARCHITECTURE.md limitations) -- a production
    deployment should also terminate oversized bodies in front of the app
    (reverse proxy body-size limit); this test covers the one field that
    was concretely reachable and concretely broken."""
    huge = "A" * (2 * 1024 * 1024)  # 2 MB in one string field
    r = client.post(
        "/api/v1/events/ai-detection",
        json={"camera_id": huge, "timestamp": "2026-09-09T10:00:00",
              "vehicle": {"type": "car", "confidence": 0.9},
              "license_plate": {"plate_detected": False, "plate_number": "UNKNOWN", "confidence": 0.0}},
        headers={"X-Ingest-Key": "test-ingest-key"},
    )
    assert r.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
