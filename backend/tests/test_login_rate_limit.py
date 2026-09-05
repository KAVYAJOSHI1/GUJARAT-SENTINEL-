"""
Phase 4 -- POST /api/v1/auth/login rate limiting.

Covers: repeated failures -> 429 with Retry-After, no credential leakage in
the 429 body, a successful login clearing the throttle, the limiter being
keyed per (ip, username), and config-driven disable.
"""
import pytest

from app.config import settings
from app.services.rate_limit import login_rate_limiter


@pytest.fixture(autouse=True)
def _tight_limit(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_MAX_FAILURES", 3)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 300)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_BLOCK_SECONDS", 120)
    login_rate_limiter.clear()
    yield
    login_rate_limiter.clear()


def _bad_login(client, username="test_admin", password="wrong-password"):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_repeated_failures_return_429_with_retry_after(client, admin_user):
    for _ in range(3):
        assert _bad_login(client).status_code == 401
    resp = _bad_login(client)
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") is not None
    assert int(resp.headers["Retry-After"]) > 0


def test_429_body_leaks_no_credentials(client, admin_user):
    for _ in range(4):
        _bad_login(client, password="super-secret-guess")
    resp = _bad_login(client, password="super-secret-guess")
    assert resp.status_code == 429
    body = resp.text
    assert "super-secret-guess" not in body
    assert "hashed_password" not in body
    # generic message only -- doesn't confirm the username exists
    msg = resp.json()["error"]["message"].lower()
    assert "test_admin" not in msg


def test_successful_login_clears_throttle(client, admin_user):
    _, _ = admin_user
    for _ in range(2):
        assert _bad_login(client).status_code == 401
    ok = client.post(
        "/api/v1/auth/login",
        json={"username": "test_admin", "password": "Password123!"},
    )
    assert ok.status_code == 200
    # counter reset -> another wrong attempt is a plain 401, not 429
    assert _bad_login(client).status_code == 401


def test_limit_is_per_username(client, admin_user, officer_user):
    for _ in range(4):
        _bad_login(client, username="test_admin")
    assert _bad_login(client, username="test_admin").status_code == 429
    # a different account from the same client IP is unaffected
    assert _bad_login(client, username="test_officer").status_code == 401


def test_disabled_via_config(client, admin_user, monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ENABLED", False)
    login_rate_limiter.clear()
    for _ in range(10):
        assert _bad_login(client).status_code == 401  # never 429
