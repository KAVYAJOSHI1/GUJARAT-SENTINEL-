"""
Phase 4 -- audit coverage for the new security-relevant actions, and a
guard that credentials never reach the audit `detail` column.
"""
from sqlalchemy import select

from app.config import settings
from app.models.audit_log import AuditLog
from app.services.rate_limit import login_rate_limiter
from conftest import bearer


def _actions(db):
    return db.execute(select(AuditLog.action)).scalars().all()


def _details(db):
    return db.execute(select(AuditLog.detail)).scalars().all()


def test_rate_limited_login_is_audited(client, admin_user, db_session, monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_MAX_FAILURES", 2)
    login_rate_limiter.clear()
    for _ in range(3):
        client.post("/api/v1/auth/login",
                    json={"username": "test_admin", "password": "nope"})
    resp = client.post("/api/v1/auth/login",
                       json={"username": "test_admin", "password": "nope"})
    assert resp.status_code == 429
    assert "LOGIN_RATE_LIMITED" in _actions(db_session)


def test_failed_login_never_stores_the_password(client, admin_user, db_session):
    client.post("/api/v1/auth/login",
                json={"username": "test_admin", "password": "hunter2-secret"})
    blob = " ".join(d for d in _details(db_session) if d)
    assert "hunter2-secret" not in blob


def test_ws_and_media_ticket_issue_do_not_log_the_ticket(client, operator_user, db_session):
    _, token = operator_user
    ws = client.post("/api/v1/auth/ws-ticket", headers=bearer(token)).json()["ticket"]
    media = client.post("/api/v1/auth/media-ticket", headers=bearer(token)).json()["ticket"]
    blob = " ".join(d for d in _details(db_session) if d)
    assert ws not in blob
    assert media not in blob


def test_core_sensitive_actions_are_wired(client, officer_user, admin_user, make_camera, db_session):
    """Smoke-check the audit trail records the actions the audit report
    called out as needing coverage."""
    _, otoken = officer_user
    # login success
    client.post("/api/v1/auth/login", json={"username": "test_officer", "password": "Password123!"})
    # watchlist create + vehicle search + evidence path all audited elsewhere;
    # here just assert LOGIN_SUCCESS + LOGIN_FAILED are both present.
    client.post("/api/v1/auth/login", json={"username": "test_officer", "password": "x"})
    acts = set(_actions(db_session))
    assert {"LOGIN_SUCCESS", "LOGIN_FAILED"} <= acts
