"""
Phase 4 -- CORS origin allow-list.

Covers: resolved_cors_origins() drops "*" outside a dev environment, keeps
an explicit list, and keeps "*" in a dev environment; and that the running
app reflects an allowed origin.
"""
from app.config import Settings


def _settings(**over):
    base = dict(CORS_ALLOW_ORIGINS=["https://ops.example.gov"], ENV="production")
    base.update(over)
    return Settings(**base)


def test_wildcard_dropped_outside_dev():
    s = _settings(CORS_ALLOW_ORIGINS=["*", "https://ops.example.gov"], ENV="production")
    assert s.resolved_cors_origins() == ["https://ops.example.gov"]


def test_wildcard_kept_in_dev():
    s = _settings(CORS_ALLOW_ORIGINS=["*"], ENV="development")
    assert s.resolved_cors_origins() == ["*"]


def test_explicit_list_passes_through():
    s = _settings(CORS_ALLOW_ORIGINS=["http://localhost:3000"], ENV="production")
    assert s.resolved_cors_origins() == ["http://localhost:3000"]


def test_running_app_allows_configured_origin(client):
    # conftest sets CORS_ALLOW_ORIGINS='["*"]' + ENV=test (a dev env) so "*"
    # is honoured -- a preflight from any origin gets the CORS headers back.
    resp = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code in (200, 204)
    assert "access-control-allow-origin" in {k.lower() for k in resp.headers}


def test_dev_env_detection():
    assert Settings(ENV="development").is_dev_env() is True
    assert Settings(ENV="test").is_dev_env() is True
    assert Settings(ENV="production").is_dev_env() is False
    assert Settings(ENV="staging").is_dev_env() is False
